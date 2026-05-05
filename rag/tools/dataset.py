from __future__ import annotations

import os

import networkx as nx


def _schema_from_glue(dataset_name: str, database: str) -> str | None:
    """Try to fetch table schema from AWS Glue Data Catalog. Returns None on any error."""
    try:
        import boto3

        client = boto3.client("glue")
        resp = client.get_table(DatabaseName=database, Name=dataset_name)
        table = resp["Table"]
        sd = table.get("StorageDescriptor", {})
        columns = sd.get("Columns", [])
        partitions = table.get("PartitionKeys", [])

        if not columns and not partitions:
            return None

        lines = [f"Schema de {table['Name']} [{database}] (via Glue):"]
        for col in columns:
            comment = f"  # {col['Comment']}" if col.get("Comment") else ""
            lines.append(f"  - {col['Name']} ({col['Type']}){comment}")
        if partitions:
            lines.append("  Partition keys:")
            for col in partitions:
                lines.append(f"    - {col['Name']} ({col['Type']})")
        return "\n".join(lines)
    except Exception:
        return None


def _glue_database(namespace: str) -> str:
    """Resolve which Glue database to query: namespace hint → env vars → 'default'."""
    # If namespace looks like a plain name (not a URL), use it directly.
    if namespace and "://" not in namespace and "/" not in namespace:
        return namespace
    return os.environ.get("GLUE_DATABASE") or os.environ.get("ATHENA_DATABASE", "default")

SCHEMAS = [
    {
        "name": "get_dataset_schema",
        "description": (
            "Obtiene el schema completo (columnas y tipos) de un dataset, "
            "junto con su linaje de columnas si está disponible. "
            "Úsalo cuando el usuario pregunte por la estructura de una tabla "
            "y el schema no esté en el contexto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre del dataset o tabla",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace del dataset (opcional, para desambiguar)",
                },
            },
            "required": ["dataset_name"],
        },
    },
    {
        "name": "search_by_field",
        "description": (
            "Busca en qué datasets aparece una columna/campo concreto por nombre exacto. "
            "Úsalo para preguntas como '¿dónde está el campo email?', "
            "'¿qué tablas tienen contrato_id?', o auditorías GDPR de campos sensibles. "
            "Más preciso que la búsqueda semántica para nombres de columnas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field_name": {
                    "type": "string",
                    "description": "Nombre del campo/columna a buscar (substring, case-insensitive)",
                },
            },
            "required": ["field_name"],
        },
    },
    {
        "name": "get_downstream_impact",
        "description": (
            "Calcula el impacto downstream de un dataset: qué jobs y datasets se verían "
            "afectados si cambia su schema o se elimina. Devuelve el árbol de dependencias "
            "por niveles. Úsalo para preguntas de impacto ('¿qué rompe si cambio X?', "
            "'¿qué depende de Y?')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre del dataset del que calcular el impacto",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace del dataset (opcional, para desambiguar)",
                },
            },
            "required": ["dataset_name"],
        },
    },
    {
        "name": "get_column_lineage",
        "description": (
            "Devuelve el linaje de columnas de un dataset: para cada campo de salida, "
            "qué campos de entrada lo originan y el tipo de transformación. "
            "Úsalo para preguntas como '¿de dónde viene la columna X?', "
            "'¿qué campos alimentan Y?', '¿cómo se calcula Z?'. "
            "Más ligero que get_dataset_schema — no devuelve el schema completo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre del dataset",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace del dataset (opcional, para desambiguar)",
                },
                "field_name": {
                    "type": "string",
                    "description": "Filtrar por campo concreto (opcional)",
                },
            },
            "required": ["dataset_name"],
        },
    },
    {
        "name": "find_jobs_by_dataset",
        "description": (
            "Dado un dataset, devuelve qué jobs lo producen y qué jobs lo consumen. "
            "Úsalo para preguntas como '¿quién escribe en X?', '¿qué jobs leen de Y?', "
            "'¿cuál es el job productor de Z?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre del dataset",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace del dataset (opcional)",
                },
            },
            "required": ["dataset_name"],
        },
    },
]


def downstream_layers(G: nx.DiGraph, start: str, max_depth: int = 6) -> list[list[tuple]]:
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


def _find_dataset_matches(G: nx.DiGraph, dataset_name: str, namespace: str) -> list[tuple]:
    return [
        (key, data)
        for key, data in G.nodes(data=True)
        if data.get("kind") == "dataset"
        and dataset_name in data.get("name", "").lower()
        and (not namespace or namespace in data.get("namespace", "").lower())
    ]


