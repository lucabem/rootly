# Rootly — RAG Lineage Assistant

Sistema de linaje de datos con RAG + Claude. Permite consultar en lenguaje natural qué datasets existen, qué jobs los producen/consumen, su schema, impacto de cambios y código fuente de jobs Glue.

## Stack

- **Backend**: FastAPI + Celery + Redis (Docker)
- **RAG**: ChromaDB (embeddings locales) + Claude Sonnet (respuestas) + Claude Haiku (rewrite + rerank)
- **Fuente de datos**: OpenLineage events en S3 (`.ndjson`) + código Glue `.py` en S3
- **Frontend**: React + TypeScript (`frontend/src/`)
- **Modelo principal**: `claude-sonnet-4-6` — **Haiku** (`claude-haiku-4-5-20251001`) para tareas auxiliares baratas

## Variables de entorno clave

```
ANTHROPIC_API_KEY
S3_BUCKET
S3_EVENTS_PREFIX   # default: "openlineage/"
S3_JOBS_PREFIX     # default: "code/glue/jobs/AEMET/"
REDIS_URL          # default: "redis://redis:6379/0"
```

## Estructura de ficheros

```
rag/
  ingest.py      # carga eventos S3/local, construye grafo NetworkX
  vectorize.py   # serializa grafo → ChromaDB
  query.py       # pipeline RAG completo + agentic loop
  knowledge.py   # carga docs de negocio (.md, .xlsx) → chunks
  watcher.py     # modo near real-time (watchdog local / S3 polling)
backend/
  main.py        # FastAPI endpoints
  tasks.py       # Celery task para sync asíncrono
frontend/
  src/components/GraphView.tsx   # visualización del grafo
chroma_data/     # ChromaDB persistido (volumen Docker)
chat/            # historial de conversaciones en .md por día
knowledge/       # documentos de negocio indexables (.md, .xlsx)
```

## Flujo de datos

```
S3 events (.ndjson)
      ↓ ingest.py: load_events_s3()
NetworkX DiGraph (nodes: dataset | job)
      ↓ ingest.py: enrich_graph_with_code()  ← solo en sync completo, NO en startup
      ↓ vectorize.py: build_index()
ChromaDB "lineage" collection
      ↓ query.py: ask()
Claude Sonnet → respuesta
```

## Startup del backend (`main.py: _ensure_loaded`)

1. Carga eventos desde disco local (`openlineage/events.ndjson`)
2. Construye el grafo sin código de jobs (startup rápido, lazy load)
3. Si ChromaDB ya tiene datos → reutiliza el índice persistido (NO llama `build_index`)
4. Si ChromaDB está vacío → descarga job code de S3 + enriquece grafo + construye índice

**El código de jobs NO se descarga en startup para no bloquear.** Se descarga on-demand via tool use cuando Claude lo necesita.

## Pipeline RAG — `query.py: ask()`

Parámetros relevantes: `question`, `collection`, `n_results=20`, `history`, `G` (grafo), `bucket`, `jobs_prefix`

### Pasos en orden

1. **`_is_list_query`** — si la pregunta es de inventario ("listar", "todos"...) aumenta `n_results` a 40
2. **`_rewrite_query`** — llama a Haiku para reescribir la pregunta como query semántica óptima (sinónimos, términos técnicos ETL). Combina con contexto histórico reciente
3. **`_graph_context`** — busca en el grafo NetworkX el nodo mencionado por nombre (match substring, prioriza el más largo). Serializa el subgrafo: inputs/outputs, schema, SQL, estadísticas de ejecución. Si hay `glue_code` y es code query → incluye código; si no → añade `"Código fuente disponible: xxx.py"` como señal para la tool
4. **ChromaDB query** — recupera `n_results * 2` candidatos con embedding semántico
5. **Filtros exactos** — si detectó dataset/namespace concreto, los prioriza al principio del contexto
6. **`_rerank_docs`** — Haiku filtra y reordena los docs por relevancia (hasta top_k=8). Los docs prioritarios (match exacto) nunca se reordenan
7. **Agentic loop** (hasta 4 iteraciones):
   - Claude recibe contexto + tools disponibles
   - Si `stop_reason == "tool_use"` → ejecuta `_execute_tool_call` → devuelve resultado → siguiente iteración
   - Si `stop_reason == "end_turn"` → respuesta final

### Tools disponibles (agentic loop)

**`get_job_code(job_name)`**
- Busca primero en el grafo en memoria (nodo con `glue_code`)
- Si no está → `fetch_single_job_code_s3(bucket, jobs_prefix, job_name)`: lista S3, busca por nombre exacto / sufijo / fuzzy (threshold 0.75), descarga el `.py`
- Cachea en el nodo del grafo para no volver a S3 en la misma sesión

