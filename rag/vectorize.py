"""
rag/vectorize.py
----------------
Serializes the lineage graph into text chunks and embeds them into ChromaDB.

Each graph node produces one document. Additionally, for each source dataset
(root node with no producer job) an "impact chain" chunk is generated
describing transitive downstream dependencies.
"""

import os

import chromadb
import networkx as nx

CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chroma")


def get_collection(persist_dir: str = CHROMA_DIR) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection("lineage")


def build_index(
    G: nx.DiGraph, persist_dir: str = CHROMA_DIR, job_code: dict | None = None
) -> chromadb.Collection:
    """
    job_code: dict {job_name: source_code} from load_job_code_s3().
              If provided, enriches job chunks with Glue source code.
    """
    client = chromadb.PersistentClient(path=persist_dir)
    try:
        client.delete_collection("lineage")
    except Exception:
        pass
    collection = client.create_collection("lineage")
    docs, ids, metas = [], [], []

    for node_key in G.nodes:
        text = _serialize_node(G, node_key, job_code or {})
        if not text:
            continue
        node = G.nodes[node_key]
        docs.append(text)
        ids.append(node_key)
        metas.append(
            {
                "kind": node.get("kind", ""),
                "name": node.get("name", ""),
                "namespace": node.get("namespace", ""),
            }
        )

    # Impact chain chunks for source datasets (no producer job = graph root)
    for ds_key, data in G.nodes(data=True):
        if data.get("kind") != "dataset":
            continue
        if any(G.nodes[src].get("kind") == "job" for src in G.predecessors(ds_key)):
            continue  # not a source - it's the output of some job
        chain_text = _serialize_impact_chain(G, ds_key)
        if chain_text:
            chain_id = f"impact::{ds_key}"
            docs.append(chain_text)
            ids.append(chain_id)
            metas.append({"kind": "impact_chain", "name": data.get("name", ""), "namespace": ""})

    if docs:
        collection.upsert(documents=docs, ids=ids, metadatas=metas)

    return collection


# ── Serializers ───────────────────────────────────────────────────────────────


def _serialize_node(G: nx.DiGraph, key: str, job_code: dict) -> str:
    node = G.nodes[key]
    kind = node.get("kind", "")
    if kind == "dataset":
        return _serialize_dataset(G, key, node)
    if kind == "job":
        return _serialize_job(G, key, node, job_code)
    return ""


def _serialize_dataset(G: nx.DiGraph, key: str, node: dict) -> str:
    name = node.get("name", "?")
    ns = node.get("namespace", "?")
    fmt = node.get("format", "unknown")
    schema = node.get("schema", [])

    producers = [
        G.nodes[src].get("name", src)
        for src in G.predecessors(key)
        if G.nodes[src].get("kind") == "job"
    ]
    consumers = [
        G.nodes[tgt].get("name", tgt)
        for tgt in G.successors(key)
        if G.nodes[tgt].get("kind") == "job"
    ]

    col_lineage: dict = node.get("column_lineage", {})

    lines = [
        f"Dataset: {name}",
        f"Namespace: {ns}",
        f"Format: {fmt}",
    ]
    if schema:
        lines.append(f"Schema: {', '.join(schema)}")
    if producers:
        lines.append(f"Produced by jobs: {', '.join(producers)}")
    if consumers:
        lines.append(f"Consumed by jobs: {', '.join(consumers)}")
    if col_lineage:
        col_lines = []
        for out_field, inputs in col_lineage.items():
            srcs = ", ".join(
                f"{inp['table']}.{inp['field']} [{inp['type']}/{inp['subtype']}]"
                for inp in inputs
            )
            col_lines.append(f"  {out_field} ← {srcs}")
        lines.append("Column lineage:\n" + "\n".join(col_lines))

    return "\n".join(lines)


def _serialize_job(G: nx.DiGraph, key: str, node: dict, job_code: dict) -> str:
    name = node.get("name", "?")
    ns = node.get("namespace", "?")
    sql = node.get("sql", "")
    runs = node.get("runs", [])

    inputs = [
        G.nodes[src].get("name", src)
        for src in G.predecessors(key)
        if G.nodes[src].get("kind") == "dataset"
    ]
    outputs = [
        G.nodes[tgt].get("name", tgt)
        for tgt in G.successors(key)
        if G.nodes[tgt].get("kind") == "dataset"
    ]

    n_complete = sum(1 for r in runs if r["type"] == "COMPLETE")
    n_fail = sum(1 for r in runs if r["type"] == "FAIL")
    last_run = runs[-1] if runs else None

    # Glue code: from the node (enriched by enrich_graph_with_code) or direct dict lookup
    glue_code = (
        node.get("glue_code")
        or job_code.get(name)
        or next((code for fname, code in job_code.items() if fname in name), None)
    )

    lines = [
        f"Job (ETL pipeline): {name}",
        f"Namespace: {ns}",
        f"Reads from (inputs): {', '.join(inputs) if inputs else 'none'}",
        f"Writes to (outputs): {', '.join(outputs) if outputs else 'none'}",
        f"Executions: {n_complete} successful, {n_fail} failed",
    ]
    if last_run:
        lines.append(f"Last event: {last_run['type']} at {last_run['ts']}")
    if sql:
        lines.append(f"SQL transformation:\n{sql.strip()}")

    # if glue_code:
    #     lines.append(f"Glue source code:\n{glue_code}")

    return "\n".join(lines)


def _serialize_impact_chain(G: nx.DiGraph, ds_key: str) -> str:
    ds_name = G.nodes[ds_key].get("name", ds_key)
    chains = []

    for job_key in G.successors(ds_key):
        if G.nodes[job_key].get("kind") != "job":
            continue
        job_name = G.nodes[job_key].get("name", job_key)
        for out_key in G.successors(job_key):
            if G.nodes[out_key].get("kind") != "dataset":
                continue
            out_name = G.nodes[out_key].get("name", out_key)
            chains.append(f"  -> job '{job_name}' -> dataset '{out_name}'")

    if not chains:
        return ""

    lines = [
        f"Impact chain for dataset: {ds_name}",
        f"If '{ds_name}' changes schema or is deleted, the following are affected:",
    ] + chains
    return "\n".join(lines)
