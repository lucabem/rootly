# examples/ - Spark pipelines

Three PySpark pipelines that demonstrate lineage capture with OpenLineage.
Each one reads source tables (Hudi / Delta) and writes the result to Iceberg,
automatically emitting lineage events.

---

## Requirements

- Python 3.11+ and Java 11/17 (local mode)
- Or Docker (no local installation needed)

Hudi, Delta, Iceberg, and OpenLineage JARs are downloaded automatically on
first run via Maven (~500 MB). With Docker they are pre-installed in the image.

---

## Setup (one-time)

Generate the source data first:

```bash
# With Docker
docker compose run --rm spark python generate_data.py

# Local
python generate_data.py
```

This creates:
- `data/hudi/orders/` - Hudi table with sample orders
- `data/delta/customers/` - Delta table with sample customers

---

## Running the pipelines

### With Docker (recommended)

```bash
docker compose run --rm spark python examples/01_hudi_to_iceberg.py
docker compose run --rm spark python examples/02_delta_to_iceberg.py
docker compose run --rm spark python examples/03_combined_pipeline.py
```

Events are sent to Marquez over HTTP (`OPENLINEAGE_URL=http://marquez:5000`).
View the lineage at http://localhost:3000 (namespace: `poc-openlineage`).

### Local

```bash
pip install -r requirements.txt

python examples/01_hudi_to_iceberg.py
python examples/02_delta_to_iceberg.py
python examples/03_combined_pipeline.py
```

In local mode, events are written to `openlineage/events.ndjson` (file transport).
To also send them to Marquez if it's running:

```bash
export OPENLINEAGE_URL=http://localhost:5000
python examples/03_combined_pipeline.py
```

---

## Pipelines

| Script | Reads | Writes | Iceberg dataset |
|--------|-------|--------|-----------------|
| `01_hudi_to_iceberg.py` | `data/hudi/orders` | Iceberg | `order_stats` |
| `02_delta_to_iceberg.py` | `data/delta/customers` | Iceberg | `customer_profiles` |
| `03_combined_pipeline.py` | `order_stats` + `customer_profiles` | Iceberg | `sales_summary` |

The resulting dependency graph:

```
orders (Hudi) ──► job_01 ──► order_stats (Iceberg) ──┐
                                                       ├──► job_03 ──► sales_summary (Iceberg)
customers (Delta) ──► job_02 ──► customer_profiles ───┘
```

---

## How the OpenLineage listener works

The `_spark_builder.py` helper auto-detects the environment:

```python
# OPENLINEAGE_URL set     -> HTTP transport (Marquez)
# OPENLINEAGE_URL not set -> file transport (events.ndjson)
```

The `OpenLineageSparkListener` intercepts the Spark execution plan and emits
events containing inputs, outputs, schema, SQL, and execution state.

---

## Inspecting the generated events

```bash
python inspect_lineage.py
```

Prints a human-readable summary of `openlineage/events.ndjson` to the terminal.
