#!/usr/bin/env bash
set -euo pipefail

# Baja solo los servicios RAG y limpia caché de ChromaDB
docker compose stop rag-api celery-worker rag-ui 2>/dev/null || true
docker compose rm -f rag-api celery-worker rag-ui 2>/dev/null || true

sudo rm -rf ./chroma_data 2>/dev/null || true

# Levanta solo lo necesario: redis + rag-api + celery-worker + rag-ui
# --build fuerza rebuild de imagen sin usar caché de Docker
docker compose up --build --no-deps redis rag-api celery-worker rag-ui
