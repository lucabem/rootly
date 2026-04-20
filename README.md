# OpenLineage POC - Spark + Hudi + Delta + Iceberg + RAG

Proof of concept that captures data lineage with OpenLineage when Spark
reads **Hudi** and **Delta** tables and writes results to **Iceberg**,
then exposes that lineage as a knowledge base queryable in natural language
(RAG + Claude).

```
data/hudi/orders       ──┐
                          ├──► Spark SQL ──► iceberg/<table>
data/delta/customers   ──┘
                               ↓
                   OpenLineage events -> Marquez UI
                               ↓
                   rag/ -> ChromaDB + Claude (Sonnet)
                               ↓
            "What breaks if I change orders?" -> answer
```

---

## Prerequisites

| Tool | Min version | Required for |
|------|-------------|--------------|
| Docker + Docker Compose | Any recent version | Option A (recommended) |
| Python | 3.11+ | Options B and C |
| Java | 11 or 17 | Option B (local Spark) |
| Node.js | 20+ | Frontend in dev mode |

---

## Environment setup

```bash
cp .env.example .env
```

Edit `.env` and fill in at least:

```
ANTHROPIC_API_KEY=sk-ant-...   # required for the RAG module
```

For S3 / production mode, also add your AWS credentials.

---

## Option A - Full Docker stack (recommended)

No need to install Java or PySpark locally.

```bash
# 1. Build and start the full stack
docker compose up -d --build

# Marquez takes ~30 s to initialize; wait for:
docker compose logs -f marquez   # until you see "Started Application"
```

```bash
# 2. Generate source data (Hudi + Delta)
docker compose run --rm spark python generate_data.py
```

```bash
# 3. Run Spark pipelines (in order)
docker compose run --rm spark python examples/01_hudi_to_iceberg.py
docker compose run --rm spark python examples/02_delta_to_iceberg.py
docker compose run --rm spark python examples/03_combined_pipeline.py
```

The scripts detect `OPENLINEAGE_URL=http://marquez:5000` and send events
directly to Marquez over HTTP.

```bash
# 4. Open the UIs
open http://localhost:3000    # Marquez - namespace: poc-openlineage
open http://localhost:8080    # RAG UI (chat, impact, graph, tasks)
open http://localhost:19120   # Nessie catalog
open http://localhost:3001    # Grafana
```

### RAG services only (no Spark or Marquez)

```bash
bash run.sh
```

Starts only Redis, RAG-API, Celery worker, and RAG-UI. Useful when you
already have events indexed and just want to use the chat.

---

## Option B - Local execution (no Docker)

Requires Python 3.11+ and Java 11/17.

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r rag/requirements.txt
pip install -r backend/requirements.txt

# Generate data and run pipelines
python generate_data.py
python examples/01_hudi_to_iceberg.py
python examples/02_delta_to_iceberg.py
python examples/03_combined_pipeline.py

# Inspect generated events in the terminal
python inspect_lineage.py
```

In local mode, events are written to `openlineage/events.ndjson`.
To also send them to Marquez (if it's running):

```bash
export OPENLINEAGE_URL=http://localhost:5000
python examples/03_combined_pipeline.py
```

---

## Option C - RAG module only (no Spark)

If you already have events in `openlineage/events.ndjson` or in S3:

```bash
pip install -r rag/requirements.txt

# Index and query (local mode)
python -m rag.query sync
python -m rag.query ask "What pipelines depend on orders?"
python -m rag.query chat            # interactive mode with history

# Impact analysis without LLM
python -m rag.query impact orders

# Near real-time (re-indexes when changes are detected)
python -m rag.query watch
```

See [rag/README.md](rag/README.md) for full module documentation.

---

## Services and ports

| Service | URL | Description |
|---------|-----|-------------|
| Marquez UI | http://localhost:3000 | Lineage visualization (namespace: poc-openlineage) |
| Marquez API | http://localhost:5000 | OpenLineage HTTP API |
| RAG UI | http://localhost:8080 | Chat, impact, graph, tasks |
| RAG API | http://localhost:8000 | REST API (see [backend/README.md](backend/README.md)) |
| Nessie | http://localhost:19120 | Iceberg catalog |
| Grafana | http://localhost:3001 | Dashboards (admin/admin) |
| Redis | localhost:6379 | Celery broker (internal) |

---

## Project structure

```
.
├── Dockerfile                  # Spark image with pre-installed JARs
├── docker-compose.yml          # Full stack (7 services)
├── run.sh                      # Starts RAG services only
├── generate_data.py            # Creates sample Hudi and Delta tables
├── inspect_lineage.py          # Prints events.ndjson summary to terminal
├── requirements.txt            # PySpark, jsonlines
├── .env.example                # Environment variables template
├── conf/                       # Marquez and Grafana configuration
├── examples/                   # Spark pipelines (see examples/README.md)
├── rag/                        # RAG module (see rag/README.md)
├── backend/                    # FastAPI + Celery API (see backend/README.md)
├── frontend/                   # React + Vite UI (see frontend/README.md)
├── data/                       # Source Hudi/Delta tables (generated, git-ignored)
├── openlineage/                # .ndjson events and Iceberg warehouse (git-ignored)
└── chat/                       # Conversation history (git-ignored)
```

---

## Component versions

| Component | Version |
|-----------|---------|
| PySpark | 3.5.3 |
| Apache Hudi | 0.15.0 |
| Delta Lake | 3.2.0 |
| Apache Iceberg | 1.6.1 |
| OpenLineage Spark | 1.43.0 |
| Marquez | 0.47.0 |
| ChromaDB | ≥ 0.5.0 |
| Anthropic SDK | ≥ 0.40.0 |
| Python | 3.11+ |
| Node.js | 20+ |

---

## GitHub Actions

The `.github/workflows/lineage-impact.yml` workflow automatically analyzes
the impact of PRs that modify Glue jobs (`glue/code/jobs/**/*.py`) and posts
a comment listing the affected downstream datasets.

Requires the `LINEAGE_API_URL` secret pointing to your deployed RAG API.
