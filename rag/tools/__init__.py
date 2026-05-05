from __future__ import annotations

import networkx as nx

from rag.tools.job import SCHEMA as _job_schema
from rag.tools.job import handle as _handle_job
from rag.tools.dataset import SCHEMAS as _dataset_schemas
from rag.tools.dataset import (
    handle_schema,
    handle_column_lineage,
    handle_search_field,
    handle_impact,
    handle_find_jobs,
)
from rag.tools.athena import SCHEMA as _athena_schema
from rag.tools.athena import handle as _handle_athena

TOOLS: list[dict] = [_job_schema, *_dataset_schemas, _athena_schema]

_DISPATCH: dict[str, callable] = {
    "get_job_code": _handle_job,
    "get_dataset_schema": handle_schema,
    "get_column_lineage": handle_column_lineage,
    "search_by_field": handle_search_field,
    "get_downstream_impact": handle_impact,
    "find_jobs_by_dataset": handle_find_jobs,
    "run_athena_query": _handle_athena,
}


def execute_tool_call(
    name: str,
    inputs: dict,
    G: nx.DiGraph | None,
    bucket: str | None,
    jobs_prefix: str,
) -> str:
    handler = _DISPATCH.get(name)
    if not handler:
        return f"Herramienta desconocida: {name}"
    return handler(inputs, G, bucket, jobs_prefix)
