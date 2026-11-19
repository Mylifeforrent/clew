# Clew Backend Development Document

> Purpose: an **implementation guide** for backend developers describing the current state of `prototype/backend/` — tech stack, module responsibilities, configuration, database, authentication, import pipeline, version rollback, AI module, error conventions, testing, and operations. The content is based on the M1–M4 prototype code and the design documents under `docs/01_design/`; for the architecture overview see [./01_architecture.md](./01_architecture.md), for API endpoint details see [./05_api-reference.md](./05_api-reference.md) (not covered here), and for the frontend/backend split see [./04_frontend-backend-boundaries.md](./04_frontend-backend-boundaries.md).

---

## 0. Basis and Sources

The facts in this document come only from the following materials; conflicts are resolved by the priority "data model → design plan → business model" (`docs/README.md` maintenance convention):

| Basis | Use |
|---|---|
| [docs/01_design/clew-data-model.md](../01_design/clew-data-model.md) (hereinafter the "data model") | Table definitions, derived views, JSON structures, naming rules, indexes, version rebuild rules, API contract increments in §9 — the most important basis for the backend |
| [docs/01_design/clew-design-proposal.md](../01_design/clew-design-proposal.md) (hereinafter the "design plan") | §3 import format spec, §4 storage and version management, §6 AI chat, §7 human correction and annotation |
| Root [README.md](../../README.md) | Backend section, startup commands, API overview |
| `prototype/backend/pyproject.toml` + `uv.lock` | Dependency and version declarations |
| All modules under `prototype/backend/src/lineagelite/` | Implementation facts (all references in this document are repository-relative paths) |
| `prototype/backend/tests/` | Test domains and isolation mechanisms |

