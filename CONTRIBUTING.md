# Contributing to Rootly

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node 20+ (frontend)
- An `ANTHROPIC_API_KEY`

## Local setup

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY (and S3 vars if needed)
docker compose up --build
```

Without S3 access, the system runs against the sample events in `openlineage/` and `examples/`.

## Project layout

| Path | Responsibility |
|---|---|
| `rag/` | Ingestion, vectorization, RAG pipeline, tools |
| `backend/` | FastAPI app, Celery tasks |
| `frontend/src/` | React + TypeScript UI |
| `knowledge/` | Business docs indexed into ChromaDB |
| `conf/` | Domain/agent configuration YAML |

## Making changes

### Backend / RAG

1. Edit code under `rag/` or `backend/`.
2. Restart the backend container: `docker compose restart backend`.
3. Re-index if you changed ingestion or vectorization: `POST /api/sync` or `python -m rag.query sync`.

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server at http://localhost:5173
npm run build      # production build
```

### Adding a new RAG tool

1. Create `rag/tools/<tool_name>.py` and implement the handler.
2. Register it in `rag/tools/__init__.py` (add to `TOOLS` list and `execute_tool_call` dispatcher).
3. Add a row to the tools table in `CLAUDE.md`.

## Testing

```bash
# Quick smoke test against local events
python -m rag.query ask "¿Qué datasets existen?"

# Impact analysis
python -m rag.query impact <dataset_name>
```

There is no automated test suite yet. Manual verification against `examples/` data is the current approach.

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(rag): add reranking step to pipeline
fix(backend): avoid reload race on task completion
refactor(tools): extract S3 fetch helper
```

Scope is optional but encouraged (`rag`, `backend`, `frontend`, `tools`, `ingest`).

## Pull requests

- Branch from `main`, target `main`.
- One logical change per PR.
- Include a short description of *why*, not just what.
- If you change the RAG pipeline, note whether ChromaDB needs a full re-sync.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Claude API access |
| `S3_BUCKET` | no | — | Source of OpenLineage events and Glue job code |
| `S3_EVENTS_PREFIX` | no | `openlineage/` | S3 prefix for `.ndjson` event files |
| `S3_JOBS_PREFIX` | no | `code/glue/jobs/AEMET/` | S3 prefix for Glue `.py` files |
| `REDIS_URL` | no | `redis://redis:6379/0` | Celery broker |
