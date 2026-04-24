from __future__ import annotations

import networkx as nx

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
        for _, data in G.nodes(data=True):
            if data.get("kind") == "job" and data.get("name", "").lower() == job_name.lower():
                if data.get("glue_code"):
                    return f"Código fuente de {job_name}.py:\n```python\n{data['glue_code'].strip()}\n```"

    if bucket:
        try:
            from rag.ingest import fetch_single_job_code_s3
            code = fetch_single_job_code_s3(bucket, jobs_prefix, job_name)
            if code:
                if G:
                    for key, data in G.nodes(data=True):
                        if data.get("kind") == "job" and data.get("name", "").lower() == job_name.lower():
                            G.nodes[key]["glue_code"] = code
                return f"Código fuente de {job_name}.py:\n```python\n{code.strip()}\n```"
        except Exception as exc:
            return f"Error al cargar {job_name}.py desde S3: {exc}"

    return f"No se encontró el código fuente de '{job_name}'. Comprueba el nombre o ejecuta sync."
