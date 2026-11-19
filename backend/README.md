# Clew backend (production directory)

The production backend for Clew: a single-process FastAPI + SQLite service for field-level data lineage verification and collaboration. The API contract in `docs/03_dev/05_api-reference.md` is the single source of truth; implementation notes live in `docs/03_dev/03_backend-development.md`; the architecture overview is in `docs/03_dev/01_architecture.md`.

## Relationship to prototype

- `prototype/backend/` is the M1–M4 prototype workspace. This directory is a **full port** of it (`src/`, `tests/`, `pyproject.toml` and `uv.lock` copied from the same source); after the port, the only code difference is how `.env` is located: the package sits at `backend/src/clew/`, so the repo root is 3 levels up (4 levels in the prototype). See `src/clew/config.py`.
- Both directories currently coexist; the prototype is kept for reference only, and future work proceeds in `backend/`.

## Development commands

```bash
cp .env.example .env             # repo-root config (SECRET_KEY / ADMIN_PASSWORD / LLM_* etc., never committed)
cd backend
uv sync                          # install dependencies (uv plays the role npm plays for the frontend; do not hand-write requirements.txt with pip)
uv run uvicorn clew.main:app --reload   # start on 127.0.0.1:8000 by default; creates the DB and initial admin on first run
uv run pytest                    # acceptance tests (54 cases, isolated temp data directory, no network)
uv run python -m clew.seed_demo          # demo data (idempotent): 5 datasets, a 4-hop lineage chain, and sample locators for all three source formats
```

All configuration (`SECRET_KEY` / `JWT_EXPIRE_HOURS` / `DATA_DIR` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `MAX_UPLOAD_MB` / `CORS_ORIGINS` / `LLM_*`) is injected from the repo-root `.env`; environment variables take precedence.

## Capabilities (M1–M4)

- **M1 data foundation**: JWT authentication + RBAC (viewer/editor/admin; roles are re-read from the database so changes take effect immediately), source-file hosting (sha256 content-addressed deduplication, controlled downloads), manifest import in CSV/XLSX/JSON (XLSX merged-cell/multi-level header locator resolution + real-file verification), version batches + change_log + per-batch rollback.
- **M2 graph queries**: a recursive CTE retrieves an N-hop subgraph in one query (dataset/field seeds, both/upstream/downstream), with a unified `GraphPayload` rendering contract; field-level source preview (locator highlighting + verification trace).
- **M3 editing and versions**: append-only annotations, field description/type/locator edits (locators are re-verified against the real file; on failure return 409 and keep the old value), lineage edge create/update/delete (`source='manual'`), change history, version-tag create/diff/rollback (idempotent; audit written to `rollback_record`).
- **M4 AI**: a read-only tool set (`search_fields` / `get_field_details` / `trace_lineage` / `get_field_history`) + OpenAI-compatible function-calling chat (stdlib urllib; 503 when no LLM is configured); heuristic lineage suggestions are stored with `source='ai'`, require human confirmation to become `manual`, and are deleted on rejection.

## Directory layout

```
backend/
├── pyproject.toml / uv.lock      # dependency declarations and lockfile (Python >=3.11, hatchling build)
├── src/clew/
│   ├── main.py / config.py / db.py / security.py / models.py
│   ├── manifest.py / locator.py / import_service.py    # import pipeline
│   ├── lineage.py / preview.py / changes.py / versioning.py
│   ├── seed_demo.py              # demo data (goes through the real upload + import path)
│   ├── ai/                       # llm / tools / suggest / chat
│   └── routes/                   # 12 route modules (auth/files/imports/datasets/lineage/preview/
│                                 #   annotations/fields/edges/changes/version_tags/ai)
└── tests/                        # 9 test files (pytest, isolated DATA_DIR)
```

Runtime data (`data/lineage.db` and `data/files/`) is created under `DATA_DIR` (default `./data`) and is gitignored; backup = back up the entire `DATA_DIR`.

## Known gaps (all require product decisions; not implemented)

- The user role-change endpoint (`PATCH /users/{username}`) is missing; user management only lists and creates users. This touches rules such as "can an admin change their own role" and "keep at least one admin" `[TBD-BIZ]`.
- The admin "delete dataset / reset import" capability (design plan §4.4) has no endpoint `[TBD-BIZ]`; cascade-delete semantics, audit approach, and interaction with rollback are undecided.
- Re-import overwrites `source` back to `imported` for existing edges; merge rules are pending `[TBD-BIZ]` (`docs/03_dev/03_backend-development.md` §12-7).
