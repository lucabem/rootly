# backend/ - REST API (FastAPI + Celery)

HTTP service that exposes the RAG module as a REST API. Used by the frontend
and by the GitHub Actions lineage-impact workflow.

---

## Local setup

```bash
pip install -r backend/requirements.txt
pip install -r rag/requirements.txt   # RAG module dependency
```

You also need Redis running (for Celery):

```bash
# With Docker (simplest)
docker run -d -p 6379:6379 redis:7-alpine

# Or start only the RAG services from the repo root
bash run.sh
```

---

## Running

```bash
# From the repo root
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Celery worker (separate terminal)
celery -A backend.tasks worker --loglevel=info
```

API available at http://localhost:8000.
Interactive docs (Swagger): http://localhost:8000/docs.

---

## Endpoints

### Health and configuration

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Dataset, job, edge, and indexed document counts |
| GET | `/api/config` | Active mode (local / s3), bucket, and prefixes |

```bash
curl http://localhost:8000/api/health
# {"status": "ok"}

curl http://localhost:8000/api/stats
# {"datasets": 3, "jobs": 3, "edges": 6, "indexed_docs": 12}
```

### Graph data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/datasets` | List all datasets with their namespaces |
| GET | `/api/graph` | Full graph as nodes + edges (for the frontend) |
| GET | `/api/trace?dataset=X&field=Y` | Column-level lineage tracing (GDPR audits) |

```bash
curl http://localhost:8000/api/datasets

curl "http://localhost:8000/api/trace?dataset=sales_summary&field=total_amount"
```

### RAG (natural language)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Natural language question -> Claude answer |
| POST | `/api/impact` | Downstream impact analysis for a dataset |

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What pipelines depend on orders?", "n": 20}'
# {"answer": "...markdown response from Claude..."}

curl -X POST http://localhost:8000/api/impact \
  -H "Content-Type: application/json" \
  -d '{"dataset": "orders"}'
# {"results": [{"dataset": "orders", "layers": [[...]]}]}
```

### Async sync

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sync` | Start a background re-indexing task (Celery) |
| GET | `/api/task/{task_id}` | Check task status |

```bash
# Trigger sync
curl -X POST http://localhost:8000/api/sync
# {"task_id": "abc123", "status": "PENDING"}

# Poll status
curl http://localhost:8000/api/task/abc123
# {"task_id": "abc123", "status": "SUCCESS", "result": {"docs": 12, "datasets": 3, "jobs": 3}}
```

---

## Environment variables

Same as the RAG module (read from `.env` at the repo root):

```
ANTHROPIC_API_KEY=sk-ant-...
REDIS_URL=redis://localhost:6379/0   # default if not set
S3_BUCKET=                           # production mode only
S3_EVENTS_PREFIX=openlineage/
S3_JOBS_PREFIX=glue/code/jobs/
```

---

## With Docker

The root `docker-compose.yml` already manages `rag-api` (FastAPI on :8000)
and `celery-worker`. To rebuild only these services:

```bash
docker compose up -d --build rag-api celery-worker
```
