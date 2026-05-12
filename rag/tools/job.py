from __future__ import annotations

import re
import networkx as nx

_MAX_CODE_LINES = 4_000_000


def _format_code(code: str, job_name: str) -> str:
    """Return code snippet with SQL blocks surfaced, capped at _MAX_CODE_LINES."""
    lines = code.splitlines()
    if len(lines) <= _MAX_CODE_LINES:
        return f"Código fuente de {job_name}.py:\n```python\n{code.strip()}\n```"

    header = "\n".join(lines[:_MAX_CODE_LINES])

    # Collect SQL string literals so they're not lost in the truncation
    sql_hits = []
    for i, line in enumerate(lines[_MAX_CODE_LINES:], start=_MAX_CODE_LINES):
        if re.search(r'\.sql\s*\(|spark\.sql|SparkSQL|executeQuery', line, re.IGNORECASE):
            block = lines[i : min(i + 20, len(lines))]
            sql_hits.append("\n".join(block))
            if len(sql_hits) >= 2:
                break

    extra = ""
    if sql_hits:
        extra = "\n\n# --- SQL encontrado fuera del fragmento ---\n" + "\n\n".join(sql_hits)

    return (
        f"Código fuente de {job_name}.py "
        f"(primeras {_MAX_CODE_LINES} de {len(lines)} líneas{', + SQL' if sql_hits else ''}):\n"
        f"```python\n{header}{extra}\n```\n"
        "⚠️ Código truncado. Pregunta por una sección específica si necesitas más."
    )

SCHEMA = {
    "name": "get_job_code",
    "description": (
        "Obtiene el código fuente Python (.py) de un Glue job. "
        "Úsalo cuando el contexto mencione 'Código fuente disponible: xxx.py' "
        "o cuando el usuario pregunte por la lógica/implementación de un job."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "job_name": {
                "type": "string",
                "description": "Nombre del job (sin extensión .py)",
            }
        },
        "required": ["job_name"],
    },
}


def handle(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    job_name = inputs.get("job_name", "").strip()

    if G:
        for node_key, data in G.nodes(data=True):
            if data.get("kind") != "job" or data.get("name", "").lower() != job_name.lower():
                continue

            if data.get("glue_code"):
                return _format_code(data["glue_code"], job_name)

            if data.get("glue_code_s3_key") and bucket:
                try:
                    import boto3
                    code = boto3.client("s3").get_object(
                        Bucket=bucket, Key=data["glue_code_s3_key"]
                    )["Body"].read().decode()
                    G.nodes[node_key]["glue_code"] = code
                    return _format_code(code, job_name)
                except Exception as exc:
                    return f"Error al cargar {job_name}.py desde S3: {exc}"

    if bucket:
        try:
            from rag.ingest import fetch_single_job_code_s3
            code = fetch_single_job_code_s3(bucket, jobs_prefix, job_name)
            if code:
                if G:
                    for node_key, data in G.nodes(data=True):
                        if data.get("kind") == "job" and data.get("name", "").lower() == job_name.lower():
                            G.nodes[node_key]["glue_code"] = code
                return _format_code(code, job_name)
        except Exception as exc:
            return f"Error al cargar {job_name}.py desde S3: {exc}"

    return f"No se encontró el código fuente de '{job_name}'. Comprueba el nombre o ejecuta sync."