def handle_schema(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    dataset_name = inputs.get("dataset_name", "").strip()
    namespace = inputs.get("namespace", "").strip().lower()
    if G:
        for _, data in G.nodes(data=True):
            if data.get("kind") != "dataset":
                continue
            if dataset_name.lower() not in data.get("name", "").lower():
                continue
            if namespace and namespace not in data.get("namespace", "").lower():
                continue
            schema = data.get("schema", [])
            col_lineage = data.get("column_lineage", {})
            if not schema and not col_lineage:
                glue_result = _schema_from_glue(data["name"], _glue_database(data.get("namespace", namespace)))
                if glue_result:
                    return glue_result
                return f"Dataset '{data['name']}' encontrado pero sin schema disponible en el índice ni en Glue."
            lines = [f"Schema de {data['name']} [{data.get('namespace', '')}]:"]
            for col in schema:
                lines.append(f"  - {col}")
            if col_lineage:
                lines.append("\nLinaje de columnas:")
                for field, sources in col_lineage.items():
                    src_str = ", ".join(f"{s['table']}.{s['field']}" for s in sources)
                    lines.append(f"  {field} ← {src_str}")
            return "\n".join(lines)

    glue_result = _schema_from_glue(dataset_name, _glue_database(namespace))
    if glue_result:
        return glue_result
    return f"No se encontró el dataset '{dataset_name}' en el índice ni en Glue. Ejecuta sync primero."


def handle_column_lineage(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    dataset_name = inputs.get("dataset_name", "").strip().lower()
    namespace = inputs.get("namespace", "").strip().lower()
    field_filter = inputs.get("field_name", "").strip().lower()
    if not G or not dataset_name:
        return "Parámetro dataset_name requerido."

    for _, data in G.nodes(data=True):
        if data.get("kind") != "dataset":
            continue
        if dataset_name not in data.get("name", "").lower():
            continue
        if namespace and namespace not in data.get("namespace", "").lower():
            continue

        col_lineage = data.get("column_lineage", {})
        if not col_lineage:
            return f"Dataset '{data['name']}' encontrado pero sin linaje de columnas disponible."

        lines = [f"Linaje de columnas de {data['name']} [{data.get('namespace', '')}]:"]
        for field, sources in col_lineage.items():
            if field_filter and field_filter not in field.lower():
                continue
            src_str = ", ".join(
                f"{s['table']}.{s['field']} [{s.get('type', '?')}/{s.get('subtype', '?')}]"
                for s in sources
            )
            lines.append(f"  {field} ← {src_str}")

        if len(lines) == 1:
            return f"No se encontró linaje para el campo '{field_filter}' en '{data['name']}'."
        return "\n".join(lines)

    return f"Dataset '{dataset_name}' no encontrado en el grafo."


def handle_search_field(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    field_name = inputs.get("field_name", "").strip().lower()
    if not G or not field_name:
        return "Parámetro field_name requerido."

    matches: list[str] = []
    for _, data in G.nodes(data=True):
        if data.get("kind") != "dataset":
            continue
        ds_name = data.get("name", "?")
        ns = data.get("namespace", "?")
        found_in: list[str] = []

        for col_entry in data.get("schema", []):
            col_name = col_entry.split("(")[0].strip().lower()
            if field_name in col_name:
                found_in.append(f"schema: {col_entry}")

        for out_field in data.get("column_lineage", {}):
            if field_name in out_field.lower() and f"schema: {out_field}" not in " ".join(found_in):
                found_in.append(f"lineage output: {out_field}")

        if found_in:
            matches.append(f"  {ds_name} [{ns}]:\n" + "\n".join(f"    - {f}" for f in found_in))

    if not matches:
        return f"No se encontró el campo '{field_name}' en ningún dataset del índice."
    return f"Datasets con campo '{field_name}' ({len(matches)} encontrados):\n\n" + "\n\n".join(matches)


def handle_impact(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    dataset_name = inputs.get("dataset_name", "").strip().lower()
    namespace = inputs.get("namespace", "").strip().lower()
    if not G or not dataset_name:
        return "Parámetro dataset_name requerido."

    ds_matches = _find_dataset_matches(G, dataset_name, namespace)
    if not ds_matches:
        return f"Dataset '{dataset_name}' no encontrado en el grafo."

    lines: list[str] = []
    for ds_key, ds_data in ds_matches:
        ds_label = f"{ds_data.get('name', ds_key)} [{ds_data.get('namespace', '')}]"
        layers = downstream_layers(G, ds_key)
        if not layers:
            lines.append(f"{ds_label}: sin dependencias downstream.")
            continue
        lines.append(f"Impacto downstream de {ds_label}:")
        for depth, layer in enumerate(layers, start=1):
            lines.append(f"  Nivel {depth}:")
            for kind, name in layer:
                tag = "[JOB]" if kind == "job" else "[DS] "
                lines.append(f"    {tag} {name}")

    return "\n".join(lines)


def handle_find_jobs(inputs: dict, G: nx.DiGraph | None, bucket: str | None, jobs_prefix: str) -> str:
    dataset_name = inputs.get("dataset_name", "").strip().lower()
    namespace = inputs.get("namespace", "").strip().lower()
    if not G or not dataset_name:
        return "Parámetro dataset_name requerido."

    ds_matches = _find_dataset_matches(G, dataset_name, namespace)
    if not ds_matches:
        return f"Dataset '{dataset_name}' no encontrado en el grafo."

    lines: list[str] = []
    for ds_key, ds_data in ds_matches:
        ds_label = f"{ds_data.get('name', ds_key)} [{ds_data.get('namespace', '')}]"
        producers = [
            G.nodes[src].get("name", src)
            for src in G.predecessors(ds_key)
            if G.nodes[src].get("kind") == "job"
        ]
        consumers = [
            G.nodes[tgt].get("name", tgt)
            for tgt in G.successors(ds_key)
            if G.nodes[tgt].get("kind") == "job"
        ]
        lines.append(f"Dataset: {ds_label}")
        if producers:
            lines.append(f"  Producido por ({len(producers)}):")
            for p in producers:
                lines.append(f"    - {p}")
        else:
            lines.append("  Producido por: ningún job registrado (dataset fuente)")
        if consumers:
            lines.append(f"  Consumido por ({len(consumers)}):")
            for c in consumers:
                lines.append(f"    - {c}")
        else:
            lines.append("  Consumido por: ningún job registrado (dataset terminal)")

    return "\n".join(lines)
