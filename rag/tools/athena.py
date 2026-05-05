from __future__ import annotations

import os
import time

SCHEMA = {
    "name": "run_athena_query",
    "description": (
        "Ejecuta una query SQL contra Amazon Athena y devuelve los resultados. "
        "Úsalo cuando el usuario pida datos reales de una tabla, quiera contar registros, "
        "hacer un sample, o verificar valores concretos que no están en el índice RAG. "
        "Las queries deben ser SELECT (no DDL/DML destructivo)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query SQL a ejecutar en Athena (solo SELECT)",
            },
            "database": {
                "type": "string",
                "description": (
                    "Base de datos / glue catalog database. "
                    "Si se omite, usa la variable de entorno ATHENA_DATABASE."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": "Número máximo de filas a devolver (default 50, máximo 200)",
            },
        },
        "required": ["query"],
    },
}

_POLL_INTERVAL = 1.5
_MAX_WAIT = 120


def handle(inputs: dict, G, bucket: str | None, jobs_prefix: str) -> str:
    import boto3

    query: str = inputs.get("query", "").strip()
    if not query:
        return "Parámetro 'query' requerido."

    # Skip leading SQL comments (-- line and /* block */) before checking the verb.
    import re as _re
    stripped = _re.sub(r"(--[^\n]*\n?|/\*.*?\*/)", "", query, flags=_re.DOTALL).strip()
    first_word = stripped.split()[0].upper() if stripped.split() else ""
    if first_word not in {"SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH"}:
        return f"Solo se permiten queries de lectura (SELECT/SHOW/DESCRIBE). Recibido: '{first_word}'."

    database = inputs.get("database") or os.environ.get("ATHENA_DATABASE", "default")
    max_rows = min(int(inputs.get("max_rows") or 50), 200)

    output_prefix = os.environ.get("ATHENA_OUTPUT_PREFIX", "athena-results")
    if not bucket:
        bucket = os.environ.get("S3_BUCKET", "")
    if not bucket:
        return "No se puede determinar el bucket S3 para los resultados de Athena. Define S3_BUCKET."
    output_location = f"s3://{bucket}/{output_prefix.strip('/')}/"

    workgroup = os.environ.get("ATHENA_WORKGROUP", "primary")

    try:
        client = boto3.client("athena", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        resp = client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": output_location},
            WorkGroup=workgroup,
        )
        execution_id = resp["QueryExecutionId"]

        # Poll until done or timeout.
        elapsed = 0.0
        while elapsed < _MAX_WAIT:
            status_resp = client.get_query_execution(QueryExecutionId=execution_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in {"SUCCEEDED"}:
                break
            if state in {"FAILED", "CANCELLED"}:
                reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "")
                return f"Query {state} en Athena: {reason}"
            time.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
        else:
            return f"Timeout ({_MAX_WAIT}s) esperando resultados de Athena (execution_id={execution_id})."

        result_resp = client.get_query_results(
            QueryExecutionId=execution_id,
            MaxResults=max_rows + 1,
        )
        rows = result_resp["ResultSet"]["Rows"]
        if not rows:
            return "Query ejecutada con éxito pero sin resultados."

        headers = [c.get("VarCharValue", "") for c in rows[0]["Data"]]
        data_rows = rows[1 : max_rows + 1]

        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in data_rows:
            values = [c.get("VarCharValue", "") for c in row["Data"]]
            lines.append("| " + " | ".join(values) + " |")

        total_returned = len(data_rows)
        summary = f"\n({total_returned} fila(s) devueltas, database={database})"
        return "\n".join(lines) + summary

    except Exception as exc:
        return f"Error ejecutando query en Athena: {exc}"
