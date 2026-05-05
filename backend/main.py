import os
import time
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from celery.result import AsyncResult

from backend.tasks import (
    S3_BUCKET,
    S3_EVENTS_PREFIX,
    S3_JOBS_PREFIX,
    celery_app,
    run_sync_task,
)
from rag.ingest import (
    build_graph,
    load_events,
)
from rag.tools.dataset import downstream_layers as _downstream_layers
from rag.query import ask, load_history, _downstream_layers
from rag.vectorize import get_collection, load_graph_cache

app = FastAPI(title="RAG Lineage API")


@app.on_event("startup")
def startup():
    threading.Thread(target=_ensure_loaded, daemon=True).start()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_state: dict = {"G": None, "collection": None, "loaded_at": 0.0, "filter_terms": None, "datasets_resp": None}
_load_lock = threading.Lock()
_last_reloaded_task: str | None = None

CHAT_DIR = "/app/chat"


def _ensure_loaded():
    if _state["collection"] is not None:
        return _state["G"], _state["collection"]

    with _load_lock:
        if _state["collection"] is not None:  # otro hilo cargó mientras esperábamos
            return _state["G"], _state["collection"]

        collection = get_collection()
        if collection.count() > 0:
            G = load_graph_cache()
            if G is not None:
                print(f"[ensure_loaded] Restored from cache — {G.number_of_nodes()} nodes, {collection.count()} docs in ChromaDB.")
            else:
                print("[ensure_loaded] ChromaDB has data but no graph cache — rebuilding from local events.")
                events = load_events()
                G = build_graph(events)
        else:
            print("[ensure_loaded] ChromaDB is empty. Run /api/sync to populate.")
            events = load_events()
            G = build_graph(events)

        _state.update({"G": G, "collection": collection, "loaded_at": time.time()})

        all_metas = collection.get(include=["metadatas"])["metadatas"] or []
        _state["filter_terms"] = {
            "namespaces": {str(v) for m in all_metas if (v := m.get("namespace"))},
            "names": {str(v) for m in all_metas if (v := m.get("name"))},
        }

        datasets = [
            {"key": k, "namespace": d.get("namespace", ""), "name": d.get("name", k)}
            for k, d in G.nodes(data=True)
            if d.get("kind") == "dataset"
        ]
        _state["datasets_resp"] = {
            "datasets": datasets,
            "namespaces": sorted({d["namespace"] for d in datasets if d["namespace"]}),
        }

    return _state["G"], _state["collection"]


def _save_chat(question: str, answer: str) -> None:
    os.makedirs(CHAT_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    path = os.path.join(CHAT_DIR, f"{today}.md")
    is_new = not os.path.exists(path)
    with open(path, "a") as f:
        if is_new:
            f.write(f"# Lineage chat - {today}\n\n")
        f.write(f"## {ts}\n\n")
        f.write(f"**Question:** {question}\n\n")
        f.write(f"{answer}\n\n")
        f.write("---\n\n")


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    question: str
    n: int = 20
    history: list[ChatMessage] = []


class ImpactRequest(BaseModel):
    dataset: str
    namespace: str | None = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def stats():
    try:
        G, collection = _state["G"], _state["collection"]
        n_ds = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "dataset")
        n_job = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "job")
        return {
            "datasets": n_ds,
            "jobs": n_job,
            "edges": G.number_of_edges(),
            "indexed_docs": collection.count(),
        }
    except Exception as e:
        return {
            "datasets": 0,
            "jobs": 0,
            "edges": 0,
            "indexed_docs": 0,
            "error": str(e),
        }


@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        history = [{"role": m.role, "content": m.content} for m in req.history]
        answer = ask(
            req.question,
            _state["collection"],
            n_results=req.n,
            history=history,
            G=_state["G"],
            bucket=S3_BUCKET,
            jobs_prefix=S3_JOBS_PREFIX,
            filter_terms=_state.get("filter_terms"),
        )
        _save_chat(req.question, answer)
        return {"answer": answer}
    except Exception as e:
        err = str(e)
        if "rate_limit_error" in err or "rate limit" in err.lower():
            raise HTTPException(
                status_code=429,
                detail="Límite de uso de la API alcanzado. Espera unos segundos e inténtalo de nuevo.",
            )
        raise HTTPException(status_code=500, detail=err)


