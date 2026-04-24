"""
rag/ingest.py
-------------
Reads OpenLineage events (.ndjson) and builds a lineage graph with NetworkX.

Node types:
  'dataset': namespace, name, format, schema, last_seen
  'job':     namespace, name, sql, runs (execution history)

Edges:
  dataset -> job  (relation="feeds")    - job reads from dataset
  job -> dataset  (relation="produces") - job writes to dataset
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import boto3

logger = logging.getLogger(__name__)

import networkx as nx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(BASE_DIR, "openlineage", "events.ndjson")


# ── Local loading ─────────────────────────────────────────────────────────────


def load_events(path: str = EVENTS_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_jobs_code(
    path: str = os.path.join(BASE_DIR, "glue", "code", "jobs")
) -> dict[str, str]:
    job_code = {}
    print(f"Loading job code from {path}...")
    if not os.path.exists(path):
        return job_code
    for fname in os.listdir(path):
        if fname.endswith(".py"):
            with open(os.path.join(path, fname)) as f:
                job_name = fname.removesuffix(".py")
                job_code[job_name] = f.read()
    return job_code


# ── S3 loading ────────────────────────────────────────────────────────────────


def load_events_s3(bucket: str, prefix: str = "openlineage/") -> list[dict]:
    """Read all .ndjson/.json files under the S3 prefix and return events.

    Only files modified today after 05:00 CEST (UTC+2) are downloaded.
    """
    CEST = timezone(timedelta(hours=2))
    now = datetime.now(tz=CEST)
    cutoff = now.replace(hour=5, minute=0, second=0, microsecond=0).astimezone(
        timezone.utc
    )

    s3 = boto3.client("s3")
    events: list[dict] = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not (key.endswith(".ndjson") or key.endswith(".json")):
                continue
            if obj["LastModified"] < cutoff:
                continue
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
            for line in body.splitlines():
                if line.strip():
                    events.append(json.loads(line))

    return events


def load_job_code_s3(bucket: str, prefix: str = "glue/code/jobs/") -> dict[str, str]:
    """Read Glue .py files from S3 and return {filename_without_ext: source_code}."""
    s3 = boto3.client("s3")
    job_code: dict[str, str] = {}

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".py"):
                continue
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
            job_name = os.path.basename(key).removesuffix(".py")
            job_code[job_name] = body

    return job_code


def _normalize_job_name(name: str) -> str:
    """job_alianzas_tnpi_dim_margen -> alianzas_tnpi_dim_margen
    ALIANZAS-tnpi_dim_margen    -> alianzas_tnpi_dim_margen"""
    name = name.lower().replace("-", "_")
    name = re.sub(r"^job_", "", name)
    return name


_SIMILARITY_THRESHOLD = 0.75


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def enrich_graph_with_code(G: nx.DiGraph, job_code: dict[str, str]) -> None:
    """Attach .py source code to each job node matched by name."""
    norm_index = {
        _normalize_job_name(fname): (fname, code) for fname, code in job_code.items()
    }
    logger.info(
        "enrich_graph_with_code: %d code files, %d graph nodes",
        len(norm_index),
        G.number_of_nodes(),
    )

    matched, unmatched = 0, 0
    for node_key, data in G.nodes(data=True):
        if data.get("kind") != "job":
            continue
        job_name = data.get("name", "")
        norm_job = _normalize_job_name(job_name)

        # 1) Exact normalized match
        match = norm_index.get(norm_job)
        if match:
            logger.debug("  [exact]  %s -> %s", norm_job, match[0])

        # 2) Suffix match (OL may add namespace/prefix)
        if match is None:
            match = next(
                (
                    v
                    for k, v in norm_index.items()
                    if norm_job.endswith(k) or k.endswith(norm_job)
                ),
                None,
            )
            if match:
                logger.debug("  [suffix] %s -> %s", norm_job, match[0])

        # 3) Best fuzzy match above threshold
        if match is None:
            best_score, best_val = 0.0, None
            for k, v in norm_index.items():
                score = _similarity(norm_job, k)
                if score > best_score:
                    best_score, best_val = score, v
            if best_score >= _SIMILARITY_THRESHOLD and best_val is not None:
                match = best_val
                logger.debug(
                    "  [fuzzy]  %s -> %s (score=%.2f)", norm_job, best_val[0], best_score
                )
            else:
                logger.warning(
                    "  [miss]   %s - best score=%.2f (threshold=%.2f)",
                    norm_job,
                    best_score,
                    _SIMILARITY_THRESHOLD,
                )

        if match:
            G.nodes[node_key]["glue_code"] = match[1]
            matched += 1
        else:
            unmatched += 1

    logger.info(
        "enrich_graph_with_code: %d jobs enriched, %d unmatched", matched, unmatched
    )


def build_graph(events: list[dict]) -> nx.DiGraph:
    G = nx.DiGraph()
    for ev in events:
        _process_event(G, ev)
    return G


def _process_event(G: nx.DiGraph, ev: dict) -> None:
    job = ev.get("job", {})
    job_name = job.get("name").split(".")[0]
    job_key = f"job::{job.get('namespace', '')}/{job_name}"
    event_type = ev.get("eventType", "")
    ts = ev.get("eventTime", "")

    if not G.has_node(job_key):
        G.add_node(
            job_key,
            kind="job",
            namespace=job.get("namespace", ""),
            name=job_name,
            sql="",
            runs=[],
        )

    if event_type and ts:
        G.nodes[job_key]["runs"].append({"type": event_type, "ts": ts})

    sql = _extract_sql(ev)
    if sql:
        G.nodes[job_key]["sql"] = sql

    for ds in ev.get("inputs", []):
        ds_key = _dataset_key(ds)
        _upsert_dataset(G, ds_key, ds)
        if not G.has_edge(ds_key, job_key):
            G.add_edge(ds_key, job_key, relation="feeds")

    for ds in ev.get("outputs", []):
        ds_key = _dataset_key(ds)
        _upsert_dataset(G, ds_key, ds)
        if not G.has_edge(job_key, ds_key):
            G.add_edge(job_key, ds_key, relation="produces")


def _parse_dataset_name(raw_name: str) -> tuple[str, str]:
    """Split '{prefix_db}/{db_name}/{table}' -> ('{prefix_db}_{db_name}', '{table}').

    Falls back to ('', raw_name) if the pattern doesn't match.
    """
    parts = raw_name.split("/")
    if len(parts) >= 3:
        return "_".join(parts[:-1]), parts[-1]
    return "", raw_name


def _dataset_key(ds: dict) -> str:
    namespace, name = _parse_dataset_name(ds.get("name", ""))
    return f"dataset::{namespace}/{name}"


def _upsert_dataset(G: nx.DiGraph, key: str, ds: dict) -> None:
    facets = ds.get("facets", {})
    schema = [
        f"{f['name']} ({f.get('type', '?')})"
        for f in facets.get("schema", {}).get("fields", [])
        if not f["name"].startswith("_hoodie_")
    ]
    namespace, name = _parse_dataset_name(ds.get("name", ""))
    fmt = _infer_format(name, facets)

    col_lineage = {
        out_field: [
            {
                "table": _parse_dataset_name(inp.get("name", ""))[1],
                "field": inp.get("field", "?"),
                "type": inp.get("transformations", [{}])[0].get("type", "?"),
                "subtype": inp.get("transformations", [{}])[0].get("subtype", "?"),
            }
            for inp in meta.get("inputFields", [])
        ]
        for out_field, meta in facets.get("columnLineage", {}).get("fields", {}).items()
    }

    if not G.has_node(key):
        G.add_node(
            key,
            kind="dataset",
            namespace=namespace,
            name=name,
            format=fmt,
            schema=schema,
            last_seen=None,
            column_lineage=col_lineage,
        )
    else:
        if schema:
            G.nodes[key]["schema"] = schema
        if fmt:
            G.nodes[key]["format"] = fmt
        if col_lineage:
            existing = G.nodes[key].get("column_lineage", {})
            merged = dict(existing)
            for field, sources in col_lineage.items():
                if field in merged:
                    seen = {(s["table"], s["field"]) for s in merged[field]}
                    merged[field] = merged[field] + [s for s in sources if (s["table"], s["field"]) not in seen]
                else:
                    merged[field] = sources
            G.nodes[key]["column_lineage"] = merged


def _extract_sql(ev: dict) -> str:
    return ev.get("job", {}).get("facets", {}).get("sql", {}).get("query", "")


def _infer_format(name: str, facets: dict) -> str:
    lower = name.lower()
    for fmt in ("hudi", "delta", "iceberg"):
        if fmt in lower:
            return fmt
    # Detect Hudi from _hoodie_* schema fields
    schema_fields = {f["name"] for f in facets.get("schema", {}).get("fields", [])}
    if any(f.startswith("_hoodie_") for f in schema_fields):
        return "hudi"
    # Extract from path if it follows the .../format/... pattern
    match = re.search(r"/(hudi|delta|iceberg)/", lower)
    return match.group(1) if match else "parquet"
