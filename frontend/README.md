# frontend/ - React + Vite + TypeScript UI

Web interface for querying the data lineage graph. Communicates with the
backend API at `http://localhost:8000`.

---

## Requirements

- Node.js 20+
- Backend running on port 8000 (see [backend/README.md](../backend/README.md))

---

## Local development

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Changes hot-reload automatically.

Vite proxies `/api/*` to the backend at `http://localhost:8000`,
so no CORS configuration or URL changes are needed.

---

## Production build

```bash
npm run build    # outputs to dist/
npm run preview  # serves dist/ locally on :4173
```

In Docker the build is served through Nginx on port 8080:

```bash
# From the repo root
docker compose up -d --build rag-ui
open http://localhost:8080
```

---

## Features

### Chat
Ask the assistant questions about the lineage graph in natural language.
Responses are rendered as Markdown. Session history is persisted in
`localStorage`.

### Impact
Select a dataset (with autocomplete) and see which downstream jobs and
datasets are affected, organized by dependency layer.

### Graph
Interactive visualization of the full lineage graph using React Flow.
Dataset and job nodes can be freely dragged and explored.

### Tasks
Monitor background sync operations. Shows status (PENDING / STARTED /
SUCCESS / FAILURE) and results (indexed docs, datasets, jobs). Polls
automatically every 3 s while tasks are active.

### Sync button
In the header. Triggers an async re-indexing of the graph and reflects
progress in the Tasks tab.

---

## Structure

```
src/
├── App.tsx              # Main component with the 4 tabs
├── App.css              # Styles
├── main.tsx             # React DOM entry point
└── components/
    ├── Autocomplete.tsx # Input with dataset/namespace suggestions
    └── GraphView.tsx    # React Flow graph visualization
```

---

## Environment variables (optional)

Create a `frontend/.env.local` file to override the backend URL:

```
VITE_API_URL=http://my-api.example.com
```

Defaults to `/api` (proxied to `http://localhost:8000` by Vite).
