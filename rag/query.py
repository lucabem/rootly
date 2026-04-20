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

SYSTEM_PROMPT = """\
Eres un asistente experto en linaje de datos para equipos de ETL y en consultas SQL sobre Amazon Athena. Respondes siempre en español, de forma concisa y estructurada.

Dispones de un contexto con:
- Datasets
- Pipelines (jobs) que leen/escriben
- Transformaciones SQL
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
- Aplica los siguientes filtros de origen según la fuente mencionada en la pregunta:
  - "siebel" → WHERE des_origen = 'SBL'
  - "delta mayorista" → WHERE des_origen = 'ESN'
  - "delta minorista" → WHERE des_origen = 'VTY'
- Si se mencionan varias fuentes, combínalas con OR o con UNION según corresponda.
- Si la pregunta pide un conteo (ej: "cuántos contratos"), usa COUNT(*) o COUNT(DISTINCT <campo_clave>).
- Añade siempre un comentario SQL encima de la query explicando qué hace.
- Si el schema no está disponible en el contexto, indica: "No se encontró el schema de la tabla en el contexto. Ejecuta 'sync' primero."
- Formato: bloque de código SQL.

### GENERAL
- Responde solo con información presente en el contexto.
- Si el contexto no tiene información relevante, responde: "No se encontró información relevante en el índice de linaje. Ejecuta 'sync' primero."

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
        if node.get("sql"):
            lines.append(f"SQL:\n{node['sql'].strip()}")

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

    # 4a. Direct graph lookup - if the question mentions a specific job/dataset
    if G is not None:
        graph_doc = _graph_context(G, question)
        if graph_doc:
            docs.insert(0, graph_doc)
            seen_ids.add(graph_doc[:40])

    # 4b. General semantic search (more candidates for reranking)
    fetch_n = min(n_results * 2, 40)
    results = collection.query(query_texts=[search_query], n_results=fetch_n)
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
    priority = docs[:1] if name and docs else []  # exact doc is always kept
    rest = docs[len(priority):]
    reranked_rest = _rerank_docs(question, rest, client, top_k=max(n_results - len(priority), 4))
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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=api_messages,
    )
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


def _downstream_layers(
    G: nx.DiGraph, start: str, max_depth: int = 6
) -> list[list[tuple]]:
    visited = {start}
    frontier = {start}
    layers = []

    for _ in range(max_depth):
        next_frontier: set[str] = set()
        layer: list[tuple] = []
        for node in frontier:
            for succ in G.successors(node):
                if succ not in visited:
                    visited.add(succ)
                    next_frontier.add(succ)
                    kind = G.nodes[succ].get("kind", "?")
                    name = G.nodes[succ].get("name", succ)
                    layer.append((kind, name))
        if not layer:
            break
        layers.append(layer)
        frontier = next_frontier

    return layers


# ── Sync ──────────────────────────────────────────────────────────────────────


def sync(
    events_path: str = EVENTS_PATH,
    bucket: str | None = None,
    events_prefix: str = "openlineage/parsed/",
    jobs_prefix: str = "glue/code/jobs/",
) -> tuple[nx.DiGraph, chromadb.Collection]:
    if bucket:
        print(f"[sync] Loading from s3://{bucket}/{events_prefix} ...")
        events = load_events_s3(bucket, events_prefix)
        print(f"[sync] {len(events)} events loaded from S3")
        events = [
            ev
            for ev in events
            if "execute_save_into_data_source_command"
            in ev.get("job", {}).get("name", "")
            and ev.get("eventType") == "COMPLETE"
            and len(ev.get("outputs", [])) > 0
            and len(ev.get("inputs", [])) > 0
        ]
        print(f"[sync] {len(events)} valid events after filtering")
        import json as _json

        os.makedirs(os.path.dirname(EVENTS_PATH), exist_ok=True)
        with open(EVENTS_PATH, "w") as _f:
            for _ev in events:
                _f.write(_json.dumps(_ev) + "\n")
        print(f"[sync] Events persisted to {EVENTS_PATH}")
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

    n_ds = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "dataset")
    n_job = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "job")
    print(f"[sync] Graph: {n_ds} datasets, {n_job} jobs, {G.number_of_edges()} edges")

    collection = build_index(G)
    print(f"[sync] ChromaDB index: {collection.count()} documents")

    return G, collection


def _load_existing_or_sync() -> tuple[nx.DiGraph, chromadb.Collection]:
    events = load_events()
    G = build_graph(events)
    collection = build_index(G)
    print(f"[info] Index updated: {collection.count()} documents")

    return G, collection


# ── Chat persistence ─────────────────────────────────────────────────────────


def _save_chat(question: str, answer: str, chat_dir: str = CHAT_DIR) -> None:
    os.makedirs(chat_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    path = os.path.join(chat_dir, f"{today}.md")

    is_new = not os.path.exists(path)
    with open(path, "a") as f:
        if is_new:
            f.write(f"# Lineage chat - {today}\n\n")
        f.write(f"## {ts}\n\n")
        f.write(f"**Question:** {question}\n\n")
        f.write(f"{answer}\n\n")
        f.write("---\n\n")

    print(f"\n[chat] Saved to {path}")


def _load_history(n: int = 5, chat_dir: str = CHAT_DIR) -> list[dict]:
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

        # Each entry is separated by "---\n\n" and contains **Question:** ...
        entries = content.split("---\n\n")
        for entry in reversed(entries):
            if len(pairs) >= n:
                break
            m_q = re.search(r"\*\*Question:\*\* (.+)", entry)
            if not m_q:
                continue
            question = m_q.group(1).strip()
            # The answer is everything after the question line
            after_q = entry[m_q.end():].strip()
            if after_q:
                pairs.append((question, after_q))

    history: list[dict] = []
    for question, answer in reversed(pairs):
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

    return history


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG over data lineage (OpenLineage + Claude)"
    )
    parser.add_argument("--bucket", help="S3 bucket (enables production mode)")
    parser.add_argument(
        "--events-prefix", default="openlineage/", help="S3 events prefix"
    )
    parser.add_argument(
        "--jobs-prefix", default="glue/code/jobs/", help="S3 Glue jobs prefix"
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Single natural language question")
    p_ask.add_argument("question", nargs="+", help="Question")
    p_ask.add_argument(
        "--n", type=int, default=20, help="Chunks to retrieve (default: 20)"
    )

    p_chat = sub.add_parser("chat", help="Interactive mode with persistent history")
    p_chat.add_argument(
        "--n", type=int, default=20, help="Chunks to retrieve (default: 20)"
    )
    p_chat.add_argument(
        "--history", type=int, default=5, metavar="K",
        help="Previous Q&A pairs to load as initial context (default: 5)"
    )

    p_impact = sub.add_parser("impact", help="Downstream impact analysis for a dataset")
    p_impact.add_argument("dataset", help="Dataset name (or partial name)")

    sub.add_parser("sync", help="Re-ingest and re-vectorize events")
    sub.add_parser("watch", help="Near real-time mode (file watcher or S3 polling)")

    args = parser.parse_args()

    if args.cmd == "sync":
        sync(
            bucket=args.bucket,
            events_prefix=args.events_prefix,
            jobs_prefix=args.jobs_prefix,
        )
        return

    if args.cmd == "watch":
        if args.bucket:
            from rag.watcher import start_watching_s3

            start_watching_s3(args.bucket, args.events_prefix, args.jobs_prefix)
        else:
            from rag.watcher import start_watching

            start_watching()
        return

    G, collection = _load_existing_or_sync()

    if args.cmd == "ask":
        question = " ".join(args.question)
        print(f"\nQuestion: {question}\n{'─'*60}")
        answer = ask(question, collection, n_results=args.n, G=G)
        print(answer)
        _save_chat(question, answer)

    elif args.cmd == "chat":
        history = _load_history(n=args.history)
        if history:
            print(f"[chat] {len(history) // 2} previous conversations loaded as context.")
        print("Interactive chat mode. Type 'exit' or press Ctrl+C to quit.\n")
        while True:
            try:
                question = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[chat] Session ended.")
                break
            if not question:
                continue
            if question.lower() in {"salir", "exit", "quit"}:
                print("[chat] Session ended.")
                break

            print(f"{'─'*60}")
            answer = ask(question, collection, n_results=args.n, history=history, G=G)
            print(f"\n{answer}\n")
            _save_chat(question, answer)

            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})

    elif args.cmd == "impact":
        impact_analysis(args.dataset, G)


if __name__ == "__main__":
    main()
