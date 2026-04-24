"""
rag/query.py
------------
CLI for querying lineage with RAG + Claude.

Subcommands:
  ask "What pipelines depend on orders?"   - free natural language question
  impact orders                            - downstream impact analysis for a dataset
  sync                                     - re-ingest and re-vectorize
  watch                                    - near real-time (file watcher)

Usage:
  python -m rag.query ask "What breaks if I change orders?"
  python -m rag.query impact orders
  python -m rag.query sync
  python -m rag.query watch
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

load_dotenv()

CHAT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chat"
)
import chromadb
import networkx as nx

from rag.ingest import (
    EVENTS_PATH,
    build_graph,

    load_events,
    load_jobs_code,
    load_events_s3,
    load_job_code_s3,
)
from rag.vectorize import build_index, get_collection
from rag.tools import TOOLS as _TOOLS, execute_tool_call as _execute_tool_call
from rag.tools.dataset import downstream_layers as _downstream_layers

SYSTEM_PROMPT = """\
Eres un asistente experto en linaje de datos para equipos de ETL y en consultas SQL sobre Amazon Athena. Respondes siempre en español, de forma concisa y estructurada.

Dispones de un contexto con:
- Datasets
- Pipelines (jobs) que leen/escriben
- Transformaciones SQL dentro del .py de Glue (si está disponible)
- Historial de ejecuciones
- Schema
- Linaje de columnas

## Clasificación de la pregunta
Antes de responder, identifica el tipo:
- ESQUEMA
- LISTAR TABLAS
- IMPACTO
- LINAJE DE COLUMNA
- CONSULTA ATHENA
- GENERAL

Si no es claro, responde como GENERAL.

## Reglas por tipo

### ESQUEMA
- Lista todas las columnas con su tipo.
- Si existe "Schema:" en el contexto, úsalo íntegramente sin modificar.
- Formato: tabla o lista clara.

### LISTAR TABLAS
- Lista todos los datasets del namespace solicitado.
- Incluye job productor si existe.
- Formato: lista.

### IMPACTO
- Indica:
  1. Jobs ETL afectados
  2. Datasets downstream impactados
  3. SQL relevante (solo transformaciones directamente relacionadas con el cambio)
- Explica brevemente el motivo del impacto.

### LINAJE DE COLUMNA
- Usa "Linaje de columnas".
- Para cada campo:
  - Origen
  - Tipo de transformación (DIRECT / INDIRECT)
- Formato estructurado.

### CONSULTA ATHENA
- Genera una query SQL válida para Amazon Athena basándote en la pregunta del usuario y el schema disponible en el contexto.
- Usa el nombre de tabla y columnas exactamente como aparecen en el schema del contexto.
- Si se mencionan varias fuentes, combínalas con OR o con UNION según corresponda.
- Si la pregunta pide un conteo (ej: "cuántos contratos"), usa COUNT(*) o COUNT(DISTINCT <campo_clave>).
- Añade siempre un comentario SQL encima de la query explicando qué hace.
- Si el schema no está disponible en el contexto, indica: "No se encontró el schema de la tabla en el contexto. Ejecuta 'sync' primero."
- Formato: bloque de código SQL.

### GENERAL
- Responde solo con información presente en el contexto.
- Si el contexto no tiene información relevante, responde: "No se encontró información relevante en el índice de linaje. Ejecuta 'sync' primero."

## Uso de herramientas — cuándo llamar a cada una

Tienes herramientas disponibles. Úsalas de forma proactiva cuando el contexto no sea suficiente:

- **`get_job_code`**: si el contexto dice `Código fuente disponible: xxx.py`, llámala automáticamente. No pidas al usuario que pregunte de nuevo.
- **`get_dataset_schema`**: si preguntan por columnas/estructura de una tabla y no está en el contexto.
- **`search_by_field`**: si preguntan por un campo/columna concreto ("¿dónde está X?", "¿qué tablas tienen Y?"). Más fiable que el contexto semántico para nombres de columnas.
- **`get_downstream_impact`**: si preguntan qué se rompe o qué depende de un dataset. Devuelve el árbol exacto del grafo.
- **`find_jobs_by_dataset`**: si preguntan quién produce o consume un dataset concreto.