Known inconsistencies between design documents and code, and code behavior not covered by the documents, are listed together in [§12](#12-known-differences-and-notes); the rest of this document follows the current code.

---

## 1. Tech Stack and Dependencies

The backend is a Python + FastAPI single-process application, starting with SQLite (a Postgres upgrade path is reserved; see §4). Package management uniformly uses **uv** (hand-written `requirements.txt` with pip is prohibited); the build backend is hatchling (the wheel only packages `src/clew`).

Python version requirement: **`>=3.11`** (`pyproject.toml` `requires-python`; the code uses 3.11 features such as `datetime.UTC` and `zip(..., strict=True)`).

Runtime dependencies (declared in `prototype/backend/pyproject.toml`; locked resolved versions come from `prototype/backend/uv.lock`):

| Dependency | Declared version | Locked version | Use |
|---|---|---|---|
| fastapi | >=0.115 | 0.161.1 | Web framework: routing, dependency injection (RBAC guards), pydantic request validation, multipart upload |
| uvicorn | >=0.30 | 0.54.0 | ASGI server (`--reload` for development) |
| pydantic | >=2.7 | 2.14.1 | API models and import record structure validation |
| pydantic-settings | >=2.2 | 2.16.1 | `.env` configuration loading (the `Settings` class) |
| python-multipart | >=0.0.9 | 0.0.32 | Multipart form/file uploads (`POST /files`, `POST /import`) |
| openpyxl | >=3.1 | 3.1.5 | XLSX parsing: dual-sheet manifests, merged-cell/multi-level header locator verification, source preview |
| pyjwt | >=2.8 | 2.15.1 | JWT signing/verification (HS256). **python-jose is not used** |
| jsonpath-ng | >=1.6 | 1.12.0 | Parsing and hit checking for the JSON locator `json_path` |

Development dependencies (`[dependency-groups] dev`): `pytest>=8` (locked 9.1.1), `httpx>=0.27` (locked 0.28.1, used by `fastapi.testclient`).

**Deliberately not introduced** (per the code):

- Password hashing uses the Python standard library `hashlib.pbkdf2_hmac` (SHA-256, random 16-byte salt, 240,000 iterations), with **no passlib / bcrypt dependency** (see §5);
- LLM calls use the standard library `urllib.request` to connect directly to the OpenAI-compatible `/chat/completions`, with **no openai SDK dependency** (see §8);
- Field search uses SQLite `LIKE`, with **no FTS5** (the M4 trade-off recorded in data model §3.2).

---

## 2. Layering and Module Responsibilities

Layering: **`routes/` (HTTP orchestration: parameter parsing, permission guards, exceptions → HTTP status codes) → service modules (`import_service` / `lineage` / `preview` / `versioning` / `changes` / `security` / `ai/*` and other business logic) → `db` (SQLite connections and DDL)**. Service modules are reusable across each other (e.g. `ai/tools.py` reuses `lineage.py` and `preview.py`; `seed_demo.py` reuses the formal paths `routes/files.store_upload` + `run_import`). Single process, single store, no message queue, no search cluster (design plan §8).

### 2.1 Root Modules (`prototype/backend/src/lineagelite/`)

| Module | Responsibility | Key functions/classes | Dependencies |
|---|---|---|---|
| `main.py` | Application entry: route assembly, CORS, lifespan startup initialization (create the database + seed the initial admin) | `create_app()`, `lifespan()` | all routes, `db`, `config`, `security` |
| `config.py` | Configuration loading and path resolution | `Settings`, `get_settings()`, `db_path()`, `files_dir()`, `resolve_storage()` | pydantic-settings |
| `db.py` | SQLite connections, transaction context, table creation DDL (10 tables + indexes) | `DDL`, `connect()`, `get_db()`, `init_db()` | `config` |
| `models.py` | pydantic API models and import record structures; locator input models (one per `src_type`) | `CsvLocatorIn` / `XlsxLocatorIn` / `JsonLocatorIn`, `LoginIn` / `UserCreate`, `AnnotationCreate` / `FieldPatch` / `EdgeCreate` / `EdgePatch` / `VersionTagCreate`, `AiChatIn` / `AiFocus` / `AiSuggestIn` / `AiEdgeKeyIn`, `DatasetFieldRecord` / `LineageEdgeRecord`, `ImportReport` / `ImportReportItem` | pydantic |
| `security.py` | Password hashing, JWT signing/verification, FastAPI role guard dependencies | `hash_password()`, `verify_password()`, `create_token()`, `current_user`, `require_role(minimum)`, `ROLE_ORDER` | `config`, `db`, pyjwt |
| `manifest.py` | Manifest normalization: CSV (two files) / XLSX (two sheets) / JSON (single file) → unified records | `read_csv_manifest()`, `read_xlsx_manifest()`, `read_json_manifest()`, `_row_record()` (row-level errors → `parse_error`) | openpyxl, `models` |
| `locator.py` | Locator structure model mapping and **real-file verification** (three checkers: csv/xlsx/json), materializing `resolved` | `CHECKERS`, `LOCATOR_MODELS`, `check_csv()` / `check_xlsx()` / `check_json()`, `_merged_anchor()`, `LocatorError` | openpyxl, jsonpath-ng, `models` |
| `import_service.py` | Import orchestration: row-level validation → real-file verification → upsert persistence → write change_log → generate import report | `run_import()`, `_resolve_source_file()`, `_ensure_dataset()`, `_upsert_field()`, `_log()` | `changes`, `locator`, `manifest` (indirectly), `db`, `config` |
| `lineage.py` | Lineage graph queries: recursive CTEs fetch an N-hop subgraph (dataset/field seeds; both/upstream/downstream) | `lineage_subgraph()`, `_dataset_closure()`, `_field_closure()`, `_payload()`, `DIRECTIONS`, `MAX_HOPS=5`, `LineageNotFound` | standard library (only a sqlite3.Connection argument) |
| `preview.py` | Field source preview: open the managed source file from the `src_locator` envelope, returning highlighted data + verification trail | `field_preview()`, `_preview_csv()` / `_preview_xlsx()` / `_preview_json()`, `PreviewError`, `PREVIEW_ROW_LIMIT=50`, `PREVIEW_JSON_LIMIT=10` | `config`, openpyxl, jsonpath-ng |
| `changes.py` | change_log writes and row snapshot utilities (shared by the import path and M3 manual edits) | `FIELD_SNAPSHOT_KEYS` / `EDGE_SNAPSHOT_KEYS`, `field_snapshot()` / `edge_snapshot()`, `log_change()`, `load_snapshot()`, `edge_key()`, `now()` | standard library |
| `versioning.py` | Version management: rollback by batch/tag (reverse change_log), tag create/list/diff, current-state snapshot | `rollback_batch()`, `rollback_to_tag()`, `create_tag()`, `list_tags()`, `tag_diff()`, `get_snapshot()`, `_reverse_log()`, `_restore_row()`, `_edge_created_by()` | `changes`, `db` |
| `seed_demo.py` | M2 demo data: generate csv/xlsx/json source files on the fly and load them through the formal upload + import path; idempotent | `seed_demo()`, `_demo_files()`, `_manifest()`, `_already_seeded()`, `_ensure_admin()` | `config`, `db`, `import_service`, `manifest`, `routes.files.store_upload`, `security`, openpyxl |

### 2.2 AI Subdirectory (`prototype/backend/src/lineagelite/ai/`)

| Module | Responsibility | Key functions/classes | Dependencies |
|---|---|---|---|
| `llm.py` | OpenAI-compatible Chat Completions client (pure urllib), configuration probing, and error classification | `complete()`, `is_configured()`, `endpoint_url()`, `LLMNotConfigured`, `LLMError`, `REQUEST_TIMEOUT_SECONDS=60` | `config`, standard library |
| `tools.py` | LLM read-only toolset (5 tools) + JSON Schema declarations + dispatcher; tool errors are returned to the model for self-correction | `TOOL_SCHEMAS`, `TOOL_FUNCS`, `search_fields()`, `get_field_details()`, `trace_lineage()`, `get_field_history()`, `mark_highlight()`, `run_tool()`, `ToolError` | `changes`, `lineage`, `preview` |
| `suggest.py` | Heuristic lineage suggestions: same-name/containment relations generate candidate edges, persisted with `source='ai'`, with a human confirm/reject loop | `suggest_edges()`, `confirm_suggestion()`, `reject_suggestion()`, `normalize_field_name()`, `_match()`; `EXACT_CONFIDENCE=0.7`, `CONTAINMENT_CONFIDENCE=0.6`, `MAX_SUGGESTIONS=20` | `changes` |
| `chat.py` | Conversation orchestration: function calling loop (at most 5 tool rounds), fixed system prompt, tool_trace / graph / highlights extraction | `run_chat()`, `SYSTEM_PROMPT`, `_system_prompt()`, `_parse_arguments()`, `MAX_TOOL_ROUNDS=5` | `llm`, `tools`, `db`, `config` |

### 2.3 Routes (`prototype/backend/src/lineagelite/routes/`, 13 files in total)

Each route declares a minimum role (`require_role`) and only performs HTTP orchestration: parameter parsing → permissions → call the service module → map exceptions to status codes. Endpoint details are in [./05_api-reference.md](./05_api-reference.md).

| Route file | Responsibility (endpoint group) | Minimum role | Services used |
|---|---|---|---|
| `auth.py` | `POST /auth/login`, `GET /auth/me`; admin user management `POST/GET /users` | login anonymous; users admin | `security`, `db`, `models` |
| `files.py` | Source file hosting: batch upload (sha256 dedup), listing, controlled download; the `store_upload()` service function is reused by `seed_demo` | viewer (upload/write: editor) | `config`, `db`, `security` |
| `imports.py` | Three-step import API (multipart: format + source_file_ids + manifest file), batch list/detail/report, rollback by batch; also the M1 verification endpoint `GET /lineage/snapshot` | import editor; batch query viewer; rollback admin | `import_service`, `manifest`, `versioning`, `db`, `security` |
| `datasets.py` | `GET /datasets` (with `field_names[]`), `GET /datasets/{id}` | viewer | `db`, `security` |
| `lineage.py` | `GET /lineage/subgraph` (N-hop subgraph GraphPayload) | viewer | `lineage`, `db`, `security` |
| `preview.py` | `GET /fields/{dataset_id}/{field_name}/preview` (source preview) | viewer | `preview`, `db`, `security` |
| `annotations.py` | `POST/GET /annotations` (append-only annotations; polymorphic target resolution and existence validation) | write editor; read viewer | `changes`, `db`, `models`, `security` |
| `fields.py` | `PATCH /fields/{dataset_id}/{field_name}` (description/type/**locator re-verification**) | editor | `changes`, `locator` (`CHECKERS`/`LOCATOR_MODELS`), `config`, `db`, `models`, `security` |
| `edges.py` | `POST /edges`, `PATCH /edges/{id}`, `DELETE /edges/{id}` (manual edges source='manual') | editor | `changes`, `db`, `models`, `security` |
| `changes.py` | `GET /changes` (change history, filter + descending + limit) | viewer | `db`, `security` |
| `version_tags.py` | `POST/GET /version-tags`, `GET /version-tags/diff`, `POST /version-tags/{name}/rollback` | create editor; rollback admin; the rest viewer | `versioning`, `models`, `security` |
| `ai.py` | `GET /ai/status`, `POST /ai/chat` (viewer); `POST /ai/suggest(/confirm|/reject)` (editor) | see left | `ai.llm`, `ai.chat`, `ai.suggest`, `config`, `db`, `models`, `security` |
| `__init__.py` | Package marker (`"""FastAPI routes."""`) | — | — |

---

## 3. Configuration (.env)

Configuration follows the `Settings` class in `config.py` (pydantic-settings):

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `SECRET_KEY` | str | `dev-secret-change-me` | JWT signing key (HS256); must be changed in production |
| `JWT_EXPIRE_HOURS` | int | `24` | JWT validity period (hours) |
| `DATA_DIR` | str | `./data` | Data directory: both the SQLite database and managed source files live here (resolved relative to the process working directory) |
| `ADMIN_USERNAME` | str | `admin` | Username of the initial admin created on first startup when the user table is empty |
| `ADMIN_PASSWORD` | str | `admin123` | Initial admin password (used only when the database is first created) |
| `MAX_UPLOAD_MB` | int | `50` | Maximum size of a single source file upload (MB); exceeding it returns 413 |
| `CORS_ORIGINS` | str | `http://localhost:5173,http://127.0.0.1:5173` | Allowed cross-origin frontend origins, comma-separated |
| `LLM_BASE_URL` | str | `""` | OpenAI-compatible service URL; empty = LLM not configured |
| `LLM_API_KEY` | str | `""` | LLM API key (may be empty, for local services without auth) |
| `LLM_MODEL` | str | `""` | Model name; "configured" only when both `LLM_BASE_URL` and `LLM_MODEL` are non-empty |

Key points:

- **`.env` lives at the repository root** and is not committed (`.gitignore`); a template is in the repository-root `.env.example` (containing `SECRET_KEY` / `JWT_EXPIRE_HOURS` / `DATA_DIR` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `CORS_ORIGINS` / `LLM_*`). Locator implementation (in `config.py`): `ENV_FILE = Path(__file__).resolve().parents[4] / ".env"` — `config.py` is in `prototype/backend/src/lineagelite/`, so four levels up is the repository root (`lineagelite → src → backend → prototype → ai-lineage`).
- Environment variables take precedence over the `.env` file (default pydantic-settings behavior); tests rely on this mechanism to inject a temporary `DATA_DIR` etc. via `monkeypatch.setenv` (see §10).
- Derived paths: `db_path = DATA_DIR/lineage.db`; `files_dir = DATA_DIR/files`; `resolve_storage(rel)` resolves `source_file.storage_path` (relative to `DATA_DIR`, e.g. `files/ab/ab12….csv`) to an absolute path. `MAX_UPLOAD_MB` is not listed in `.env.example` (it can be appended to `.env` to override; see §12).

---

## 4. Database

### 4.1 Database Initialization Flow and Connections

- **First startup**: `main.py` `lifespan` → `db.init_db()` executes `executescript(DDL)` (all `CREATE TABLE/INDEX IF NOT EXISTS`, idempotent) → if the `user` table is empty, creates the initial admin (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, `display_name='Initial Administrator'`, `role='admin'`) and prints a hint to stderr.
- **Connection** (`db.py` `connect()`): `sqlite3.connect(path, check_same_thread=False)`, `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON` (constraints such as the edge composite foreign key actually take effect); the parent directory is created automatically via `mkdir`.
- **Transactions**: `get_db()` is a `@contextmanager` — it `commit`s on normal return, `rollback`s and re-raises on any exception, and closes when done. All write paths (routes/services) complete inside a single `with get_db()`, ensuring partial failures are not persisted.

### 4.2 Schema and Its Mapping to Data Model §2

`DDL` in `db.py` aligns table by table with data model §2: `user`, `source_file`, `dataset`, `field`, `edge`, `import_batch`, `version_tag`, `annotation`, `change_log`, `rollback_record` (new in M3; 10 tables in total).

Implementation additions (already recorded in the data model, not drift):

- `import_batch` adds the `rolled_back_at` / `rolled_back_by` rollback trail columns (data model §2.6);
- The same-pair uniqueness invariant on `edge` is enforced by **two partial unique indexes** (`uq_edge_field` / `uq_edge_table`) — SQLite applies `NULLS DISTINCT` semantics to `UNIQUE` on combinations containing NULL, so table-level edges would not be caught (data model §2.5);
- Indexes: `idx_edge_to/idx_edge_from` (main recursive CTE path), `idx_field_sf`, `idx_log_entity`, `idx_log_batch`, `idx_annot_target`, `idx_rollback_tag`, consistent with data model §6;
- Time columns uniformly store ISO8601 UTC text (`changes.now()`, second precision).

Derived view: the `v_dataset_edge` view from data model §3.1 **is not created in the DDL** — table-level projection is derived on demand by queries (`_dataset_closure` traverses all edges) and is not persisted.

### 4.3 Reserved Postgres Path

Per the design plan: start with SQLite and write all SQL in a compatible subset + recursive CTEs (`lineage.py` comments state explicitly "only standard CTE syntax supported by both databases"). Migration notes are in data model §7: `AUTOINCREMENT`→`GENERATED ALWAYS AS IDENTITY`, time columns TEXT→`timestamptz`, field search `LIKE`→`tsvector`+GIN; recursive CTEs and composite FK semantics are identical and need no change. No ORM / migration tool is currently introduced; the DDL is a static script in `db.py`.

### 4.4 data_dir Directory Layout

```
{DATA_DIR}/
├── lineage.db                      # SQLite (all business tables)
└── files/<first 2 chars of sha256>/<sha256>.<ext>   # managed source files, content-addressed
```

- `source_file.storage_path` stores a relative path (e.g. `files/ab/ab12….csv`) that is **never exposed externally**; access goes through controlled APIs (`GET /files/{id}/download`, source preview).
- File names keep the original extension: parsers such as openpyxl identify the format by extension (comment in `routes/files.py`).

---

## 5. Authentication and RBAC

Implemented in `security.py` (+ `routes/auth.py`), corresponding to design plan §4.4.

### 5.1 JWT and Password Hashing

- **Signing**: `create_token(username, role)` produces an HS256 JWT with payload `{sub, role, iat, exp}` and `exp = iat + JWT_EXPIRE_HOURS`; the key is `SECRET_KEY`.
- **Verification**: `_bearer_payload` requires `Authorization: Bearer <token>`; a parse failure or expiry raises 401; `current_user` extracts `{username, role}`.
- **Password hashing**: standard-library PBKDF2-HMAC-SHA256 with a random 16-byte salt and `PBKDF2_ITERATIONS = 240_000`; storage format `pbkdf2$<iterations>$<salt hex>$<digest hex>`; verification uses `hmac.compare_digest` for constant-time comparison. Passwords are never stored in plaintext.

### 5.2 Role Guard (`require_role`)

`ROLE_ORDER = {viewer: 0, editor: 1, admin: 2}`; `require_role(minimum)` returns a FastAPI dependency function: it first passes `current_user` (401), then **queries the user's current role from the database in real time** (user not found 401; insufficient role 403 "requires role xx or above"). The database value is authoritative (the role in the JWT is only issued at login), so after an admin changes a role, old tokens immediately take effect with the new role (test `test_r4_role_change_takes_effect_immediately`).

### 5.3 Permissions per Role (per route declarations)

| Role | Allowed operations |
|---|---|
| `viewer` | All reads: login/`me`, `GET /datasets`, `GET /lineage/subgraph`, field source preview, `GET /annotations`, `GET /changes`, `GET /version-tags` and diff, `GET /import/batches`, `GET /files` listing and download, `GET /ai/status`, `POST /ai/chat` |
| `editor` | viewer + `POST /files` upload, `POST /import` import, `POST /annotations`, `PATCH /fields/...`, `POST/PATCH/DELETE /edges`, `POST /version-tags`, `POST /ai/suggest(/confirm|/reject)` |
| `admin` | editor + `POST/GET /users` user management, `POST /import/batches/{id}/rollback` rollback by batch, `POST /version-tags/{name}/rollback` rollback by tag |

(Design plan §4.4 also plans admin abilities to "delete datasets, reset imports"; the prototype does not implement those endpoints — see §12.)

### 5.4 Initial Admin

Both paths provide a fallback: `main.py` lifespan (when the user table is empty on first startup) and `seed_demo._ensure_admin()` (demo data needs a valid actor to satisfy the `source_file.uploaded_by` foreign key). After login, an admin can create other accounts via `POST /users` (one of three roles).

---

## 6. Import Pipeline

Corresponds to design plan §3 (import format spec, §3.5 validation rules / §3.6 source file hosting) and data model §4 (JSON structures). Overall chain:

```
① POST /files upload source files (sha256 dedup)
        ↓
② POST /import upload the manifest (manifest.py normalizes three formats)
        ↓
③ row-level validation + locator structure validation (models.py pydantic)
        ↓
④ real-file verification (locator.py CHECKERS, materialize resolved)
        ↓
⑤ batch persistence (import_service.run_import: fields → edges → change_log)
        ↓
⑥ import report (import_batch.report JSON)
        ↓ (closed loop)
⑦ source preview (preview.field_preview: locator-card highlight + verification trail)
```

### 6.1 Source File Upload (sha256 Dedup)

`routes/files.py` `store_upload(filename, data, username)`:

- Extension allowlist `csv/xlsx/json` (others 400); empty file 400; over `MAX_UPLOAD_MB` 413;
- Computes the `sha256` content fingerprint — **re-uploading the same content reuses the same `source_file` record** (returns `deduped: true`, does not rewrite disk); in lineage scenarios many fields often come from the same source file;
- Stores at `files/<sha[:2]>/<sha>.<src_type>`, registering the original file name, size, uploader, and time. `seed_demo` goes through the same service function.

### 6.2 Manifest Normalization (`manifest.py`)

The three physical formats (design plan §3.4) are normalized into the same set of pydantic records `DatasetFieldRecord` / `LineageEdgeRecord`, making subsequent processing format-independent:

| Format | Carried by | Parse function | Error semantics |
|---|---|---|---|
| CSV | Two files `datasets.csv` + `lineage.csv` (UTF-8, BOM tolerant) | `read_csv_manifest()` | Row-level errors go to `parse_error`; file-level errors (missing headers, etc.) reject the whole batch with 400 |
| XLSX | One workbook with two sheets `datasets` / `lineage` (sheet names matched after strip+lower) | `read_xlsx_manifest()` | Missing sheet / root parse failure rejects the whole batch with 400 |
| JSON | Single file `{"datasets": [...], "lineage": [...]}` (`src_locator` is a nested object) | `read_json_manifest()` | Root JSON parse failure rejects the whole batch with 400 |

- The `src_locator` column accepts a dict (JSON manifest) or a JSON string (CSV/XLSX cells);
- **Row-level parse errors are not raised**; they are written to the record's `parse_error` field, and the import stage rejects the entire row (the reason is the in-row error description), so one bad row does not fail the whole batch with 400;
- `row` records the original manifest row number (CSV/XLSX start at 2, JSON starts at 1) and becomes `source_row` in the report.

### 6.3 Locator Validation and Real-File Verification (`locator.py`)

`LOCATOR_MODELS` (`src_type` → pydantic input model) performs **structure validation**, and `CHECKERS` (`src_type` → checker) opens the managed source file for **real-file verification** and materializes `resolved` (data model §4.1 envelope `{type, input, resolved}`):

| src_type | Validation/verification points | resolved materialization |
|---|---|---|
| csv | Either `column` (1-based) or `header`; the header name must match in the first row; the column number must not exceed the column count | `{column_index, header}` |
| xlsx | The sheet must exist; either `column` (column letter) or `header_path` (multi-level header); `row_end >= row_start`; **multi-level headers** are matched row by row per level, with parent merged cells expanded into candidate column ranges to continue descending; **anchor normalization**: a locator inside a merged region materializes to the top-left anchor + merged range | `{column_index, column, row_start, row_end, merged_anchors[]}` (`row_start` defaults to `header_rows+1` when not given for a `header_path`) |
| json | JSONPath syntax is valid and hits at least once in the source file | `{hits}` |

Verification failure raises `LocatorError`, which the import stage turns into `rejected` for that row (the reason starts with "real-file verification failed: "), **without producing an HTTP error** — the batch import completes as usual and every result is reflected item by item in the report. The same `CHECKERS`/`LOCATOR_MODELS` are reused by locator editing in M3 `PATCH /fields/...` (see §6.6).

### 6.4 Batch Persistence and Import Report (`import_service.run_import`)

Executed within a single transaction (any exception rolls back everything):

1. Create `import_batch`: `version_no = MAX(version_no)+1`, record the manifest file names (JSON array), format, and operator;
2. **Stage one: datasets/fields** (fields before edges, to satisfy the edge table's composite foreign keys):
   - Row-level validation: `parse_error`, required `dataset_id/field_name`, `src_type` enum, `src_file` reference resolution (pure digits → source file ID within the batch's bound file set; otherwise **unique lookup** by original file name in the bound set, with 0 or multiple hits both rejected), `src_type` matching the source file's actual `src_type`;
   - After structure validation + real-file verification pass, assemble the locator envelope and persist it;
   - `_ensure_dataset`: auto-create the dataset if missing (writes a `dataset added` log); `_upsert_field`: new → `added`; completely identical values → `ok (unchanged)` with no log; differences → `updated`;
3. **Stage two: lineage edges**: `parse_error`, required `from_dataset/to_dataset`, **mixed field edges (one empty, one non-empty) rejected**, upstream/downstream fields referenced by field-level edges must exist (in this batch or an existing version), datasets must exist, `confidence` in 0~1 (default 1.0);
   - Duplicate natural keys within the same batch: **later entries override** `transform/confidence/note`, and the report marks `merged` (design plan §3.5-4);
   - Existing edges: identical values → `ok (unchanged)` with no log (re-import is idempotent); differences → `updated` — note that this path overwrites `source` back to `'imported'` (see §12-7);
   - New edges get `source='imported'` and write an `added` log;
4. Each change writes `change_log` (op + before/after business-column snapshots; snapshot keys in `changes.py`);
5. Produce `ImportReport` `{summary: {total, ok, merged, rejected}, items: [{status, kind, ref, reason, source_row}]}` (data model §4.3), serialize it into `import_batch.report`, downloadable with batch details.

### 6.5 Source Preview Loop (`preview.field_preview`)

After clicking a field's locator card, preview the source file region directly in the system (design plan §3.6): returns `file` (id/original name/sha256/size/type/uploader) + `verification` (`{status:"passed", version_no, checked_by, checked_at}` or `null` — taken from the most recent `added/updated` change_log entry for that field tied to an import batch; the importer only writes a log after verification passes, so that record means "verification passed") + the `locator` envelope + a structured preview (csv: header + column number + first 50 rows; xlsx: header rows/merged regions/columns/row range + first 50 rows; json: hit count + first 10 hit values). **Locator failure** (missing file, renamed sheet, out-of-range row/column, no JSONPath hits, etc.) uniformly raises `PreviewError` → HTTP 409.

### 6.6 Locator Editing in Human Correction (design plan §7)

`routes/fields.py` `PATCH /fields/{dataset_id}/{field_name}`: can change `description / field_type / src_locator`; when `src_locator` is supplied, it accepts either the locator `input` or a full envelope (`resolved` is always discarded and recomputed), and **must go through structure validation + real-file verification + envelope rewrite again**; any failing step returns 409 (with a human-readable reason) and the field keeps its original value within the transaction; on success it writes `change_log` (`batch_id=NULL`, op=`updated`). A locator type that does not match the source file's `src_type` returns 409.

---

## 7. Versions and Rollback

Implemented in `versioning.py` + `changes.py`, with rules from data model §7. Core idea: **the current state is read from and written to the base tables directly, and all historical capability is reconstructed from the `change_log` append log**; no full snapshots are taken.

### 7.1 Append-Only change_log Records

- `changes.log_change()`: all write paths append logs within the same transaction; snapshots contain only business columns (`FIELD_SNAPSHOT_KEYS` / `EDGE_SNAPSHOT_KEYS`, excluding `id`/timestamps/audit columns), so before/after for the same entity can be compared directly and a deleted row's before image can be re-inserted whole;
- `edge_key()` generates polymorphic names of the form `<ds>.<field|-->*--><ds>.*` (data model §5.2);
- The import path writes `batch_id=<batch>`; manual edits write `batch_id=NULL`, so they do not interfere with batch rollback.

### 7.2 Rollback by Batch (`rollback_batch`, admin)

- Batch not found 404; already rolled back (`rolled_back_at` non-null) 409;
- Take all logs of the batch and reverse them in **descending id order**: `added`→delete, `updated`→restore before, `deleted`→re-insert before (`_reverse_log`);
- If reversal hits `sqlite3.IntegrityError` (foreign key/unique conflict; typical scenario: an edge created by a later batch references a field of this batch) → roll back everything + 409 "edges from later batches reference fields of this batch; roll back later batches first" — **batch rollback must proceed linearly from newest to oldest**;
- On success, write `import_batch.rolled_back_at/by`; the rollback itself does not write change_log.

### 7.3 Version Tags (`create_tag` / `list_tags` / `tag_diff`)

- Create (editor): `change_seq = current change_log MAX(id)` anchors the end of the log; `batch_id` is informational only (takes the current most recent batch; rollback does not depend on it); duplicate name 409; **no change_log entry is written** — otherwise "roll back to an earlier tag" would treat the tag as reversible data and delete it, violating "tags are kept forever" (data model §2.7);
- diff (viewer): the interval `(from.change_seq, to.change_seq]` is merged by `(entity_kind, entity_key)` — the first before in the interval is the start point and the last after is the end point; if both start and end are empty (added then deleted) it is not counted as a net change; if from is later than to, return 400.

### 7.4 Rollback to Tag (`rollback_to_tag`, admin, idempotent)

- Reverse **all** logs with `id > tag.change_seq` (across batches + manual edits), in descending id order;
- **Idempotent reversal**: `_restore_row` uses `ON CONFLICT ... DO UPDATE` / read-then-write (edge natural keys contain NULL, so partial unique indexes cannot be ON CONFLICT targets), and `_delete_row` is naturally idempotent — repeated rollbacks are safe and the final state is unchanged;
- Audit column restoration: when re-inserting an edge, `created_by` is preferably restored from the actor of the most recent `added` log for the same natural key **before** this deleted log (falling back to the rollback executor if absent), and `updated_by` records the rollback executor;
- Batches owning the reversed logs are also updated with `COALESCE` writes to `rolled_back_at/by` (repeated rollbacks keep the first timestamp; tags are only created between batch transactions, so a single batch is never split);
- **Audit**: each call appends a `rollback_record` (tag_name, interval from/to, reverted count, actor, time) — the rollback itself does not write change_log, otherwise the next rollback would reverse the "rollback logs" and break idempotency (data model §2.10).

### 7.5 Write and Audit Matrix

For whether each write operation writes change_log and where its audit lands, see data model §9.4 (annotations are append-only, never modified, and write no log; manual field/edge edits write logs; tag creation and rollback write no log and land in `version_tag` and `rollback_record` respectively). Annotations do not participate in rollback and are kept forever.

---

## 8. AI Module (M4/M5)

Corresponds to design plan §6 (AI chat) and §6.4 "the two paths of AI optimization"; M5's LangChain migration / streaming / in-conversation suggestions / description drafts / MCP are covered in [07_ai-module-evolution-plan](./07_ai-module-evolution-plan.md). Security baseline: **AI has only read-only query capability + low-confidence candidate suggestions, and a candidate takes effect only after human confirmation; write-type tools (candidates / drafts) validate the caller's role at execution time, and when triggered by a viewer the call is returned to the model as a tool error and nothing is written to the database** (business invariant #4; role guardrails in [08_review-fix-batch-2026-10-26](./08_review-fix-batch-2026-10-26.md) R8).

### 8.1 LLM Access Layer (`ai/llm.py`, D1 upgraded to LangChain)

- `get_chat_model()` builds a `ChatOpenAI` from settings (temperature=0, timeout 60s, max_retries=1); `complete()` **keeps its original signature** (it internally converts to LangChain messages and back to OpenAI dict form, so existing orchestration/tests need zero changes), `stream_chat()` supports per-token callbacks (SSE aggregation), and `get_embeddings()` returns `None` when embeddings are not configured (semantic suggestions degrade to pure heuristics, D5); `endpoint_url` supports both `https://host/v1` and the fully written `.../chat/completions`; provider, key, and model are configured through the repository-root `.env`; keys are never committed and the API never echoes them back;
- `is_configured()`: configured only when both `LLM_BASE_URL` and `LLM_MODEL` are non-empty (`LLM_API_KEY` may be empty, for local services without auth);
- When `tools` is empty, no `tools`/`tool_choice` is sent (used to close out the answer);
- Error classification: `LLMNotConfigured` (routes map to **503**) and `LLMError` (non-200 HTTP / unreachable / invalid response structure; routes map to **502**);
- `GET /ai/status` returns `{configured, model}` (`model=null` when not configured); when not configured, the chat endpoints (streaming or not) both return 503 (`NOT_CONFIGURED_MESSAGE` explains how to configure).

### 8.2 Toolset (`ai/tools.py`, 8 tools in M5)

`TOOL_SCHEMAS` (OpenAI function calling JSON Schema) + tool implementations; each function receives a `sqlite3.Connection` that `chat.py` opens on every round. Six read-only tools + two write-type tools (their persistence targets are the candidate/draft workspace, which **never touches business data** and takes effect only after human confirmation, 07 §4.4):

| Tool | Type | Description |
|---|---|---|
| `search_fields` | read-only | `LIKE` matching on dataset_id / dataset name / field name / field description / field annotation (no FTS5); exact > prefix > the rest; `LIMIT 20` |
| `get_field_details` | read-only | Field metadata + locator envelope + source file + annotations + source preview (a preview failure degrades to `{"error": ...}` without blocking details) |
| `trace_lineage` | read-only | Reuses `lineage_subgraph` (direction both/up/down, hops 1~5) and returns a GraphPayload for canvas rendering |
| `get_field_history` | read-only | Field change_log in descending order `LIMIT 50` (reuses `changes.load_snapshot`) |
| `mark_highlight` | read-only | Canvas linkage signal: validates `{dataset, field}` existence, dedupes, cap 8; invalid items are recorded in `ignored`, and if all are invalid a `ToolError` is raised (see doc 06) |
| `analyze_impact` | read-only | Downstream impact aggregation: downstream field list + each one's source file and verification status + recent changes (`MAX_IMPACT_CHANGES=10`) |
| `suggest_lineage` | **write-type** | Runs the existing heuristics (+ semantic layer) for a dataset/field to generate candidate edges, persisted with `source='ai'` (human confirmation required); **editor+ only** (R8) |
| `draft_descriptions` | **write-type** | Generates description drafts into `description_draft` for fields lacking descriptions (`lang` defaults to zh, parameterized in R12); **editor+ only** (R8) |

Invalid parameters/targets raise `ToolError`, which is returned to the LLM as `{"error": ...}` for self-correction **without interrupting the conversation**; insufficient role is likewise returned as a `ToolError` (nothing is written, and `tool_trace` records `ok=false`).

### 8.3 Heuristic Lineage Suggestions (`ai/suggest.py`)

**Does not call the LLM; runs offline** (a lightweight implementation of path 2 in design plan §6.4):

1. Field name normalization (`lower` + strip underscores): exact equality → `confidence=0.7`; containment (the shorter side ≥3 chars) → `0.6`;
2. Candidate direction: the dataset/field given in the request is upstream (from), and similar fields in **other datasets** are downstream (to);
3. Exclude existing edges (in both directions, to avoid suggesting reverse duplicates/cycles) and keys already seen in this run; sort by descending confidence, stable within equal confidence, cap 20;
4. Candidates are **persisted with `source='ai'`** and write `change_log(added)` — repeated calls with the same natural key are skipped and not persisted again;
5. Closed loop (all located by the four-part natural key; only `source='ai'` candidates are operable, otherwise 404):
   - `POST /ai/suggest/confirm` (editor): change `source` to `manual` and write an `updated` log;
   - `POST /ai/suggest/reject` (editor): delete the candidate edge, write a `deleted` log, return 204.

### 8.4 Conversation Orchestration (`ai/chat.py`, function calling)

- The system prompt **is fixed by the backend** (`SYSTEM_PROMPT`: tool instructions + "must answer based on tool data, must not fabricate", "write-type outputs require confirmation and there is no direct write permission", "call mark_highlight first when highlights are needed", "answer in the same language as the question"); the frontend only sends user/assistant history (`AiChatMessage.role` is limited to these two), with an optional `focus={dataset, field}` to append focused context;
- Loop: call `llm.complete(messages, tools)` → when the model returns `tool_calls`, execute each tool (**the caller's role is passed into `run_tool`, and viewer calls to write-type tools are rejected**, see §8.2 and R8), append the results as `role=tool` messages, and continue to the next round; when no more tools are requested, take content as the final `answer`;
- **Boundedness**: at most 5 tool rounds (`MAX_TOOL_ROUNDS=5`); the 6th request carries no tools to force closure;
- **Context budget** (doc 08 R10): after extracting `graph`/`highlights`/`suggestions`/`drafts`, tool results are JSON-truncated before being appended back to the conversation (`MAX_TOOL_RESULT_CHARS=4000`, with a truncation marker; canvas linkage data is unaffected by truncation); after each round is appended, **the oldest whole rounds are trimmed** according to `CONTEXT_TOKEN_BUDGET` (default 96k tokens, overridable in `.env` via `LLM_CONTEXT_TOKEN_BUDGET`, estimated at ASCII≈4 chars/token, CJK≈1 char/token), where a whole round = one assistant message together with all its tool messages; the system message and the current round are never removed;
- Returns `{answer, tool_trace: [{tool, args, ok}], graph?, highlights?}` — `graph` is the GraphPayload from the last `trace_lineage` return, for frontend canvas linkage rendering; `highlights` aggregates fields declared by `mark_highlight` (deduped across calls, cap 8) for the frontend canvas red trace-chain linkage;
- Tool argument `arguments` supports both dict and JSON-string provider shapes; content supports both strings and segmented arrays.

### 8.5 SSE Streaming and Stop on Disconnect (`routes/ai.py` + `ai/chat.py`, M5)

- `POST /ai/chat/stream` (viewer+): orchestration runs in a background thread and events are handed to the generator through a queue; event types are `token` / `tool` / `suggest` / `drafts` / `done` / `error`; for the full contract see 05 §13.6;
- **Heartbeat** (doc 08 R9): when events are absent for more than 15s, emit the comment frame `: ping` to prevent reverse proxies from cutting silent connections; the frontend parser safely ignores comment frames;
- **Stop on disconnect** (doc 08 R9): a client disconnect sets the cancellation event, which the orchestration loop checks every round; rounds that have not started (including the `suggest_lineage` / `draft_descriptions` writes) are not executed;
- The non-streaming `POST /ai/chat` contract is unchanged (MCP/script consumption scenarios). For streaming orchestration details see [07_ai-module-evolution-plan](./07_ai-module-evolution-plan.md) §4.3.

### 8.6 Rate Limiting (`ai/ratelimit.py`, doc 08 R11)

- In-memory sliding-window rate limiting (`time.monotonic` + per-user deque + `threading.Lock`), with the FastAPI dependency factory `ai_limiter(window_seconds, max_requests)`; over-limit returns 429 with `Retry-After`;
- Mounted on: `/ai/chat`, `/ai/chat/stream` → 10 requests/60s/user; `/ai/suggest*` → 6 requests/60s/user [TBD-OPS: thresholds may be adjusted based on usage];
- No third-party dependencies; windows are counted in process memory, so multi-process deployments need external storage (explicitly out of scope for the single-machine form; see 08 §5).

---

## 9. Error Handling Conventions

- **Unified shape**: the route layer raises `HTTPException(status, detail)`, where detail is a **human-readable reason** (the frontend displays it directly, e.g. the 409 locator verification failure reason). The service layer does not raise HTTP exceptions directly; it raises domain exceptions that routes convert:

| Service-layer exception | Route mapping | Typical scenario |
|---|---|---|
| `LookupError` (including `LineageNotFound`) | 404 | Dataset/field/edge/batch/tag/source file/AI candidate edge not found |
| `PreviewError` | 409 | Source preview locator failure (missing file, renamed sheet, out-of-range row/column, no JSONPath hits) |
| `LocatorError` | No HTTP error — row-level `rejected` in the import report; a `PATCH /fields` verification failure returns 409 | Real-file verification failure |
| `ValueError` (business rules) | 400 or 409 (by semantics) | Duplicate tag name 409, diff with `from` later than `to` 400, batch already rolled back 409, rollback reference conflict 409 |
| `LLMNotConfigured` / `LLMError` | 503 / 502 | LLM not configured / LLM upstream error |
| `sqlite3.IntegrityError` | 409 (caught in the service layer and converted to `ValueError`) | Foreign key/unique conflict during rollback; concurrent duplicate `POST /edges` caught by the unique index and converted to 409 |

- **Status code semantics**: 401 missing/invalid Bearer credentials or user deleted; 403 insufficient role (`require_role`); 400 request structure/format/parameter error (including mixed field edges and missing manifest files); 404 target not found; **409 business conflict** — locator verification failure (PATCH field), field modified/source file type mismatch, edge natural key already exists, batch already rolled back, rollback referential integrity conflict, duplicate tag name, duplicate username; 413 single file over `MAX_UPLOAD_MB`; 422 subgraph parameter out of range (`hops`/`direction`, double-checked by FastAPI Query validation and manual validation in `lineage.py`); 502/503 are used only for LLM.
- **Row-level vs whole batch**: row-level errors in the import manifest (parse/validation/verification) **do not produce HTTP errors**; they become per-item `rejected` entries in the import report with reason + row number; file-level errors (missing sheet, root JSON parse failure, format mismatch) reject the whole batch with 400.
- **Transaction guarantee**: all write operations complete within a single transaction in `with get_db()`; exceptions roll back automatically (e.g. a field keeps its original value when locator verification fails).

---

## 10. Testing

### 10.1 How to Run

```bash
cd prototype/backend
uv run pytest          # pyproject [tool.pytest.ini_options] testpaths=["tests"]
```

### 10.2 Isolated Environment Setup (`tests/conftest.py` + `tests/fixtures.py`)

- `client` fixture: `monkeypatch.setenv` injects `DATA_DIR=<tmp_path>/data`, `SECRET_KEY`, `ADMIN_USERNAME/PASSWORD` (environment variables take precedence over the repository-root `.env`) → `create_app()` + a `TestClient` context triggers lifespan → **each test case gets an independent temporary data directory** (temporary database + temporary managed files), fully isolated from development data;
- Helper functions: `login()` (logs in and obtains Bearer headers), `create_user()` (creates a user with the specified role and logs in), `upload()` (batch upload), `csv_bytes()`;
- `fixtures.py` builds first-hand file samples: `order_xlsx_bytes()` (XLSX with B1:F1 merged "Product Info" + G1 "Shipping Info", i.e. **multi-level headers + merged cells**), `user_csv_bytes()`, `source_json_bytes()`;
- LLM never touches the network: `monkeypatch.setattr("clew.ai.llm.complete", fake)` replaces the client; other cases monkeypatch `urllib.request.urlopen` to verify request construction.

### 10.3 Test Files and Coverage Areas

| File | Coverage area |
|---|---|
| `test_auth_rbac.py` | Login/me, wrong password 401, viewer has no write permission, editor can upload but cannot manage users, unauthenticated 401, CORS allows only configured origins |
| `test_files.py` | sha256 dedup, invalid type 400, controlled download returns the original content |
| `test_import.py` | CSV manifest (multi-level-header XLSX locator + bad locator rejection), XLSX manifest, JSON manifest, missing sheet rejects the whole batch |
| `test_rollback.py` | Rollback by batch after a v2 import restores the v1 state, unknown batch 404, repeated rollback rejected |
| `test_lineage_api.py` | M2 acceptance: dataset/field seed subgraphs, hops and directions, table-level edges fully connected, GraphPayload contract shape, three-format source preview, 404/409 (locator failure), authentication, parameter out of range |
| `test_m3_api.py` | M3 acceptance: annotation append and target validation, field PATCH (locator re-verification), edge CRUD and natural keys, GraphPayload edges[].id, changes filter/sort/limit, tag create/list/diff, tag rollback idempotent and preserving annotations, 403 on all write endpoints for viewer |
| `test_m4_api.py` | M4 acceptance: LLM client endpoint construction, status/unconfigured 503, tool loop returning answer/graph, tool error feedback, 5-round cap, LLM error 502, heuristic suggestions (same-name/containment/excluding existing), confirm/reject flow and permissions |
| `test_m5_api.py` | M5 acceptance: SSE event sequence and "no tokens emitted during tool rounds", MCP server tool names (5 read-only) |
| `test_review_fixes.py` | Review fix regressions: R1–R7 (2026-10-24 round: partial unique indexes block duplicate table-level edges, mixed field edges rejected, rollback foreign key conflict 409, role changes take effect immediately, row-level parse errors reject only the row, same-pair edges merged, re-import idempotent without logs, empty upload 400 / over-limit 413); R8–R12 (2026-10-26 round: role guardrails for write-type tools, SSE heartbeat and stop on disconnect, tool result truncation and context trimming, AI route rate limiting 429, draft prompt language parameter) |

All test data is loaded through the formal APIs (upload → import → operate); business tables are never INSERTed directly (a few cases connect to SQLite only for assertion reads).

---

## 11. Operations Commands

```bash
cp .env.example .env                  # repository-root configuration (SECRET_KEY / ADMIN_PASSWORD / LLM_* etc.)
cd prototype/backend
uv sync                               # install dependencies (creates/uses .venv and uv.lock)
uv run uvicorn lineagelite.main:app --reload   # start (default 127.0.0.1:8000; creates the database + initial admin on first run)
uv run pytest                         # acceptance tests
uv run python -m lineagelite.seed_demo          # demo data (idempotent, skipped on repeat runs)
```

- **seed_demo**: generates on the fly 5 datasets (d0→d1→d2→d3→d4, a four-hop chain), 1 field-level edge + 1 table-level edge per hop, plus csv / xlsx (merged-cell multi-level headers) / json source-preview samples; it goes through the formal upload + import path (`store_upload` + `run_import`). Note: the execution directory written in the module docstring "cd backend" should be `prototype/backend` (the README is authoritative).
- **Rollback notes**:
  - Batch rollback must run **linearly from newest to oldest** (when a later batch's edge references an earlier field, rolling back the earlier batch first returns 409);
  - Tag rollback is idempotent (repeated rollbacks leave the final state unchanged), and each call appends a `rollback_record` audit entry;
  - Rollback never deletes annotations or tags (kept forever); reversed batches show `rolled_back_at` in the batch list;
  - Backup = back up the entire `DATA_DIR` (the single SQLite file + managed source files addressed by sha256 must stay consistent with each other).
- Deployment form: single-process uvicorn; CORS is explicitly configured via `CORS_ORIGINS` (authentication uses Bearer headers rather than cookies, `allow_credentials=False`).

---

## 12. Known Differences and Notes

The following are inconsistencies between design documents and code found while writing this document, or code behavior not explicitly covered by the design documents (numbered for easy reference):

1. **FTS5**: design plan §2 (non-goals) and the §8 architecture diagram say "SQLite (FTS5 search)", but the implementation does not introduce FTS5; `search_fields` uses `LIKE` full-table scans (data model §3.2 already records this trade-off; the design plan was not updated in sync).
2. **AI toolset**: design plan §6.2 lists 6 tools and describes them as "thin wrappers over REST" (corresponding to endpoint forms such as `GET /search`, `GET /lineage/trace`); the implementation provides 8 **internal Python tools** (including the two in-conversation write-type tools `suggest_lineage` and `draft_descriptions`, see §8.2), with no standalone REST search endpoint; lineage suggestions have a separate direct endpoint `POST /ai/suggest` (data model §9.3 and [05_api-reference](./05_api-reference.md) §13 already record it per the implementation).
3. **seed_demo execution directory**: the `seed_demo.py` docstring says `cd backend`, but it is actually `prototype/backend` (the README is correct).
4. **edge unique constraint**: the design plan §4.1 DDL only has `UNIQUE(four columns)`; the implementation additionally creates the two partial unique indexes `uq_edge_field` / `uq_edge_table` (explained in data model §2.5; this is a documented M1 increment).
5. **`.env.example` does not list `MAX_UPLOAD_MB`**: `Settings` supports it (default 50MB) but the template lacks the key, so users must add it to override.
6. **`GET /lineage/snapshot`**: the M1 verification endpoint is defined in `routes/imports.py` (its path prefix belongs to lineage) and is not listed in the README API overview; from M2 on the main query capability is `GET /lineage/subgraph`.
7. **Re-import overwrites `source`**: in `import_service` stage two, an existing edge with different content is updated via `UPDATE ... source='imported'` — if an edge was previously a manual edge (`manual`) or a confirmed AI edge, re-importing the same natural key from a manifest changes its source back to `imported`. The design documents do not specify the merge rule for `source` on re-import; [TBD-BIZ] whether the original `source` should be preserved is to be confirmed by product in the next milestone.
8. **admin "delete dataset / reset import"** (design plan §4.4) and per-row user role modification (a known README gap, `[TBD-BIZ]`) are not implemented in the prototype; user management only supports list + create.