@app.get("/api/datasets")
def list_datasets():
    if _state.get("datasets_resp"):
        return _state["datasets_resp"]
    try:
        G = _state["G"]
        datasets = []
        for key, data in G.nodes(data=True):
            if data.get("kind") == "dataset":
                datasets.append(
                    {
                        "key": key,
                        "namespace": data.get("namespace", ""),
                        "name": data.get("name", key),
                    }
                )
        namespaces = sorted({d["namespace"] for d in datasets if d["namespace"]})
        return {"datasets": datasets, "namespaces": namespaces}
    except Exception as e:
        return {"datasets": [], "namespaces": [], "error": str(e)}


@app.post("/api/impact")
def impact(req: ImpactRequest):
    G = _state["G"]
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not loaded yet.")

    matches = [
        k
        for k, d in G.nodes(data=True)
        if d.get("kind") == "dataset"
        and req.dataset.lower() in d.get("name", "").lower()
        and (
            not req.namespace or req.namespace.lower() in d.get("namespace", "").lower()
        )
    ]
    if not matches:
        return {
            "results": [],
            "message": f"Dataset '{req.dataset}' not found in the graph.",
        }

    results = []
    for ds_key in matches:
        ds_name = G.nodes[ds_key].get("name", ds_key)
        layers = _downstream_layers(G, ds_key)
        results.append(
            {
                "dataset": ds_name,
                "layers": [
                    [{"kind": kind, "name": name} for kind, name in layer]
                    for layer in layers
                ],
            }
        )
    return {"results": results}


@app.post("/api/sync")
def do_sync():
    try:
        task = run_sync_task.delay(
            bucket=S3_BUCKET,
            events_prefix=S3_EVENTS_PREFIX,
            jobs_prefix=S3_JOBS_PREFIX,
        )
        source = f"s3://{S3_BUCKET}/{S3_EVENTS_PREFIX}" if S3_BUCKET else "local"
        return {
            "task_id": task.id,
            "status": "PENDING",
            "message": f"Sync started from {source}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/task/{task_id}")
def task_status(task_id: str):
    global _last_reloaded_task
    result = AsyncResult(task_id, app=celery_app)
    data: dict = {"task_id": task_id, "status": result.state}
    if result.state == "SUCCESS":
        data["result"] = result.result
        should_reload = False
        with _load_lock:
            if _last_reloaded_task != task_id:
                _last_reloaded_task = task_id
                completed_at = (result.result or {}).get("completed_at", 0.0)
                already_fresh = _state["loaded_at"] >= completed_at > 0
                if already_fresh:
                    print(f"[task_status] task={task_id} SUCCESS — state already loaded after sync, skipping reload.")
                else:
                    print(f"[task_status] task={task_id} SUCCESS — scheduling reload.")
                    _state["G"] = None
                    _state["collection"] = None
                    _state["loaded_at"] = 0.0
                    _state["filter_terms"] = None
                    _state["datasets_resp"] = None
                    should_reload = True
            else:
                print(f"[task_status] task={task_id} SUCCESS (already processed) — skipping reload.")
        if should_reload:
            threading.Thread(target=_ensure_loaded, daemon=True, name=f"reload-{task_id[:8]}").start()
    elif result.state == "FAILURE":
        data["error"] = str(result.result)
        print(f"[task_status] task={task_id} FAILURE: {result.result}")
    return data


@app.get("/api/graph")
def graph():
    G = _state["G"]
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not loaded yet.")
    nodes = []
    for key, data in G.nodes(data=True):
        nodes.append({
            "id": key,
            "kind": data.get("kind", ""),
            "name": data.get("name", key),
            "namespace": data.get("namespace", ""),
            "has_code": bool(data.get("glue_code")),
            "has_column_lineage": bool(data.get("column_lineage")),
            "format": data.get("format", ""),
        })
    edges = []
    for src, dst, data in G.edges(data=True):
        edges.append({"source": src, "target": dst, "relation": data.get("relation", "")})
    return {"nodes": nodes, "edges": edges}


@app.get("/api/namespaces")
def namespaces():
    G = _state["G"]
    if G is None:
        return {"namespaces": []}
    ns = sorted({
        d.get("namespace", "")
        for _, d in G.nodes(data=True)
        if d.get("kind") == "dataset" and d.get("namespace")
    })
    return {"namespaces": ns}


@app.get("/api/tables")
def tables(namespace: str = ""):
    G = _state["G"]
    if G is None:
        return {"tables": []}
    result = sorted({
        d.get("name", k)
        for k, d in G.nodes(data=True)
        if d.get("kind") == "dataset"
        and (not namespace or d.get("namespace", "") == namespace)
    })
    return {"tables": result}