**`get_dataset_schema(dataset_name, namespace?)`**
- Busca en el grafo por nombre (substring) + namespace opcional
- Devuelve schema (columnas+tipos) + linaje de columnas

### Detección de filtros — `_detect_filters`

Descarga todos los metadatos de ChromaDB y compara contra la pregunta por:
1. Substring exacto (`"contratos" in question`)
2. Tokens (`re.split(r"[\s_\-/]+")`) — captura referencias parciales
Prioriza términos más largos (más específicos). Devuelve `(namespace, dataset_name)`.

## `ingest.py` — construcción del grafo

- **`load_events_s3`**: solo descarga ficheros modificados hoy después de las 05:00 CEST
- **`build_graph`**: procesa eventos OpenLineage. Nodos: `job` (con runs, SQL) y `dataset` (con schema, column_lineage, format). Edges: `dataset→job` (feeds) y `job→dataset` (produces)
- **`enrich_graph_with_code`**: matchea ficheros `.py` contra nodos job por nombre normalizado (exacto → sufijo → fuzzy). Adjunta `glue_code` al nodo
- **`fetch_single_job_code_s3`**: descarga un único `.py` de S3 para lazy load on-demand

### Normalización de nombres de job

`_normalize_job_name`: convierte a lowercase, reemplaza `-` por `_`, elimina prefijo `job_`. Así `"job_alianzas-tnpi"` → `"alianzas_tnpi"`.

## `vectorize.py` — ChromaDB

- **`CHROMA_DIR`**: `rag/.chroma` (mapeado como volumen Docker a `chroma_data/`)
- **`get_collection`**: `get_or_create_collection("lineage")` — reutiliza si existe
- **`build_index`**: borra colección existente + crea nueva (genera nuevo UUID). Serializa todos los nodos del grafo + "impact chains" para datasets raíz
- Cada sync genera un nuevo UUID en `chroma_data/` — los directorios viejos son huérfanos y se pueden borrar

## `knowledge.py` — docs de negocio

Carga ficheros `.md` y `.xlsx` del directorio `knowledge/`. Los `.md` se parten por secciones `##`. Los `.xlsx` se parten por sheet y bloques de 60 filas. Se indexan en ChromaDB con `kind="knowledge"`.

## `watcher.py` — near real-time

- **`start_watching`**: watchdog sobre `events.ndjson` local. Re-indexa en cada modificación (incremental: solo lee líneas nuevas)
- **`start_watching_s3`**: polling cada 30s comparando ETags de objetos S3. Re-indexa si hay cambios

## Sync asíncrono — `backend/tasks.py`

Celery task `run_sync_task`: llama a `rag.query.sync()` en background. El endpoint `/api/sync` lo dispara y devuelve `task_id`. El frontend puede hacer polling a `/api/task/{task_id}` para ver el estado. Cuando termina (`SUCCESS`), el backend resetea `_state` y recarga el grafo.

## Endpoints API relevantes

| Endpoint | Descripción |
|---|---|
| `POST /api/chat` | Pregunta RAG. Recibe `question`, `history[]`, `n` |
| `POST /api/sync` | Lanza sync asíncrono desde S3 |
| `GET /api/task/{id}` | Estado de la tarea Celery |
| `GET /api/datasets` | Lista todos los datasets del grafo |
| `POST /api/impact` | Análisis de impacto downstream |
| `GET /api/graph` | Todos los nodos y edges del grafo |
| `GET /api/trace` | Linaje de columna recursivo |
| `GET /api/stats` | Número de datasets, jobs, edges, docs |

## Decisiones de diseño importantes

- **Lazy load de código**: el código `.py` de jobs NO se descarga al arrancar. Solo cuando Claude llama la tool `get_job_code`. Esto evita descargar cientos de ficheros innecesarios
- **Graph lookup primero**: antes de buscar en ChromaDB, se hace lookup directo en el grafo NetworkX. Más preciso para preguntas con nombre específico
- **Reranking con Haiku**: se recuperan el doble de docs necesarios y Haiku filtra. Así el recall del embedding no limita la calidad final
- **Cache en prompt**: `SYSTEM_PROMPT` y el contexto de linaje usan `cache_control: ephemeral` para prompt caching de Anthropic
- **Match exacto en GraphView**: los filtros de dataset/job en el frontend usan `===` (no `includes`) para evitar falsos positivos (ej: "contratos" no debe mostrar "contratos_viejo")
