# Clew

A field-level AI data lineage tool (named **Clew** as of 2026-10, meaning "ball of thread / clue" — the word clue derives from clew: the thread that leads you out of the maze; formerly working name LineageLite).

> Clew — field-level data lineage, visualized. Follow the thread out of the data maze.

Based on source-code research into two open-source lineage solutions (OpenMetadata and DataHub), we design a lightweight solution for small teams: **field-level lineage + precise source file locator with verification against the actual file + versioning + AI assistance**.

> This file is the detailed project description (formerly the repository root README). For the product showcase home, see [README](../README.md) (English by default) · [README.zh](../README.zh.md) (Chinese).
> Note: the structure and wording of the original README are preserved below; for details on M5 (LangChain, SSE streaming, description drafts, in-conversation suggestions, MCP), see the root README and the [AI Module Evolution Plan](./03_dev/07_ai-module-evolution-plan.md).
> Unless otherwise noted, the commands below are run from the repository root.

## Documentation Navigation

All design documents and prototypes are organized under [`docs/`](./README.md) (see [docs/README.md](./README.md) for the reading order and the document-to-code mapping):

| Document | Contents |
|---|---|
| [Design Plan](./01_design/clew-design-proposal.md) | Overall technical design: research findings on the two open-source solutions, import format specification, storage and version management (since 2026-11: SQLite source of truth + Kùzu lineage graph dual database), system-level lineage (§4.7), visualization, AI chat, milestones, confirmed decision records |
| [Business Model](./01_design/clew-business-model.md) | Business-layer model: positioning and value proposition, stakeholders and roles, core domain concepts (including systems), business processes, business rules and invariants |
| [Data Model](./01_design/clew-data-model.md) | Data-layer model: ER diagram, definitions for 13 SQLite business tables + graph_state, derived views (including v_system_edge), JSON structures, identifier naming rules, index and version rebuild rules, §10 Kùzu graph schema (including System/LINEAGE_SYSTEM) and dual-write consistency |
| [Lo-fi Prototype](./02_prototype/clew-lofi-prototype.html) | Wireframe prototype of 6 screens (open directly in a browser; the confirmed UI baseline) |
| [Hi-fi Clickable Prototype](./02_prototype/clew-hifi-prototype.html) | Demo accompanying the 2026-11 dual-database plan: mock data, 7 interactive screens (lineage canvas/source preview/import/AI chat/versions/RBAC/architecture overview) |
| [System-Level Lineage Prototype](./02_prototype/clew-system-lineage-prototype.html) | Accompanying the 2026-11 system-level lineage design: system/dataset/field three-level views, explicit and projected edges, evidence drill-down; AI assistant drawer (system-level tool calls, graph linking, suggested edge confirmation; see [04_hifi/07](./04_hifi/07_system-level-ai-assistant.md) for the interaction design) |

## Directory Structure

```
clew/
├── backend/       # Official backend project (ported from prototype/backend): M1 data foundation + M2 graph query/source preview + M3 editing/annotation/version tags + M4 AI (FastAPI + SQLite + uv)
│   ├── src/clew/
│   ├── tests/
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/      # Official frontend project (ported from prototype/frontend): hi-fi visuals + import wizard (React + TS + Vite + Tailwind + @xyflow/react)
│   ├── src/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── vite.config.ts
├── docs/          # Design documents (01_design), lo-fi prototype (02_prototype), development documents (03_dev), hi-fi spec (04_hifi); see docs/README.md for the index
├── scripts/demo/  # Scripts for preparing README demo data and recording with Playwright (GIF generation)
├── prototype/     # Prototype workspace (historical baseline for backend/frontend), kept for reference only; future features evolve in backend/ and frontend/
├── README.md      # Product showcase home (English by default)
├── README.zh.md   # Product showcase home (Chinese)
└── .env.example   # Environment configuration template (copy to the repository root .env; .env is not committed)
```

The development server of the official frontend `frontend/` uses the Vite proxy to forward `/auth`, `/datasets`, `/lineage`, `/fields`, `/edges`, `/annotations`, `/changes`, `/version-tags`, `/users`, `/files`, `/import`, `/ai` to `http://127.0.0.1:8000`.

## Backend (M1-M4 Implemented)

Data foundation: JWT authentication + RBAC (admin/editor/viewer), source file hosting (sha256 deduplication), import of three formats CSV/XLSX/JSON (including locator parsing for merged cells and multi-level headers in XLSX, plus verification against the actual file), version batches + change_log + rollback by batch.

M3 editing and versions: annotation (append-only), editing of field description/type/locator (locator re-verified against the actual file), create/update/delete of lineage edges (manual edges source='manual'), change history, business tag creation/list/diff/rollback (rollback is idempotent; audit written to rollback_record).

M4 AI: read-only toolset (`search_fields` / `get_field_details` / `trace_lineage` / `get_field_history`) + OpenAI-compatible function calling chat; when no LLM is configured, `/ai/status` returns `configured=false` and `/ai/chat` returns 503. Heuristic lineage suggestions generate candidate edges from same-name fields (0.7) / containment relationships (0.6), persisted with `source='ai'`; they must be manually confirmed before becoming `manual`, and rejection deletes the candidate edge.