@app.get("/api/schema")
def schema(dataset: str, namespace: str | None = None):
    G = _state["G"]
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not loaded yet.")
    matches = [
        d for _, d in G.nodes(data=True)
        if d.get("kind") == "dataset"
        and d.get("name", "").lower() == dataset.lower()
        and (not namespace or d.get("namespace", "") == namespace)
    ]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found.")
    node = matches[0]
    columns = []
    for raw in node.get("schema", []):
        if " (" in raw and raw.endswith(")"):
            name, type_part = raw.rsplit(" (", 1)
            columns.append({"name": name, "type": type_part[:-1]})
        else:
            columns.append({"name": raw, "type": ""})
    return {
        "dataset": node.get("name"),
        "namespace": node.get("namespace"),
        "columns": columns,
    }


@app.get("/api/trace")
def trace(dataset: str, field: str | None = None, namespace: str | None = None):
    """
    Trace column-level lineage for a field in a dataset.
    Useful for GDPR audits: find the exact origin of a sensitive field.

    ?dataset=customers&field=email  -> recursive trace of email in customers
    ?dataset=customers              -> full column lineage for the dataset
    ?namespace=ns&dataset=customers -> scoped to a specific namespace
    """
    G = _state["G"]
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not loaded yet.")

    all_ds = [(k, d) for k, d in G.nodes(data=True) if d.get("kind") == "dataset"]
    if namespace:
        all_ds = [(k, d) for k, d in all_ds if d.get("namespace", "") == namespace]
    exact = [(k, d) for k, d in all_ds if d.get("name", "").lower() == dataset.lower()]
    matches = exact or [(k, d) for k, d in all_ds if dataset.lower() in d.get("name", "").lower()]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found.")

    def _trace_field(ds_name: str, out_field: str, visited: set, depth: int) -> dict:
        """Recursively trace a field back to its origins."""
        if depth > 6 or (ds_name, out_field) in visited:
            return {"field": out_field, "dataset": ds_name, "namespace": "", "sources": [], "cycle": depth > 6}
        visited.add((ds_name, out_field))

        src_node = next(
            (
                (k, d) for k, d in G.nodes(data=True)
                if d.get("kind") == "dataset" and d.get("name", "").lower() == ds_name.lower()
            ),
            None,
        )
        ns = src_node[1].get("namespace", "") if src_node else ""
        col_lineage = src_node[1].get("column_lineage", {}) if src_node else {}
        sources_meta = col_lineage.get(out_field, [])

        sources = []
        for s in sources_meta:
            child = _trace_field(s["table"], s["field"], visited, depth + 1)
            child["transform"] = s.get("type", "?")
            child["transform_subtype"] = s.get("subtype", "?")
            sources.append(child)

        return {"field": out_field, "dataset": ds_name, "namespace": ns, "sources": sources}

    results = []
    for node_key, data in matches:
        col_lineage = data.get("column_lineage", {})
        if not col_lineage:
            results.append({
                "dataset": data.get("name", node_key),
                "namespace": data.get("namespace", ""),
                "fields": [],
                "message": "No column lineage available for this dataset.",
            })
            continue

        fields_to_trace = [field] if field else list(col_lineage.keys())
        missing = [f for f in fields_to_trace if f not in col_lineage]
        if field and missing:
            raise HTTPException(
                status_code=404,
                detail=f"Field '{field}' not found in '{data.get('name')}'. "
                       f"Available fields: {', '.join(col_lineage.keys())}",
            )

        traced_fields = [
            _trace_field(data.get("name", ""), f, set(), 0)
            for f in fields_to_trace
        ]
        results.append({
            "dataset": data.get("name", node_key),
            "namespace": data.get("namespace", ""),
            "fields": traced_fields,
        })

    return {"results": results}


@app.get("/api/history")
def history(n: int = 20):
    msgs = load_history(n=n, chat_dir=CHAT_DIR)
    return {"messages": msgs}


@app.get("/api/config")
def config():
    return {
        "mode": "s3" if S3_BUCKET else "local",
        "bucket": S3_BUCKET,
        "events_prefix": S3_EVENTS_PREFIX if S3_BUCKET else None,
        "jobs_prefix": S3_JOBS_PREFIX if S3_BUCKET else None,
    }
