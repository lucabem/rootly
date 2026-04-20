# rag/ - Natural language lineage query module

Converts OpenLineage events into a NetworkX graph, vectorizes it into
ChromaDB, and exposes a CLI to ask questions in natural language about
datasets, ETL jobs, SQL transformations, and dependencies.

---

## Installation

```bash
pip install -r rag/requirements.txt
```

Make sure `ANTHROPIC_API_KEY` is set in your `.env` (or exported):

```bash
cp .env.example .env   # from the repo root
# edit .env and fill in ANTHROPIC_API_KEY
```

---

## Quick start

```bash
# 1. Index events (required on first run and after new pipelines)
python -m rag.query sync

# 2. Ask a single question in natural language
python -m rag.query ask "What pipelines depend on the orders table?"
python -m rag.query ask "What is the schema of customer_profiles?"
python -m rag.query ask "What breaks if I change orders?"

# 3. Interactive chat mode (keeps session history)
python -m rag.query chat

# 4. Direct graph impact analysis (no LLM, faster)
python -m rag.query impact orders

# 5. Near real-time: re-indexes automatically when changes are detected
python -m rag.query watch
```

Every question is automatically saved to `chat/YYYY-MM-DD.md`.

---

## Interactive chat mode

```bash
python -m rag.query chat
# [chat] 5 previous conversations loaded as context.
# Interactive chat mode. Type 'exit' or press Ctrl+C to quit.
#
# You: What tables are in the publication namespace?
# ──────────────────────────────────────────────────────────
# ...Claude's answer...
#
# You: exit
```

Options:

```bash
# Load more or fewer previous conversations (default: 5)
python -m rag.query chat --history 10

# Adjust the number of chunks retrieved from the index
python -m rag.query chat --n 30
```

---

## Production mode (S3 + AWS Glue)

When events and job code are stored in S3:

```bash
# Index from S3
python -m rag.query --bucket my-bucket sync

# Ask with enriched context (includes Glue source code)
python -m rag.query --bucket my-bucket ask "What ETL jobs write to sales_summary?"

# Interactive chat over S3
python -m rag.query --bucket my-bucket chat

# Near real-time: S3 polling every 30 s
python -m rag.query --bucket my-bucket watch

# Custom S3 prefixes
python -m rag.query \
  --bucket my-bucket \
  --events-prefix data/lineage/ \
  --jobs-prefix glue/code/jobs/ \
  sync
```

S3 environment variables (in `.env`):

```
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=        # only for temporary STS credentials
AWS_DEFAULT_REGION=eu-west-1
S3_BUCKET=your-bucket
S3_EVENTS_PREFIX=openlineage/
S3_JOBS_PREFIX=glue/code/jobs/
```

---

## Command reference

```
python -m rag.query [--bucket BUCKET] [--events-prefix PREFIX] [--jobs-prefix PREFIX] <cmd>

Subcommands:
  sync              Re-ingest events and re-vectorize into ChromaDB
  ask "question"    Single natural language question
    --n N             Chunks to retrieve (default: 20)
  chat              Interactive session with history
    --n N             Chunks to retrieve (default: 20)
    --history K       Previous Q&A pairs to load as context (default: 5)
  impact DATASET    Downstream impact analysis (no LLM)
  watch             Near real-time: re-indexes when changes are detected
```

---

## Internal architecture

```
OpenLineage events (.ndjson or S3)
  + Glue job code (S3 glue/code/jobs/*.py)
             │
             ▼
        ingest.py
   Builds NetworkX DiGraph:
   dataset ──► job ──► dataset
             │
             ▼
       vectorize.py
   Serializes each node as text
   + transitive impact chains
   -> ChromaDB (rag/.chroma/)
             │
        ┌────┴────┐
        ▼         ▼
   query.py    watcher.py
  CLI / RAG    Near real-time
```

### Indexed chunk types

| Type | Content |
|------|---------|
| Dataset | Name, namespace, format, schema, producer and consumer jobs, column lineage |
| Job | Inputs, outputs, SQL transformation, execution history, Glue source code |
| Impact chain | Transitive dependencies dataset -> job -> dataset for propagation analysis |

### Question classification

The system prompt classifies each question before answering:

| Type | Triggered when |
|------|----------------|
| `SCHEMA` | Questions about columns or data types |
| `LIST TABLES` | "What tables are there?", "list all datasets" |
| `IMPACT` | "What breaks if...?", "What depends on...?" |
| `COLUMN LINEAGE` | "Where does field X come from?" |
| `GENERAL` | Any other query about the graph |

---

## Generated files

| Path | Description |
|------|-------------|
| `rag/.chroma/` | ChromaDB vector index (git-ignored) |
| `chat/YYYY-MM-DD.md` | Conversation history (git-ignored) |