```bash
cp .env.example .env           # Repository root configuration (SECRET_KEY / ADMIN_PASSWORD, etc.)
cd backend
uv sync                        # Install dependencies
uv run uvicorn clew.main:app --reload   # Start; the database and initial admin are created automatically on first run
uv run pytest                  # Run acceptance tests
```

API overview (Bearer Token required): `POST /auth/login`, `POST/GET /users` (admin), `POST/GET /files`, `GET /files/{id}/download`, `POST /import` (editor+, multipart: format + source_file_ids + manifest file), `GET /import/batches`, `POST /import/batches/{id}/rollback` (admin), `GET /datasets`, `GET /lineage/subgraph?dataset=&field=&hops=&direction=`, `GET /fields/{dataset_id}/{field_name}/preview`; M3: `POST/GET /annotations`, `PATCH /fields/{dataset_id}/{field_name}`, `POST /edges`, `PATCH/DELETE /edges/{id}`, `GET /changes`, `POST/GET /version-tags`, `GET /version-tags/diff?from=&to=`, `POST /version-tags/{name}/rollback` (admin); M4: `GET /ai/status`, `POST /ai/chat` (viewer+), `POST /ai/suggest`, `POST /ai/suggest/confirm`, `POST /ai/suggest/reject` (editor+).

If you need demo data, run `uv run python -m clew.seed_demo` in the backend directory to generate 5 datasets, a 4-hop lineage chain, and csv/xlsx/json source preview samples.

## Frontend (M4)

Field-level lineage canvas: dataset filtering, dagre left-to-right layered layout, field-level/table-level connections, node field collapsing and "box-select collapse into group", hop count switching, field details and CSV/XLSX/JSON source preview.

M3 editing and versions: write entry points hidden by login role (viewer is read-only); hover/select an edge to edit its transformation and notes, or delete it; drag field/table-level handles to add lineage; field description/type/locator editing (409 reason displayed); append-only annotation of fields and edges; field/edge change history drawer; version drawer (import batches, tag creation, diffs between tags, admin rollback); admin user management. Login uses JWT; the Bearer Token is stored in `localStorage`, and any authenticated request returning 401 sends the user back to the login page.

M4 AI assistant: "AI assistant" drawer in the top bar (conversation, tool call trace, `trace_lineage` results linked to the graph); one-click generation of heuristic candidate edges inside field details; any edge with `source='ai'` on the canvas can be "confirmed as a manual edge" from its edge details, regardless of whether the candidate card is still in memory.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173; the API is proxied to :8000 by Vite
npm run build      # tsc -b && vite build
```

The frontend accesses the API using only `fetch`; the canvas relies on `@xyflow/react` and the layered layout on `@dagrejs/dagre`.

Frontend/backend integration testing: after starting the backend, run `node scripts/api-e2e.mjs` (or `E2E_BASE_URL=http://127.0.0.1:8001 node scripts/api-e2e.mjs`), which mirrors every request in `src/lib/api.ts` for end-to-end validation (including RBAC/error semantics); it writes data with the `e2e_` prefix and automatically rolls back the parts that can be rolled back.

## Known Gaps

- **User management prototype fidelity**: the current `UserManagementModal` only supports a user list + adding users (including role selection at creation); the per-row role dropdown and RBAC permission matrix from the prototype "Versions and Users" screen are not yet implemented. Changing roles requires a new admin endpoint and involves business rules such as "whether admins may change their own role / how to guarantee at least one admin remains" (`[TBD-BIZ]`, to be confirmed by the product owner before implementation); the UI explicitly notes this limitation.
- **Annotation management**: annotations are append-only and currently have no edit/delete entry point (consistent with the business model).

## Referenced Repositories

`OpenMetadata/` and `datahub/` are source copies of the two open-source projects used for research; they are for local reference only and are **not version-controlled in this repository** (see `.gitignore`).

## Demo Assets and Recording

The feature GIFs in the README live in [`docs/assets/demo/`](./assets/demo/) and are recorded by scripts in this repository against a separate demo database:

```bash
# Terminal 1: prepare the English demo database (5 datasets, 4-hop lineage chain) and start a separate backend
cd backend
DATA_DIR=/tmp/clew-demo/data uv run python ../scripts/demo/seed_demo_en.py
DATA_DIR=/tmp/clew-demo/data uv run uvicorn clew.main:app --port 8010

# Terminal 2 (repository root): start the frontend, proxying the API to the demo backend
cd frontend && VITE_API_TARGET=http://127.0.0.1:8010 npx vite --port 5199

# Terminal 3: install recording dependencies, record segment by segment and convert to GIF
cd scripts/demo
npm install
npm run setup      # Write annotations, change history and version tags through the API
npm run record     # One WebM per feature (.work/video)
npm run gifs       # Playwright ffmpeg frame extraction + Pillow palette + gifsicle
```

`record-demo.mjs` outputs WebM segment by segment; `build-gifs.sh` handles transcoding and compression. The import segment must be recorded against a fresh demo database.

## Tech Stack

- Backend: Python + FastAPI + uv, starting with SQLite (a Postgres upgrade path is reserved)
- Frontend: React + TypeScript + Vite + Tailwind + @xyflow/react + @dagrejs/dagre (component sources vendored, no additional UI component library)
- AI: OpenAI-compatible Chat API + function calling (keys configured via `.env`, never committed)