## Reglas globales
- No inventes información.
- Si falta un dato, indica: "No disponible en el contexto".
- Si hay inconsistencias, señálalas explícitamente.
- Prioriza claridad y formato estructurado.
- No escribas las lineas muy juntas, usa saltos de línea para claridad.
- Cuando uses una línea separadora (del estilo `________________________`), añade siempre un salto de línea antes y después de ella.
- Si la respuesta es demasiado larga y debes truncarla o recortarla, añade al final: "⚠️ He recortado la respuesta porque el contexto es muy amplio. Filtra la pregunta por namespace, dataset concreto o campo específico para obtener la respuesta completa."

"""


# ── Consulta RAG ──────────────────────────────────────────────────────────────

_LIST_KEYWORDS = {
    "listar", "lista", "todos", "todas", "enumera", "muéstrame",
    "cuántos", "cuantos", "qué tablas", "que tablas",
    "qué datasets", "que datasets", "inventario",
}


def _is_list_query(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _LIST_KEYWORDS)


def _detect_filters(
    question: str, collection: chromadb.Collection
) -> tuple[str | None, str | None]:
    """Detecta namespace y/o nombre de dataset mencionados en la pregunta.

    Usa matching exacto por substring Y matching por tokens (split en _-/espacio)
    para capturar referencias parciales. Prioriza términos más largos (más específicos).
    """
    try:
        all_metas = collection.get(include=["metadatas"])["metadatas"] or []
        q = question.lower()
        q_tokens = set(re.split(r"[\s_\-/]+", q))

        namespaces = {str(v) for m in all_metas if (v := m.get("namespace"))}
        names = {str(v) for m in all_metas if (v := m.get("name"))}

        def matches(term: str) -> bool:
            tl = term.lower()
            if tl in q:
                return True
            term_tokens = set(re.split(r"[\s_\-/]+", tl))
            return len(term_tokens) > 1 and term_tokens.issubset(q_tokens)

        ns = next((n for n in sorted(namespaces, key=lambda x: len(x), reverse=True) if matches(n)), None)
        name = next((n for n in sorted(names, key=lambda x: len(x), reverse=True) if matches(n)), None)
        return ns, name
    except Exception:
        return None, None


def _rewrite_query(question: str, history: list[dict], client: anthropic.Anthropic) -> str:
    """Rewrite the question as optimal search terms for the RAG index."""
    recent = [
        (m["content"] if m["role"] == "user" else m["content"][:200])
        for m in history[-6:]
        if m["role"] in ("user", "assistant")
    ]
    ctx_block = f"Contexto previo:\n{chr(10).join(recent[-3:])}\n\n" if recent else ""
    prompt = (
        "Reescribe la siguiente pregunta como una consulta de búsqueda semántica concisa "
        "para un índice de linaje de datos (datasets, jobs ETL, SQL, columnas, namespaces). "
        "Incluye sinónimos y términos técnicos relevantes. "
        "Responde SOLO con la query reescrita, sin explicaciones ni puntuación extra.\n\n"
        f"{ctx_block}Pregunta: {question}"
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        block = next((b for b in resp.content if b.type == "text"), None)
        return block.text.strip() if block else question
    except Exception:
        return question


def _rerank_docs(
    question: str, docs: list[str], client: anthropic.Anthropic, top_k: int = 8
) -> list[str]:
    """Filter and reorder retrieved docs by relevance using Claude Haiku."""
    if len(docs) <= top_k:
        return docs
    numbered = "\n\n".join(f"[{i}] {doc[:400]}" for i, doc in enumerate(docs))
    prompt = (
        f"Pregunta: {question}\n\n"
        f"Fragmentos de contexto:\n{numbered}\n\n"
        f"Devuelve los índices de los fragmentos MÁS relevantes para responder la pregunta, "
        f"en orden de relevancia (máximo {top_k}). "
        "Responde SOLO con los índices separados por coma, ejemplo: 2,0,5,1"
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        block = next((b for b in resp.content if b.type == "text"), None)
        if not block:
            return docs[:top_k]
        indices = [int(x.strip()) for x in block.text.strip().split(",") if x.strip().isdigit()]
        indices = [i for i in indices if 0 <= i < len(docs)]
        reranked = [docs[i] for i in indices[:top_k]]
        return reranked if reranked else docs[:top_k]
    except Exception:
        return docs[:top_k]


_CODE_KEYWORDS = {
    "código", "codigo", "script", "implementación", "implementacion",
    "cómo funciona", "como funciona", "qué hace", "que hace",
    "lógica", "logica", "fuente", "python", ".py", "glue", "spark",
    "muéstrame", "muestrame", "enséñame", "enseñame", "ver el código",
    # lógica de campos
    "cómo se calcula", "como se calcula", "cómo se genera", "como se genera",
    "cómo se construye", "como se construye", "cómo se obtiene", "como se obtiene",
    "de dónde viene", "de donde viene", "de dónde sale", "de donde sale",
    "cómo se rellena", "como se rellena", "cómo se popula", "como se popula",
    "qué lógica", "que logica", "qué lógica", "que lógica",
    "lógica del campo", "logica del campo", "lógica de la columna", "logica de la columna",
    "cómo se deriva", "como se deriva", "cómo se transforma", "como se transforma",
    "ver", "muestra", "dame", "necesito",
}


def _is_code_query(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _CODE_KEYWORDS)


def _graph_context(G: nx.DiGraph, question: str) -> str:
    """Find the job or dataset mentioned in the question and serialize its full subgraph."""
    q = question.lower()

    # Exact match first, then partial - jobs take priority
    match_key = None
    match_kind = None
    best_len = 0
    for key, data in G.nodes(data=True):
        name = data.get("name", "")
        if not name:
            continue
        if name.lower() in q and len(name) > best_len:
            best_len = len(name)
            match_key = key
            match_kind = data.get("kind")

    if not match_key:
        return ""

    node = G.nodes[match_key]
    lines: list[str] = []

    if match_kind == "job":
        inputs = [(src, G.nodes[src]) for src in G.predecessors(match_key) if G.nodes[src].get("kind") == "dataset"]
        outputs = [(tgt, G.nodes[tgt]) for tgt in G.successors(match_key) if G.nodes[tgt].get("kind") == "dataset"]
        runs = node.get("runs", [])
        n_ok = sum(1 for r in runs if r["type"] == "COMPLETE")
        n_fail = sum(1 for r in runs if r["type"] == "FAIL")
        last = runs[-1] if runs else None

        lines.append(f"Job: {node.get('name', '?')}")
        lines.append(f"Namespace: {node.get('namespace', '?')}")
        lines.append(f"Ejecuciones: {n_ok} exitosas, {n_fail} fallidas")
        if last:
            lines.append(f"Último evento: {last['type']} en {last['ts']}")

        if node.get("glue_code"):
            if _is_code_query(question):
                print(f"[debug] Detected code-related question, including glue code for job '{node.get('name', '?')}'")
                lines.append(f"\nCódigo fuente ({node.get('name', '?')}.py):\n```python\n{node['glue_code'].strip()}\n```")
            else:
                lines.append(f"\nCódigo fuente disponible: {node.get('name', '?')}.py")

        lines.append(f"\nInputs ({len(inputs)}):")
        for _, ds in inputs:
            lines.append(f"  - {ds.get('name', '?')} [{ds.get('namespace', '?')}]")
            if ds.get("schema"):
                lines.append(f"    Schema: {', '.join(ds['schema'])}")
            if ds.get("column_lineage"):
                for out_field, srcs in ds["column_lineage"].items():
                    src_str = ", ".join(f"{s['table']}.{s['field']}" for s in srcs)
                    lines.append(f"    {out_field} ← {src_str}")

        lines.append(f"\nOutputs ({len(outputs)}):")
        for _, ds in outputs:
            lines.append(f"  - {ds.get('name', '?')} [{ds.get('namespace', '?')}]")
            if ds.get("schema"):
                lines.append(f"    Schema: {', '.join(ds['schema'])}")
            if ds.get("column_lineage"):
                for out_field, srcs in ds["column_lineage"].items():
                    src_str = ", ".join(f"{s['table']}.{s['field']}" for s in srcs)
                    lines.append(f"    {out_field} ← {src_str}")

    elif match_kind == "dataset":
        producers = [(src, G.nodes[src]) for src in G.predecessors(match_key) if G.nodes[src].get("kind") == "job"]
        consumers = [(tgt, G.nodes[tgt]) for tgt in G.successors(match_key) if G.nodes[tgt].get("kind") == "job"]

        lines.append(f"Dataset: {node.get('name', '?')}")
        lines.append(f"Namespace: {node.get('namespace', '?')}")
        lines.append(f"Formato: {node.get('format', '?')}")
        if node.get("schema"):
            lines.append(f"Schema: {', '.join(node['schema'])}")
        if node.get("column_lineage"):
            lines.append("Linaje de columnas:")
            for out_field, srcs in node["column_lineage"].items():
                src_str = ", ".join(f"{s['table']}.{s['field']} [{s['type']}/{s['subtype']}]" for s in srcs)
                lines.append(f"  {out_field} ← {src_str}")
        if producers:
            lines.append(f"Producido por: {', '.join(d.get('name', k) for k, d in producers)}")
        if consumers:
            lines.append(f"Consumido por: {', '.join(d.get('name', k) for k, d in consumers)}")

    return "\n".join(lines)




def ask(
    question: str,
    collection: chromadb.Collection,
    n_results: int = 20,
    history: list[dict] | None = None,
    G: nx.DiGraph | None = None,
    bucket: str | None = None,
    jobs_prefix: str = "glue/code/jobs/",
) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "[ERROR] ANTHROPIC_API_KEY environment variable is missing."

    history = history or []
    client = anthropic.Anthropic()

    # 1. Increase n_results for inventory-style questions
    if _is_list_query(question):
        n_results = max(n_results, 40)

    # 2. Build search_query from recent history (user messages + assistant snippets)
    recent_context = [
        (m["content"] if m["role"] == "user" else m["content"][:200])
        for m in history[-6:]
        if m["role"] in ("user", "assistant")
    ]
    raw_query = " ".join(recent_context[-4:] + [question])

    # 3. Rewrite query with Haiku to improve semantic retrieval
    search_query = _rewrite_query(question, history, client)
    # Combine rewritten query + historical context for the embedding
    search_query = f"{raw_query} {search_query}"

    seen_ids: set[str] = set()
    docs: list[str] = []
    graph_doc: str = ""

    # 4a. Direct graph lookup - if the question mentions a specific job/dataset
    if G is not None:
        graph_doc = _graph_context(G, question)
        if graph_doc:
            docs.insert(0, graph_doc)
            seen_ids.add(graph_doc[:40])

    # 4b. General semantic search (more candidates for reranking)
    fetch_n = min(n_results * 2, 40)
    results = collection.query(query_texts=[f"query: {search_query}"], n_results=fetch_n)
    for doc, meta in zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
    ):
        key = meta.get("name", doc[:40])
        if key not in seen_ids:
            seen_ids.add(key)
            docs.append(doc)

    ns, name = _detect_filters(search_query, collection)

    # Exact dataset match -> prioritize at the top of context
    if name and name not in seen_ids:
        r = collection.get(where={"name": name}, include=["documents"])
        for doc in r.get("documents") or []:
            seen_ids.add(name)
            docs.insert(0, doc)
            break

    # Namespace match -> compact summary
    if ns:
        r = collection.get(
            where={"$and": [{"namespace": ns}, {"kind": "dataset"}]},
            include=["metadatas", "documents"],
        )
        ns_lines = [f"Datasets in {ns}:"]
        for doc, meta in zip(r.get("documents") or [], r.get("metadatas") or []):
            n = meta.get("name", "?")
            if n not in seen_ids:
                seen_ids.add(n)
                summary = "\n".join(
                    line
                    for line in doc.splitlines()
                    if line.startswith(("Dataset:", "Produced by", "Namespace:"))
                )
                ns_lines.append(summary)
        if len(ns_lines) > 1:
            docs.append("\n\n".join(ns_lines))

    if not docs:
        return "No relevant information found in the lineage index. Run 'sync' first."

    # 5. Reranking: filter to the most relevant docs with Haiku
    # graph_doc is always kept (exact node match) - never passed through reranker
    n_priority = 1 if graph_doc and docs and docs[0] == graph_doc else 0
    n_priority += 1 if name and len(docs) > n_priority else 0
    priority = docs[:n_priority]
    rest = docs[n_priority:]
    reranked_rest = _rerank_docs(question, rest, client, top_k=max(n_results - n_priority, 4))
    docs = priority + reranked_rest

    context = "\n\n---\n\n".join(docs)

    # 6. Build messages for Sonnet with history + RAG context
    api_messages: list[dict] = []
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    api_messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Contexto de linaje:\n{context}",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"Pregunta: {question}",
                },
            ],
        }
    )

    system_block = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    response = None
    for _ in range(4):  # max tool-use roundtrips
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_block,
            tools=_TOOLS,
            messages=api_messages,
        )

        if response.stop_reason != "tool_use":
            break

        # Append assistant turn and execute each tool call
        api_messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool_call(block.name, block.input, G, bucket, jobs_prefix)
                print(f"[tool] {block.name}({block.input}) -> {result[:80]}...")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        api_messages.append({"role": "user", "content": tool_results})

    if response is None:
        return ""
    block = next((b for b in response.content if b.type == "text"), None)
    return block.text if block else ""


# ── Análisis de impacto (grafo puro, sin LLM) ─────────────────────────────────


def impact_analysis(dataset_name: str, G: nx.DiGraph) -> None:
    matches = [
        k
        for k, d in G.nodes(data=True)
        if d.get("kind") == "dataset"
        and d.get("name", "").lower() == dataset_name.lower()
    ]

    if not matches:
        print(f"[!] Dataset '{dataset_name}' no encontrado en el grafo.")
        return

    for ds_key in matches:
        ds_name = G.nodes[ds_key].get("name", ds_key)
        print(f"\nAnálisis de impacto: {ds_name}")
        print("=" * 60)

        layers = _downstream_layers(G, ds_key)
        if not layers:
            print("  Sin dependencias downstream.")
            continue

        for depth, layer in enumerate(layers, start=1):
            print(f"\n  Nivel {depth}:")
            for kind, name in layer:
                tag = "[JOB]" if kind == "job" else "[DS] "
                print(f"    {tag} {name}")



# ── Sync ──────────────────────────────────────────────────────────────────────
def sync(
    events_path: str = EVENTS_PATH,
    bucket: str | None = None,
    events_prefix: str = "openlineage/parsed/",
    jobs_prefix: str = "glue/code/jobs/",
) -> tuple[nx.DiGraph, chromadb.Collection]:
    job_code: dict[str, str] = {}

    if bucket:
        print(f"[sync] Loading events from s3://{bucket}/{events_prefix} ...")
        events = load_events_s3(bucket, events_prefix)
        print(f"[sync] {len(events)} events loaded from S3")
        if jobs_prefix:
            print(f"[sync] Loading job code from s3://{bucket}/{jobs_prefix} ...")
            job_code = load_job_code_s3(bucket, jobs_prefix)
            print(f"[sync] {len(job_code)} .py files loaded from S3")
    else:
        print(f"[sync] Loading events from {events_path} ...")
        events = load_events(events_path)
        job_code = load_jobs_code(
            path=os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
            )
        )
        print(f"[sync] {len(events)} events loaded")

    G = build_graph(events)
    if job_code:
        from rag.ingest import enrich_graph_with_code
        enrich_graph_with_code(G, job_code)

    n_ds = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "dataset")
    n_job = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "job")
    print(f"[sync] Graph: {n_ds} datasets, {n_job} jobs, {G.number_of_edges()} edges")

    collection = build_index(G, job_code=job_code)
    print(f"[sync] ChromaDB index: {collection.count()} documents")

    return G, collection


def load_history(n: int = 5, chat_dir: str = CHAT_DIR) -> list[dict]:
    """Load the last n Q&A pairs from chat files as conversation history."""
    if not os.path.isdir(chat_dir):
        return []

    files = sorted(
        (f for f in os.listdir(chat_dir) if f.endswith(".md")),
        reverse=True,
    )

    pairs: list[tuple[str, str]] = []
    for fname in files:
        if len(pairs) >= n:
            break
        path = os.path.join(chat_dir, fname)
        with open(path) as f:
            content = f.read()

        entries = content.split("---\n\n")
        for entry in reversed(entries):
            if len(pairs) >= n:
                break
            m_q = re.search(r"\*\*Question:\*\* (.+)", entry)
            if not m_q:
                continue
            question = m_q.group(1).strip()
            after_q = entry[m_q.end():].strip()
            if after_q:
                pairs.append((question, after_q))

    history: list[dict] = []
    for question, answer in reversed(pairs):
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

    return history