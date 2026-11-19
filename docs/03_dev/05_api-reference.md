# Clew Frontend-Backend API Documentation

> This document is the **single authoritative API contract** for frontend-backend interaction in LineageLite (a lightweight AI lineage tool): all endpoints, parameters, request/response structures, and error semantics are written by checking them item by item against the route code under `prototype/backend/src/lineagelite/` (implemented scope M1–M4); proposed endpoints that are not implemented are marked separately. For system architecture see ./01_architecture.md, for the frontend's calling conventions see ./02_frontend-development.md, for backend module breakdown see ./03_backend-development.md, and for the responsibility boundary of the frontend-backend data contract see ./04_frontend-backend-boundaries.md.

## Basis and sources

| Abbreviation | Location | Scope in this document |
|---|---|---|
| Route code | `prototype/backend/src/lineagelite/routes/` (`auth.py`, `files.py`, `imports.py`, `datasets.py`, `lineage.py`, `preview.py`, `fields.py`, `edges.py`, `annotations.py`, `changes.py`, `version_tags.py`, `ai.py`) | Methods, paths, role dependencies, and error raising for all endpoints |
| Entrypoint / security | `prototype/backend/src/lineagelite/main.py`, `security.py` | Route mounting, CORS, Bearer authentication, role guards |
| Models | `prototype/backend/src/lineagelite/models.py` | Fields, types, and constraints of request/response pydantic models (verified verbatim) |
| Supporting modules | `prototype/backend/src/lineagelite/` (`db.py`, `lineage.py`, `preview.py`, `versioning.py`, `changes.py`, `import_service.py`, `manifest.py`, `locator.py`, `config.py`, `ai/chat.py`, `ai/llm.py`, `ai/suggest.py`, `ai/tools.py`) | Response structures, error reasons, manifest format, locator materialization rules |
| Design document | `docs/01_design/clew-design-proposal.md` | §3.5 import validation, §3.6 hosted source-file upload, §6.2 AI toolset |
| Data model | `docs/01_design/clew-data-model.md` | §4 JSON structures (locator envelope / before/after snapshots / import report), §5.2 entity_key naming, §9 API contract increments (M2/M3/M4) |
| README | Root `README.md` of the repository | API overview cross-check (differences in §17; the code prevails) |

Conventions: when documentation and code disagree, **the code prevails**; `[ASSUMPTION]` marks an inference that cannot be determined from the code and must be stated; `[TBD-BE]` marks an endpoint present in the design document but not implemented by the backend. Example data is fabricated and only guarantees correct types and business meaning.

---

## 1. General conventions

### 1.1 Base URL and proxy

- Development backend: `http://127.0.0.1:8000` (`uv run uvicorn clew.main:app --reload`, see root `README.md`).
- The development frontend (Vite, `http://localhost:5173`) forwards the `/auth`, `/users`, `/files`, `/import`, `/datasets`, `/lineage`, `/fields`, `/edges`, `/annotations`, `/changes`, `/version-tags`, `/ai` prefixes to the backend via the proxy in `prototype/frontend/vite.config.ts`, i.e. **same-origin access**, so there are no cross-origin issues on the browser side.
- If the frontend bypasses the proxy and connects directly to the backend (e.g. a standalone deployment), allowed cross-origin origins are configured by `CORS_ORIGINS` in the repository-root `.env` (default `http://localhost:5173,http://127.0.0.1:5173`), with `allow_credentials=False` (authentication uses the Bearer header rather than cookies, `main.py`).

### 1.2 Authentication and roles

- Except for `POST /auth/login`, **all endpoints require authentication**: request header `Authorization: Bearer <JWT>` (`security.py`).
- JWTs are issued by `POST /auth/login`: HS256, payload `{sub: username, role, iat, exp}`, lifetime `JWT_EXPIRE_HOURS` (default 24 hours, `.env`).
- Three role levels: `viewer < editor < admin` (`ROLE_ORDER`). Routes declare the **minimum role** with `require_role("viewer"|"editor"|"admin")`; the role is taken from the current database value (the role in the JWT is only a login-time snapshot, so after an administrator changes the database an old token immediately takes effect with the new role).
- Missing/invalid Bearer credentials → 401 "Missing Bearer credentials" / "Invalid or expired credentials"; the user corresponding to the token has been deleted → 401 "User does not exist or has been deleted"; database role below the requirement → 403 "Requires {minimum} role or above".
- `GET /auth/me` is special: it only decodes the JWT (`current_user`) and neither queries the database nor validates the role.
- Frontend convention (./02_frontend-development.md): the token is stored in `localStorage`; any request that receives 401 returns to the login page.

### 1.3 Content-Type

| Scenario | Content-Type |
|---|---|
| Plain JSON request body (POST/PATCH) | `application/json` |
| `POST /files`, `POST /import` | `multipart/form-data` |
| Other GET / DELETE / 204 responses | No request body |

### 1.4 Error response structure

- Business errors (`HTTPException` in code) uniformly take the form:

```json
{ "detail": "Error message" }
```

- When the request body/query parameters fail pydantic validation, FastAPI automatically returns **422**, with `detail` as an array of validation details (`[{loc, msg, type}, ...]`), not a string. The frontend must treat 422 as an array.
- Successful responses are always JSON (except file downloads and 204).

### 1.5 Status code semantics

| Status code | Meaning | Typical trigger in code |
|---|---|---|
| 200 | Success (default) | All GET, PATCH, POST /ai/*, etc. |
| 201 | Created | `POST /users`, `POST /files`, `POST /import`, `POST /edges`, `POST /annotations`, `POST /version-tags` |
| 204 | Success with no response body | `DELETE /edges/{edge_id}`, `POST /ai/suggest/reject` |
| 400 | Request semantic error | Empty request body, field-level/table-level either-or violation, malformed `target_id`/`source_file_ids`, missing or unparsable manifest file, reversed tag diff direction, etc. |
| 401 | Unauthenticated | Missing/invalid/expired Bearer; user deleted; wrong login username or password |
| 403 | Authenticated but insufficient role | The `require_role` guard determines that the database role is below the minimum role |
| 404 | Target not found | Dataset/field/edge/source file/batch/tag/AI candidate edge not found; wrong login username |
| 409 | State conflict (business invariant violated) | See the 409 scenario summary below |
| 413 | File too large | A single uploaded file exceeds `MAX_UPLOAD_MB` (default 50MB, `routes/files.py`) |
| 422 | Parameter validation failed | Automatic pydantic/FastAPI validation (e.g. `hops` outside 1-5, `confidence` outside 0-1, invalid `role` enum); internal validation in `GET /lineage/subgraph` is also mapped to 422 |
| 502 | LLM upstream error | `POST /ai/chat`: LLM service unreachable, non-200 response, or invalid response structure (`ai/llm.py`) |
| 503 | Service not configured | `POST /ai/chat`: `LLM_BASE_URL` / `LLM_MODEL` not configured in `.env` |

**409 scenario summary** (all from `HTTPException(409, ...)` in code or its mappings):

| Endpoint | Trigger condition |
|---|---|
| `POST /users` | Username already exists (unique constraint) |
| `GET /fields/{ds}/{f}/preview` | The locator is no longer valid for the current source file: file not in managed storage, envelope type inconsistent with the source file type, CSV header/column index out of range, XLSX sheet missing or row/column out of range, JSONPath with no hits, corrupted source file (`preview.PreviewError`) |
| `PATCH /fields/{ds}/{f}` | `src_locator` locator type inconsistent with the source file's `src_type`, structure validation failure, real-file verification failure, source file not in managed storage (uniformly mapped to 409 by `routes/fields.py`) |
| `POST /edges` | An edge with the same upstream/downstream natural key already exists (edges are unique, invariant #3; includes a unique-index backstop under concurrency) |
| `POST /import/batches/{id}/rollback` | Batch has already been rolled back; or, while reverting, there are edges from later batches that reference fields of this batch (referential integrity conflict) |
| `POST /version-tags` | Tag name already exists (duplicate name) |
| `POST /version-tags/{name}/rollback` | Referential integrity conflict during revert (edges later than the tag reference fields that will be deleted) |

### 1.6 Time format

All time fields such as `created_at` / `updated_at` / `checked_at` are ISO8601 UTC text with second precision, of the form `2026-10-24T08:00:00+00:00` (`changes.now()` / `datetime.now(UTC).isoformat(timespec="seconds")`).

---

## 2. Authentication and users (`routes/auth.py`)

### 2.1 POST /auth/login

Log in and exchange credentials for a JWT. **The only anonymous endpoint.**

- Required role: anonymous
- Request body (`LoginIn`, `models.py`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| username | string | Yes | No length constraint | `"admin"` |
| password | string | Yes | No length constraint | `"admin123"` |

- Success response: `200`

| Field | Type | Description |
|---|---|---|
| access_token | string | JWT (HS256, valid for 24h by default) |
| token_type | string | Fixed `"bearer"` |
| username | string | Login username |
| role | string | `admin` / `editor` / `viewer` |

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "username": "admin",
  "role": "admin"
}
```

- Error scenarios: `401` username does not exist or password is wrong (uniformly "Invalid username or password", without distinguishing the two cases).

### 2.2 GET /auth/me

Current user information. Only decodes the JWT (`current_user` dependency); does not query the database or validate the role - it returns as long as the token has not expired.

- Required role: logged-in user (any role; the role is the snapshot inside the JWT)
- Request parameters: none
- Success response: `200` → `{"username": "admin", "role": "admin"}`
- Error scenarios: `401` missing/invalid/expired Bearer credentials.
- Note: the API overview in the root `README.md` does not list this endpoint, but it is registered in code (`routes/auth.py`); the code prevails.

### 2.3 POST /users

Create a user (admin user management, M3).

- Required role: admin
- Request body (`UserCreate`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| username | string | Yes | 2-64 characters | `"editor1"` |
| password | string | Yes | ≥6 characters (transmitted in plaintext, stored server-side as a pbkdf2 hash) | `"secret123"` |
| display_name | string\|null | No | None | `"Zhang San"` |
| role | string | Yes | Regex `^(admin\|editor\|viewer)$` | `"editor"` |

- Success response: `201` (`UserOut`):

| Field | Type |
|---|---|
| username | string |
| display_name | string\|null |
| role | string |

- Error scenarios: `409` username already exists (`User "{username}" already exists`); `422` field constraint not satisfied; `401`/`403` authentication failure or insufficient role.
- Note: only a create endpoint exists; there are no update/delete user endpoints (a role-change endpoint is a known gap, "Known gaps" in the root `README.md`).

### 2.4 GET /users

User list, ascending by `id`.

- Required role: admin
- Success response: `200` → array of `UserOut` (fields as above).
- Error scenarios: `401` / `403`.

---

## 3. Source files (`routes/files.py`, prefix `/files`)

Supported upload extensions (case-insensitive, determined by filename suffix): `csv`, `xlsx`, `json` (`ALLOWED_TYPES`). Content with the same sha256 is automatically deduplicated and the existing record is reused (design document §3.6).

### 3.1 POST /files

Batch-upload first-hand source files (step 1 of the three-step import).

- Required role: editor
- Request: `multipart/form-data`, form field name `files`, repeated, one file per item:

| Field | Type | Required | Meaning |
|---|---|---|---|
| files | file[] | Yes (at least 1) | Source files; the filename suffix must be csv/xlsx/json |

- Success response: `201` → array; each element is the registration record for that file (all `source_file` columns + a dedup flag):

| Field | Type | Description |
|---|---|---|
| id | integer | Source file ID (the import manifest `src_file` can reference it) |
| original_name | string | Original filename |
| storage_path | string | Storage path relative to `DATA_DIR` (`files/<first 2 chars of sha>/<sha256>.<ext>`; an internal server-side field, returned alongside the row) |
| sha256 | string | Content hash (64 hex characters), the dedup key |
| size_bytes | integer | Size in bytes |
| src_type | string | `csv` / `xlsx` / `json` |
| uploaded_by | string | Uploader username |
| created_at | string | ISO8601 UTC |
| deduped | boolean | `true` = content already existed and the old record was reused; `false` = newly registered |

```json
[
  {
    "id": 3,
    "original_name": "order_details.xlsx",
    "storage_path": "files/9f/9f86d071….xlsx",
    "sha256": "9f86d071…",
    "size_bytes": 20480,
    "src_type": "xlsx",
    "uploaded_by": "editor1",
    "created_at": "2026-10-24T08:00:00+00:00",
    "deduped": false
  }
]
```

- Error scenarios: `400` no file was passed (`Upload at least one file`); a file's suffix is not in the supported list; a file's content is empty (`File "{name}" is empty`); `413` a single file exceeds `MAX_UPLOAD_MB` (default 50MB); `401`/`403`. If any file fails, the whole batch fails; files processed earlier may already be registered (no batch-level rollback; repeated uploads are covered by sha256 deduplication).

### 3.2 GET /files

Source file list, ascending by `id`. **Does not include `storage_path`** (storage paths are not exposed, business rule #8).

- Required role: viewer
- Success response: `200` → array; element fields: `id`, `original_name`, `sha256`, `size_bytes`, `src_type`, `uploaded_by`, `created_at`.
- Error scenarios: `401`/`403`.

### 3.3 GET /files/{file_id}/download

Controlled source file download (returns the file body; `Content-Disposition` carries the original filename).

- Required role: viewer
- Path parameters:

| Parameter | Type | Required | Meaning |
|---|---|---|---|
| file_id | integer | Yes | Source file ID |

- Success response: `200`, binary file stream (not JSON).
- Error scenarios: `404` source file does not exist (`Source file {file_id} does not exist`).

---

## 4. Import (`routes/imports.py`)

Steps 2 and 3 of the three-step import: upload manifest → validation + persistence (bound to the same `import_batch`). Import rules (row-level rejections recorded in the report, duplicate merging, real-file verification) are in design document §3.5 and data model §4.

### 4.1 POST /import

Upload a manifest and run the import.

- Required role: editor
- Request: `multipart/form-data`:

| Field | Type | Required | Meaning |
|---|---|---|---|
| format | string (form) | Yes | `csv` / `xlsx` / `json` (case-insensitive) |
| source_file_ids | string (form) | Yes | Comma-separated source file IDs, e.g. `"3,4"`; must be ids returned by `POST /files` |
| manifest | file | Required for xlsx/json | xlsx: a workbook with both `datasets` and `lineage` sheets; json: `{"datasets": [], "lineage": []}` |
| manifest_datasets | file | Required for csv | `datasets.csv` (dataset and field manifest) |
| manifest_lineage | file | Required for csv | `lineage.csv` (lineage manifest) |

Manifest columns (`DATASET_COLUMNS` / `EDGE_COLUMNS` in `manifest.py`; CSV/XLSX headers and JSON object keys share these names):

- datasets: `dataset_id`, `dataset_name`, `field_name`, `field_type`, `src_file`, `src_type`, `src_locator`, `description`
- lineage: `from_dataset`, `from_field`, `to_dataset`, `to_field`, `transform`, `confidence`, `note`

Here `src_file` may be a source file library ID (number) or an original filename within the file set bound to this batch (must be unique); `src_locator` is the locator input (a JSON-string cell in CSV/XLSX, an object in a JSON manifest; structure in Appendix A1); a row-level error (e.g. `src_locator` is not JSON, `confidence` is not a number) does not fail the whole batch - that row is recorded in the report marked `rejected`.

- Success response: `201`

| Field | Type | Description |
|---|---|---|
| batch_id | integer | Import batch ID |
| version_no | integer | Version number (incrementing) |
| report | object | Import report (structure in Appendix A5) |

```json
{
  "batch_id": 7,
  "version_no": 3,
  "report": {
    "summary": { "total": 3, "ok": 2, "merged": 0, "rejected": 1 },
    "items": [
      { "status": "ok", "kind": "field", "ref": "ods_raw.order_id",
        "reason": null, "source_row": 2 },
      { "status": "rejected", "kind": "field", "ref": "ods_raw.bad_field",
        "reason": "Real-file verification failed: csv header \"no_such_header\" was not found in the first row of the source file (5 columns in total)",
        "source_row": 3 }
    ]
  }
}
```

- Error scenarios: `400` `source_file_ids` is not comma-separated numbers / is empty; the manifest file(s) required for the format are missing; `format` is invalid; manifest file-level parsing fails (XLSX missing `datasets`/`lineage` sheets, JSON root parse failure, CSV/XLSX file-level row-structure error); the manifest is completely empty; `404` some source file in `source_file_ids` does not exist; `422` missing `format` / `source_file_ids` form fields.
- Note: **row-level validation failures do not produce HTTP errors**; they become `rejected` items in the report (the invariant "no locator, no persistence" is guaranteed by row-level real-file verification).

### 4.2 GET /import/batches

Import batch list, descending by `version_no` (used by the version drawer).

- Required role: viewer
- Success response: `200` → array:

| Field | Type | Description |
|---|---|---|
| id | integer | Batch ID |
| version_no | integer | Version number |
| file_names | string[] | Source file names bound to this batch (already parsed from JSON into an array) |
| format | string | `csv` / `xlsx` / `json` |
| created_by | string | Importer |
| created_at | string | ISO8601 UTC |
| rolled_back_at | string\|null | Rollback time; `null` if not rolled back |

- Error scenarios: `401`/`403`.
- Note: `rolled_back_by` is not in this list response (the `SELECT` does not fetch that column); the API overview in the root `README.md` does not list this endpoint, but it is registered in code; the code prevails.

### 4.3 GET /import/batches/{batch_id}

Batch details (including the full import report).

- Required role: viewer
- Path parameter: `batch_id` (integer, required)
- Success response: `200` → all fields from 4.2, plus:

| Field | Type | Description |
|---|---|---|
| rolled_back_by | string\|null | Rollback performer |
| report | object\|null | Import report (Appendix A5; `null` when there is no report) |

- Error scenarios: `404` `Import batch {batch_id} does not exist`.
- Note: the API overview in the root `README.md` does not list this endpoint, but it is registered in code; the code prevails.

### 4.4 POST /import/batches/{batch_id}/rollback

Roll back by batch: revert all change_log entries of the batch (added→delete, updated→restore before, deleted→reinsert before); the batch records `rolled_back_at/by`.

- Required role: admin
- Path parameter: `batch_id` (integer, required)
- Success response: `200` → `{"batch_id": 7, "reverted": 25}` (`reverted` is the number of log entries reverted)
- Error scenarios: `404` batch does not exist; `409` batch has already been rolled back; `409` there are edges from later batches that reference fields of this batch - roll back the later batches first.

---

## 5. Datasets and field browsing (`routes/datasets.py`)

### 5.1 GET /datasets

Dataset list (the sidebar's two search targets, "Datasets / Fields", design document §5.1).

- Required role: viewer
- Success response: `200` → array, ascending by `id`:

| Field | Type | Description |
|---|---|---|
| id | string | Dataset ID (user-defined string primary key) |
| name | string\|null | Dataset name |
| field_count | integer | Field count (LEFT JOIN count) |
| field_names | string[] | Field name list (M2 contract increment, data model §9.1) |

```json
[
  { "id": "ods_raw", "name": "Raw order layer", "field_count": 3,
    "field_names": ["order_id", "amount", "buyer_name"] }
]
```

- Error scenarios: `401`/`403`.

### 5.2 GET /datasets/{dataset_id}

Dataset details and field list (including locator envelopes and source file names).

- Required role: viewer
- Path parameter: `dataset_id` (string, required)
- Success response: `200`

```json
{
  "id": "ods_raw",
  "name": "Raw order layer",
  "description": null,
  "fields": [
    {
      "name": "order_id",
      "field_type": "string",
      "description": "Order number",
      "src_locator": { "type": "csv", "input": { "header": "order_no" },
                       "resolved": { "column_index": 3, "header": "order_no" } },
      "source_file_id": 3,
      "source_file_name": "order_details.csv"
    }
  ]
}
```

- `fields[].src_locator` has been parsed from TEXT into a locator envelope object (Appendix A1); fields are sorted ascending by field name.
- Error scenarios: `404` `Dataset "{dataset_id}" does not exist`.
- Note: the API overview in the root `README.md` does not list this endpoint, but it is registered in code; the code prevails.

---

## 6. Lineage subgraph (`routes/lineage.py`; also includes legacy endpoints in `routes/imports.py`)

### 6.1 GET /lineage/subgraph

Fetch the N-hop lineage subgraph of a dataset/field (`GraphPayload`, implemented with a recursive CTE, design document §4.3).

- Required role: viewer
- Query parameters:

| Parameter | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| dataset | string | Yes | — | Seed dataset ID |
| field | string | No | — | Seed field name; when provided, traces at field level |
| hops | integer | No | 1-5, default 3 | Maximum number of hops |
| direction | string | No | `both` / `up` / `down`, default `both` | Trace direction |

- Seed semantics (`lineage.py`): a dataset seed expands along all connected edges (field-level + table-level); a field seed expands precisely along field-level edges, and **table-level edges are treated as fully connecting the fields of the datasets on both sides**.
- Success response: `200` → `GraphPayload` (Appendix A6; each `edges[]` item contains `id` - M3 edits/deletes locate by it, data model §9.1).
- Error scenarios: `404` seed dataset/field does not exist; `422` `hops` out of range or invalid `direction`.

### 6.2 GET /lineage/snapshot

Snapshot of the current full lineage state. **Legacy M1 verification endpoint** (the code comment explicitly states "for M1 verification; M2 will replace it with recursive CTE subgraph queries"), defined in `routes/imports.py`; new frontend features must not depend on it.

- Required role: viewer
- Success response: `200`

```json
{
  "datasets": [{ "id": "ods_raw", "name": "Raw order layer" }],
  "fields": [{ "dataset_id": "ods_raw", "name": "order_id",
               "field_type": "string", "source_file_id": 3,
               "description": "Order number" }],
  "edges": [{ "from_dataset": "ods_raw", "from_field": "order_id",
              "to_dataset": "dwd_order", "to_field": "order_no",
              "transform": "cast/trim", "confidence": 1.0,
              "source": "imported", "note": null }]
}
```

- Error scenarios: `401`/`403`.
- Note: the API overview in the root `README.md` does not list this endpoint, but it is registered in code; the code prevails.

---

## 7. Source preview (`routes/preview.py`)

### 7.1 GET /fields/{dataset_id}/{field_name}/preview

Open the managed source file according to the field's locator envelope and return the structured preview needed for the locator card highlight (design document §3.6 source verification closed loop).

- Required role: viewer
- Path parameters:

| Parameter | Type | Required | Meaning |
|---|---|---|---|
| dataset_id | string | Yes | Dataset ID |
| field_name | string | Yes | Field name |

- Success response: `200`

| Field | Type | Description |
|---|---|---|
| file | object | `{id, original_name, sha256, size_bytes, src_type, uploaded_by}` (M2 contract increment, data model §9.1; sha256 lets the frontend display the dedup basis) |
| verification | object\|null | `{status: "passed", version_no, checked_by, checked_at}` - information about the most recent import batch that passed real-file verification; `null` when there is no verification record (e.g. the field was persisted outside the import path) |
| locator | object | Locator envelope (Appendix A1) |
| preview | object | One of three forms selected by `src_type`, see below |

The three `preview` forms (`preview.py`):

| src_type | Fields |
|---|---|
| csv | `header: string[]` (first-row header), `column_index: integer` (1-based), `rows: string[][]` (at most 50 rows; short rows are padded on the right with empty strings) |
| xlsx | `sheet: string`, `header_rows: string[][]` (header rows, 0-n rows), `merged_ranges: string[]` (merged regions intersecting the visible area, e.g. `"B1:F1"`), `column_index: integer`, `row_start: integer`, `row_end: integer`, `rows: [][]` (first 50 data rows; cell values have been converted to JSON-serializable form) |
| json | `json_path: string`, `hits: integer` (total hit count), `samples: any[]` (first 10 hit values) |

```json
{
  "file": { "id": 3, "original_name": "order_details.csv", "sha256": "9f86d071…",
            "size_bytes": 2048, "src_type": "csv", "uploaded_by": "editor1" },
  "verification": { "status": "passed", "version_no": 3,
                    "checked_by": "editor1", "checked_at": "2026-10-24T08:00:00+00:00" },
  "locator": { "type": "csv", "input": { "header": "order_no" },
               "resolved": { "column_index": 3, "header": "order_no" } },
  "preview": { "header": ["dt", "buyer", "order_no"],
               "column_index": 3,
               "rows": [["2026-01-01", "alice", "A001"], ["2026-01-02", "bob", "A002"]] }
}
```

- Error scenarios: `404` dataset or field does not exist; `409` locator resolution failure (see the 409 summary in §1.5: missing file, type mismatch, sheet/column/row out of range, JSONPath with no hits, corrupted source file, etc.; `detail` is always a "... locator has become invalid" message, which the frontend displays directly).

---

## 8. Field editing (`routes/fields.py`, M3)

### 8.1 PATCH /fields/{dataset_id}/{field_name}

Manually correct a field's description / type / source locator. `src_locator` is the only field requiring real-file verification: it accepts a locator input or a full envelope, and `resolved` is always discarded and recomputed; if any step fails, 409 is returned and the field keeps its original value (transaction rollback). A successful edit writes change_log (`batch_id=NULL`, `actor=current user`) and can be reverted by a tag rollback.

- Required role: editor
- Path parameters: `dataset_id` (string), `field_name` (string), both required
- Request body (`FieldPatch`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| description | string\|null | No | At least one editable field must be provided | `"Order number"` |
| field_type | string\|null | No | Same as above | `"string"` |
| src_locator | object\|null | No | When provided, must not be `null` (a field must always remain traceable to its source); the value is a locator input (e.g. `{"column": 3}`) or a full envelope `{"type","input","resolved"}` (`resolved` is ignored and recomputed) | `{"header": "order_no"}` |

- Success response: `200` → the updated field object:

```json
{
  "dataset_id": "ods_raw",
  "name": "order_id",
  "field_type": "string",
  "source_file_id": 3,
  "src_locator": { "type": "csv", "input": { "header": "order_no" },
                   "resolved": { "column_index": 3, "header": "order_no" } },
  "description": "Order number",
  "updated_at": "2026-10-24T09:00:00+00:00"
}
```

- Behavior detail: when the submitted value is exactly the same as the current value, no change_log is written and the current value is returned directly (this no-change branch additionally carries three source-file columns - `storage_path` / `original_name` / `src_type` - an implementation branch difference; the frontend should ignore the extra fields).
- Error scenarios: `400` the request body provides no editable field; `src_locator: null` is passed explicitly; `404` field does not exist; `409` locator type inconsistent with the source file type, structure validation failure, real-file verification failure, source file not in managed storage (`detail` carries the reason text, displayed by the frontend); `422` field type mismatch.

---

## 9. Lineage edges (`routes/edges.py`, M3)

All three write operations write change_log (`batch_id=NULL`, op=`added`/`updated`/`deleted`) for history viewing and tag rollback. An edge's natural key is `(from_dataset, from_field, to_dataset, to_field)`; `from_field`/`to_field` being `null` means a table-level edge; **field-level/table-level is an either-or choice** (one empty and one non-empty → 400). `source` cannot be modified through this group of endpoints.

Edge object (Edge, Appendix A2) fields: `id, from_dataset, from_field, to_dataset, to_field, transform, confidence, source, note, created_by, updated_by, created_at, updated_at`.

### 9.1 POST /edges

Manually create an edge; `source` is fixed to `manual`.

- Required role: editor
- Request body (`EdgeCreate`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| from_dataset | string | Yes | ≥1 character, must not be empty after trim | `"ods_raw"` |
| from_field | string\|null | No | Must be empty or non-empty together with `to_field` | `"order_id"` |
| to_dataset | string | Yes | ≥1 character, must not be empty after trim | `"dwd_order"` |
| to_field | string\|null | No | Same as above | `"order_no"` |
| transform | string\|null | No | An empty string after trim is stored as `null` | `"cast/trim"` |
| confidence | number | No | 0-1, default `1.0` | `0.9` |
| note | string\|null | No | Same as transform | `"Manual addition"` |

- Success response: `201` → Edge object (`source: "manual"`):

```json
{
  "id": 12,
  "from_dataset": "ods_raw", "from_field": "order_id",
  "to_dataset": "dwd_order", "to_field": "order_no",
  "transform": "cast/trim", "confidence": 0.9,
  "source": "manual", "note": "Manual addition",
  "created_by": "editor1", "updated_by": "editor1",
  "created_at": "2026-10-24T09:00:00+00:00",
  "updated_at": "2026-10-24T09:00:00+00:00"
}
```

- Error scenarios: `400` `from_dataset`/`to_dataset` is empty after trim; `from_field`/`to_field` has one empty and one non-empty; `404` a referenced dataset or field does not exist (datasets are checked before fields); `409` an edge with the same natural key already exists (`A lineage edge with the same upstream/downstream natural key already exists (edges are unique, invariant #3)`, including a partial unique-index backstop under concurrency); `422` `confidence` out of range, etc.

### 9.2 PATCH /edges/{edge_id}

Modify an edge's `transform` / `note` / `confidence` (endpoints and `source` are immutable).

- Required role: editor
- Path parameter: `edge_id` (integer, required)
- Request body (`EdgePatch`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| transform | string\|null | No | At least one must be provided; an empty string after trim is stored as `null` | `"cast"` |
| note | string\|null | No | Same as above | `"reviewed in 2026-10"` |
| confidence | number\|null | No | 0-1; when provided, must not be `null` | `0.8` |

- Success response: `200` → Edge object (when there is no actual change, no change_log is written and the current value is returned directly).
- Error scenarios: `400` no editable field is provided; `confidence: null` is passed explicitly; `404` `Lineage edge {edge_id} does not exist`; `422` `confidence` out of range.

### 9.3 DELETE /edges/{edge_id}

Delete an incorrect edge; the before snapshot is written to change_log (`deleted`), so a tag rollback can restore it.

- Required role: editor
- Path parameter: `edge_id` (integer, required)
- Success response: `204` no response body
- Error scenarios: `404` `Lineage edge {edge_id} does not exist`.

---

## 10. Annotations (`routes/annotations.py`, M3)

Annotations are **append-only** business notes: only added, never modified, never written to change_log, and never deleted by version rollback (business rules / data model §9.4). `target_kind` + `target_id` form a polymorphic association (data model §5.2):

| target_kind | target_id format | Example |
|---|---|---|
| dataset | `<dataset_id>` | `ods_raw` |
| field | `<dataset_id>.<field_name>` (dataset IDs / field names may contain dots; the backend tries each dot position and takes the unique hit; ambiguity → 400) | `ods_raw.order_id` |
| edge | `<from>--><to>`; field-level `ds.f-->ds.f`, table-level `ds.*-->ds.*` (the shorthand `ds-->ds` omitting `.*` is also accepted; each side is split at the rightmost dot) | `ods_raw.order_id-->dwd_order.order_no`, `ods_raw.*-->dwd_order.*` |

### 10.1 POST /annotations

Append an annotation.

- Required role: editor
- Request body (`AnnotationCreate`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| target_kind | string | Yes | `dataset` / `field` / `edge` | `"field"` |
| target_id | string | Yes | 1-512 characters, format as in the table above | `"ods_raw.order_id"` |
| body | string | Yes | 1-4000 characters, must not be empty after trim | `"Definition includes refund orders from 2026-10"` |

- Success response: `201` → annotation object (Appendix A3):

```json
{
  "id": 5,
  "target_kind": "field",
  "target_id": "ods_raw.order_id",
  "body": "Definition includes refund orders from 2026-10",
  "author": "editor1",
  "created_at": "2026-10-24T09:30:00+00:00"
}
```

- Error scenarios: `400` `body` is empty after trim; `target_id` has an invalid format (a per-format error message); the field target is ambiguous; `404` target does not exist (dataset / field / lineage edge); `422` constraint not satisfied.

### 10.2 GET /annotations

Filter annotations by target and return them in append order (ascending `id`); with no parameters, returns all.

- Required role: viewer
- Query parameters:

| Parameter | Type | Required | Meaning |
|---|---|---|---|
| target_kind | string | No | `dataset` / `field` / `edge` |
| target_id | string | No | Combined with `target_kind` for exact targeting |

- Success response: `200` → array of annotation objects (fields as in the 10.1 response).
- Error scenarios: `422` invalid `target_kind` enum (validated by `Literal`).

---

## 11. Change history (`routes/changes.py`, M3)

### 11.1 GET /changes

Recent change log, descending by `id`; `before`/`after` are already parsed into JSON objects (snapshot structure in Appendix A4).

- Required role: viewer
- Query parameters:

| Parameter | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| entity_kind | string | No | `dataset` / `field` / `edge` | Filter by entity type |
| entity_key | string | No | — | Filter by entity key (format: dataset `<id>`, field `<ds>.<f>`, edge `<from>--><to>` with `*` for empty fields) |
| limit | integer | No | 1-500, default 50 | Maximum number of returned entries |

- Success response: `200` → array:

```json
[
  {
    "id": 88,
    "op": "updated",
    "before": { "dataset_id": "ods_raw", "name": "order_id", "field_type": "integer",
                "source_file_id": 3, "src_locator": "{…}", "description": null },
    "after": { "dataset_id": "ods_raw", "name": "order_id", "field_type": "string",
               "source_file_id": 3, "src_locator": "{…}", "description": "Order number" },
    "actor": "editor1",
    "created_at": "2026-10-24T09:00:00+00:00"
  }
]
```

> Note: in snapshots written by the import path, `src_locator` is **stringified JSON** (see the `{…}` placeholder in the example); the M3 manual-edit path also writes a string (`log_change` applies `json.dumps` to dicts). This endpoint only parses the outer `before`/`after`; the inner `src_locator` remains a string, and the frontend should `JSON.parse` it itself when needed. The response does not include the `entity_kind` / `entity_key` / `batch_id` columns.

- Error scenarios: `422` `limit` out of range, invalid `entity_kind` enum.

---

## 12. Versions and tags (`routes/version_tags.py`, M3)

### 12.1 POST /version-tags

Create a business tag: `change_seq` anchors to the current maximum change_log id (tags are kept permanently and are not written to change_log).

- Required role: editor
- Request body (`VersionTagCreate`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| name | string | Yes | 1-64 characters, must not be empty after trim | `"v1.0-launch-baseline"` |
| note | string\|null | No | An empty string after trim is stored as `null` | `"after first full import"` |

- Success response: `201`

```json
{ "name": "v1.0-launch-baseline", "note": "after first full import", "change_seq": 120,
  "created_by": "editor1", "created_at": "2026-10-24T10:00:00+00:00" }
```

- Error scenarios: `400` tag name is empty after trim; `409` `Version tag "{name}" already exists`; `422` length exceeds the limit.

### 12.2 GET /version-tags

Tag list, ascending by `id`.

- Required role: viewer
- Success response: `200` → array:

| Field | Type | Description |
|---|---|---|
| id | integer | |
| name | string | Tag name (unique) |
| note | string\|null | |
| batch_id | integer\|null | Informational record: the most recent import batch at creation time |
| change_seq | integer | Anchored maximum change_log id |
| created_by | string | |
| created_at | string | |

- Error scenarios: `401`/`403`.

### 12.3 GET /version-tags/diff

Net changes between two tags (the change_log range is merged by `(entity_kind, entity_key)`: the first entry's before is the start point and the last entry's after is the end point; entries added then deleted within the range are not counted).

- Required role: viewer
- Query parameters:

| Parameter | Type | Required | Meaning |
|---|---|---|---|
| from | string | Yes | Start tag name (query parameter name `from`, an alias in code) |
| to | string | Yes | End tag name |

- Success response: `200`

```json
{
  "summary": { "added": 2, "updated": 1, "deleted": 0 },
  "items": [
    { "entity_kind": "field", "entity_key": "ods_raw.amount",
      "op": "added", "before": null,
      "after": { "dataset_id": "ods_raw", "name": "amount", "…": "…" } }
  ]
}
```

- `items[]` fields: `entity_kind` (dataset/field/edge), `entity_key`, `op` (`added`/`updated`/`deleted`), `before`, `after` (snapshot structure in Appendix A4, may be `null`); sorted by `(entity_kind, entity_key)`.
- Error scenarios: `404` start or end tag does not exist; `400` the `from` tag is later than the `to` tag (`Start tag "{from}" is later than end tag "{to}"; the diff cannot be computed`).

### 12.4 POST /version-tags/{name}/rollback

Roll back to a tag: revert **all** change_log entries after `change_seq` (including manual edits). Log entries already reverted by a previous rollback are skipped (their batch has been rolled back, or they fall within a reverted range in `rollback_record`), so repeated rollbacks have no side effects and return 0; each call appends one `rollback_record` audit entry; import batches owning the reverted log entries are marked `rolled_back_at/by` in sync.

- Required role: admin
- Path parameter: `name` (string, required, tag name)
- Success response: `200` → `{"reverted": 25}` (`reverted` = number of log entries actually reverted this time; a repeated rollback skips already-reverted entries and returns `0`)
- Error scenarios: `404` `Version tag "{name}" does not exist`; `409` referential integrity conflict (`Rollback hit a referential integrity conflict: delete the lineage edges later than this tag that reference fields to be deleted first`).

---

## 13. AI (`routes/ai.py`, M4)

Permission tiers (revision R8 in document 08): `/ai/status`, `/ai/chat`, `/ai/chat/stream`, `GET /ai/description-drafts` are viewer+; `/ai/suggest` (including confirm/reject) and draft accept/reject are editor+ - AI suggestions cannot take effect directly (invariant #4). The **write-type tools** reachable by the model on the conversation path (`suggest_lineage` / `draft_descriptions`) re-validate the role at the tool layer: when triggered by a viewer, a tool error is returned to the model and no database write is performed.

### 13.1 GET /ai/status

LLM configuration status. `configured` semantics: if both `LLM_BASE_URL` and `LLM_MODEL` in the repository-root `.env` are **non-empty**, it is considered configured (`LLM_API_KEY` may be empty, to support local OpenAI-compatible services without authentication; `ai/llm.py::is_configured`). **Keys are never returned**.

- Required role: viewer
- Success response: `200`

```json
{ "configured": true, "model": "gpt-4o-mini" }
```

When not configured: `{ "configured": false, "model": null }`.

- Error scenarios: `401`/`403`.

### 13.2 POST /ai/chat

Natural-language conversation: the model calls tools via OpenAI-compatible function calling (`ai/tools.py`, 8 tools in total - 6 read-only: `search_fields` / `get_field_details` / `trace_lineage` / `get_field_history` / `mark_highlight` / `analyze_impact`; 2 write-type: `suggest_lineage` persists candidate edges, `draft_descriptions` persists description drafts; see 13.6 and Appendix A8), and after at most 5 tool-call rounds it is forced to wrap up with a final answer. **Tool-layer role guard** (R8 in document 08): write-type tools validate the caller's role; when triggered by a viewer, a tool error is returned to the model and no database write is performed. **Tool result budget** (R10 in document 08): a single result JSON over 4000 characters is truncated before being appended back to the conversation (the `graph`/`highlights` extraction for canvas linkage happens before truncation and is unaffected). The system prompt is fixed by the backend (including the focus context); the frontend cannot pass the `system` role. `mark_highlight` is the canvas linkage signal: the model declares fields to highlight in the frontend (at most 8; existence-checked and deduplicated), and the backend aggregates them into the response `highlights`; see [06_AI canvas linkage highlight fix](./06_ai-canvas-highlight-fix.md).

- Required role: viewer
- Request body (`AiChatIn`):

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| messages | object[] | Yes | 1-50 entries | Conversation history; array elements below |
| focus | object\|null | No | — | Current focused scope, injected into the system prompt |

`messages[]` elements (`AiChatMessage`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| role | string | Yes | Only `user` / `assistant` | `"user"` |
| content | string | Yes | 1-8000 characters | `"Where does order_no in the orders table come from?"` |

`focus` (`AiFocus`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| dataset | string | Yes | 1-256 characters | `"dwd_order"` |
| field | string\|null | No | ≤256 characters | `"order_no"` |

- Success response: `200`

```json
{
  "answer": "order_no is derived from ods_raw.order_id via cast/trim (1 hop, confidence 1.0); the source field is located at column 3 of \"order_details.csv\" (header order_no).",
  "tool_trace": [
    { "tool": "search_fields", "args": { "q": "order_no" }, "ok": true },
    { "tool": "trace_lineage",
      "args": { "dataset": "dwd_order", "field": "order_no", "direction": "up", "hops": 3 },
      "ok": true },
    { "tool": "mark_highlight",
      "args": { "fields": [ { "dataset": "ods_order", "field": "order_no" } ] },
      "ok": true }
  ],
  "graph": { "datasets": [ /* GraphPayload, same as GET /lineage/subgraph */ ],
             "edges": [ /* … */ ] },
  "highlights": [ { "dataset": "ods_order", "field": "order_no" } ]
}
```

| Field | Type | Description |
|---|---|---|
| answer | string | The model's final answer (the content text after tool wrap-up) |
| tool_trace | object[] | Tool call trace; each item is `{tool: string, args: object, ok: boolean}`; `ok=false` means the tool execution failed (the error message is only returned to the model and does not appear in the trace) |
| graph | object | Optional. The `GraphPayload` (Appendix A6) returned by the **last** successful `trace_lineage`, for canvas-linked rendering; omitted when no graph was queried in this conversation |
| highlights | object[] | Optional. Highlight fields aggregated by `mark_highlight` (at most 8, deduplicated), each item `{dataset: string, field: string}`; the frontend uses this to apply the red trace chain on the canvas. Omitted when the model did not call this tool (backward compatible) |

- Error scenarios: `503` LLM not configured (`LLM not configured: set LLM_BASE_URL / LLM_MODEL in the repository-root .env (fill in LLM_API_KEY as required by the provider)`); `502` LLM upstream unreachable / non-200 response / invalid response structure; `422` empty messages, invalid role, content too long, etc.; `429` rate limit triggered (10 requests per 60s per user, R11 in document 08).

### 13.6 POST /ai/chat/stream

SSE streaming conversation (M5): request body and permissions same as 13.2; the response is `text/event-stream` with frame format `event: <type>\ndata: <json>\n\n`. Event types:

| event | data meaning |
|---|---|
| token | `{delta: string}` - incremental text of the final answer (no text is emitted during tool rounds) |
| tool | `{tool, args, ok}` - tool call checkpoint (`args` are the arguments given by the model) |
| suggest | `{count, candidates[]}` - emitted after `suggest_lineage` candidates are persisted; when triggered by a viewer the tool is blocked by R8 and this event is not produced |
| drafts | `{items[]}` - emitted after `draft_descriptions` drafts are generated |
| done | Complete payload: `{answer, graph?, highlights?, suggestions?, drafts?, tool_trace}` |
| error | `{status, detail}` - orchestration fallback error (`503`/`502`/`500`, semantics same as 13.2) |

Heartbeat and stop-on-disconnect (R9 in document 08): when there is a gap of more than 15s between events, an SSE comment frame `: ping` is emitted (the frontend parser looks up the `data: ` line per frame; comment frames are safely ignored and imperceptible to the UI); after the client disconnects, a cancellation signal is passed into the orchestration loop and **rounds that have not yet started are no longer executed** (including write-type tool persistence); candidates/drafts already persisted are not automatically rolled back.

- Required role: viewer
- Rate limit: 10 requests per 60s per user (R11 in document 08)
- Error scenarios: `429` rate limited (with `Retry-After`); in-stream `error` event (`503`/`502`/`500`); `422` request body validation.

### 13.3 POST /ai/suggest

Heuristically generate candidate edges (**no LLM call**; runs offline): exact equality after name normalization (lowercase + strip underscores) → `confidence 0.7`; containment relation (the shorter one ≥3 characters) → `0.6`. The requested dataset/field is upstream (from), and similar fields in other datasets are downstream (to); existing edges are excluded (including reverse direction); candidates are **persisted** with `source='ai'` and written to change_log(`added`), descending by confidence, at most 20; when an edge with the same natural key already exists it is skipped, so repeated calls do not persist duplicates.

- Required role: editor
- Request body (`AiSuggestIn`):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| dataset | string | Yes | 1-256 characters, must not be empty after trim | `"ods_raw"` |
| field | string\|null | No | ≤256 characters; when omitted, candidates are generated for all fields of the dataset | `"order_id"` |

- Success response: `200`

```json
{
  "candidates": [
    { "from_dataset": "ods_raw", "from_field": "order_id",
      "to_dataset": "dwd_order", "to_field": "order_id",
      "confidence": 0.7,
      "reason": "Same-name field (case- and underscore-insensitive): order_id and order_id" },
    { "from_dataset": "ods_raw", "from_field": "user_id",
      "to_dataset": "dim_user", "to_field": "user_id_flag",
      "confidence": 0.6,
      "reason": "Highly similar field names (containment after case- and underscore-insensitive comparison): user_id and user_id_flag" }
  ]
}
```

- Rate limit: 6 requests per 60s per user (R11 in document 08).

> Note: the `reason` text has two fixed forms - same-name match (0.7) is "Same-name field (case- and underscore-insensitive): X and Y", and containment (0.6) is "Highly similar field names (containment after case- and underscore-insensitive comparison): X and Y"; the normalization rule is lowercase + strip underscores (`ai/suggest.py::normalize_field_name`).

- Error scenarios: `400` `dataset` is empty after trim; `404` dataset does not exist (`Dataset "{dataset}" does not exist`) or the specified field does not exist; `422` constraint not satisfied.

### 13.4 POST /ai/suggest/confirm

Manually confirm an AI candidate edge (invariant #4): change the `source='ai'` edge to `manual` and write change_log(`updated`).

- Required role: editor
- Request body (`AiEdgeKeyIn`, the candidate edge natural key, shared by confirm / reject):

| Field | Type | Required | Constraints | Example |
|---|---|---|---|---|
| from_dataset | string | Yes | 1-256 characters, non-empty after trim | `"ods_raw"` |
| from_field | string\|null | No | ≤256; must be empty or non-empty together with `to_field` | `"order_id"` |
| to_dataset | string | Yes | 1-256 characters | `"dwd_order"` |
| to_field | string\|null | No | ≤256 | `"order_id"` |

- Success response: `200` → `{"edge": <Edge object>}` (`source` is now `"manual"`; fields as in Appendix A2)
- Error scenarios: `400` `from_dataset`/`to_dataset` is empty after trim; one field is empty and the other non-empty; `404` `AI suggested edge does not exist or has already been processed (only source='ai' candidates can be confirmed/rejected)` - already confirmed, already rejected, or originally a manual/imported edge all return 404.

### 13.5 POST /ai/suggest/reject

Reject an AI candidate edge: delete that `source='ai'` edge and write change_log(`deleted`).

- Required role: editor
- Request body: same as 13.4 (`AiEdgeKeyIn`)
- Success response: `204` no response body
- Error scenarios: same as 13.4 (`400` / `404`).

### 13.7 GET /ai/description-drafts

List AI description drafts (M5; supplementary record of the draft-flow contract in documents 03/07). Filterable by dataset / status.

- Required role: viewer
- Query parameters: `dataset` (string, optional), `status` (string, optional; only `pending` / `accepted` / `rejected` allowed)
- Success response: `200`

```json
{ "items": [ { "id": 1, "dataset_id": "ods_raw", "field_name": "order_id",
               "draft": "Order number, from column 3 of the source file…", "model": "qwen-plus",
               "status": "pending", "created_at": "…", "decided_at": null } ] }
```

- Error scenarios: `400` `status only allows pending/accepted/rejected`.

### 13.8 POST /ai/description-drafts/{draft_id}/accept

Accept a description draft: write an `annotation` (target_kind='field', body with the provenance prefix "AI description accepted | model=…") and set the draft to `accepted`. The original `field.description` is not modified (original imports and human insights remain separate).

- Required role: editor
- Success response: `200` → `{"draft": <draft object, fields as in 13.6>}`
- Error scenarios: `404` `Description draft #{id} does not exist`; `409` `Draft #{id} has already been processed ({status})`

### 13.9 POST /ai/description-drafts/{draft_id}/reject

Reject a description draft: set it to `rejected`; drafts are no longer regenerated for that field (regeneration requires a field content change).

- Required role: editor
- Success response: `204` no response body
- Error scenarios: same as 13.7 (`404` / `409`).

---

## 14. Data structure appendix

The composite structures below follow `models.py`, `db.py`, `locator.py`, `changes.py`, `import_service.py`, `ai/chat.py`, and data model §4.

### A1 src_locator locator envelope

Unified envelope: `{ "type": <src_type>, "input": <user-provided>, "resolved": <materialized from real-file parsing> }`. `type` must match the `src_type` of the source_file the field belongs to (validated at the application layer; mismatch → 409 / preview 409); `resolved` only materializes the parse result, while verification traces are carried by `change_log`/`import_batch` (the preview response's `verification` field returns the most recent verification information).

| type | input fields (`models.py` locator models) | resolved fields (`locator.py` materialization) |
|---|---|---|
| csv | `column: integer|null` (≥1), `header: string|null` (one of the two) | `column_index: integer`, `header: string|null` |
| xlsx | `sheet: string` (required), `column: string|null` (e.g. `"D"`), `row_start: integer|null` (≥1), `row_end: integer|null` (≥1), `header_path: string[]|null` (multi-level header), `header_rows: integer|null` (≥1); one of `column` and `header_path` | `column_index: integer`, `column: string`, `row_start: integer|null`, `row_end: integer|null`, `merged_anchors: [{value, anchor, range}]` (merged regions normalized to the top-left anchor) |
| json | `json_path: string` (required) | `hits: integer` (JSONPath hit count) |

```json
{ "type": "xlsx",
  "input": { "sheet": "orders", "header_path": ["Product info", "Order number"], "header_rows": 2, "row_start": 3 },
  "resolved": { "column_index": 4, "column": "D", "row_start": 3, "row_end": null,
                "merged_anchors": [{ "value": "Product info", "anchor": "B1", "range": "B1:F1" }] } }
```

### A2 edge (lineage edge object)

Returned by `GET/POST/PATCH /edges*`, `GET /lineage/subgraph` (the latter only the first 9 business fields), and `/ai/suggest/confirm`:

| Field | Type | Description |
|---|---|---|
| id | integer | Primary key (used to locate for subgraph/edit/delete, M2 contract increment) |
| from_dataset / to_dataset | string | Upstream/downstream dataset ID |
| from_field / to_field | string\|null | Upstream/downstream field name; both `null` means a table-level edge |
| transform | string\|null | Transform description |
| confidence | number | 0-1 |
| source | string | `imported` / `manual` / `ai` |
| note | string\|null | Remark |
| created_by / updated_by | string\|null | Audit columns (not included in the subgraph response) |
| created_at / updated_at | string | Audit columns (not included in the subgraph response) |

### A3 annotation (annotation object)

`{id: integer, target_kind: "dataset"|"field"|"edge", target_id: string, body: string, author: string, created_at: string}`. Append-only: no update/delete endpoints; not deleted by rollback.

### A4 change_log.before / after (row snapshot)

A fixed set of **business columns** (`FIELD_SNAPSHOT_KEYS` / `EDGE_SNAPSHOT_KEYS` in `changes.py`), excluding id, timestamps, and audit columns; the key sets are identical for added/updated/deleted of the same entity, allowing direct comparison and whole-row reinsertion:

- field: `dataset_id, name, field_type, source_file_id, src_locator, description`
- edge: `from_dataset, from_field, to_dataset, to_field, transform, confidence, source, note`
- `before`/`after` being `null` means that side has no state (before of added, after of deleted).

### A5 import_batch.report (import report)

```json
{ "summary": { "total": 120, "ok": 100, "merged": 8, "rejected": 12 },
  "items": [ { "status": "ok|merged|rejected",
               "kind": "field|edge",
               "ref": "ods_raw.order_id",
               "reason": "…",        // required for rejected; ok may be "unchanged"; merged is the overwrite description
               "source_row": 15 } ] }
```

`status` values: `ok` (added/updated/unchanged), `merged` (duplicate of the same natural key within the same batch; the later one overwrites transform/note/confidence), `rejected` (row-level rejection, including real-file verification failure). `ref`: fields are `dataset_id.field_name`; edges are `ds.field-->ds.field` (`*` when a field is empty).

### A6 GraphPayload (lineage subgraph)

Shared by `GET /lineage/subgraph` and the `graph` field of `POST /ai/chat` (design document §5.2 "AI graph output and the canvas use the same rendering protocol"):

```json
{
  "datasets": [
    { "id": "ods_raw", "name": "Raw order layer",
      "fields": [
        { "name": "order_id", "field_type": "string", "description": "Order number",
          "src_locator": { /* A1 envelope */ },
          "source_file": { "id": 3, "original_name": "order_details.csv" } }
      ] }
  ],
  "edges": [ /* first 9 business fields of A2 */ ]
}
```

- `datasets[].fields[]`: **all** fields of the datasets in the closure; when a locator envelope is corrupted it degrades to `{"type": null, "input": null, "resolved": null}` (the whole graph does not fail with 500).
- `edges[]`: all edges between the datasets in the closure (both table-level and field-level).

### A7 Three forms of the source preview payload

See the `preview` field table in §7.1 (csv / xlsx / json).

### A8 AI chat messages and tool call trace

- Request messages: `{role: "user"|"assistant", content: string}` (`system` is fixed by the backend; the frontend must not pass it).
- Tool call trace: `{tool: string, args: object, ok: boolean}`; the toolset has 8 tools in total (`ai/tools.py`, current state M4/M5):
  - 6 read-only: `search_fields`, `get_field_details`, `trace_lineage`, `get_field_history`, `mark_highlight` (canvas linkage signal), `analyze_impact`;
  - 2 write-type: `suggest_lineage` (candidate edges persisted with `source='ai'`), `draft_descriptions` (description drafts persisted to `description_draft`) - validated at the tool layer by the caller's role; when triggered by a viewer, a tool error is returned to the model and no database write is performed (R8 in document 08).
- Conversation orchestration details (at most 5 tool rounds; the 6th request is sent without tools to force wrap-up; `graph` takes the last successful graph query; tool results >4000 characters are truncated before being appended back; the context token budget is trimmed in whole blocks; stop on client disconnect) are in `ai/chat.py` and [08 review fix batch](./08_review-fix-batch-2026-10-26.md).

### A9 SystemGraphPayload (system-level lineage subgraph, new in design)

Shared by `GET /lineage/systems` and the system-level AI tool `trace_system_lineage`; isomorphic to A6 `GraphPayload`; the frontend selects a renderer by `level`:

```json
{
  "level": "system",
  "seed": { "id": "dw_platform", "name": "Data warehouse" },
  "hops": 3,
  "direction": "both",
  "systems": [
    { "id": "crm", "name": "CRM customer system", "system_type": "source",
      "owner": "Customer platform team", "dataset_count": 2, "is_seed": false, "hop": 2 }
  ],
  "edges": [
    { "from_system": "crm", "to_system": "order_center",
      "origin": "derived", "dataset_edge_count": 1,
      "system_edge_id": null, "source": "derived",
      "confidence": 1.0, "transform": null, "note": null }
  ],
  "graph_state": "clean",
  "engine": "kuzu"
}
```

| Field | Description |
|---|---|
| `systems[].hop` | Shortest hop count from the seed system (`min(length(p))`); 0 for the seed |
| `edges[].origin` | `explicit` (explicit edge only) / `derived` (projected from dataset edges only) / `both` (both present; explicit attributes take precedence) |
| `edges[].dataset_edge_count` | Number of dataset-level edges contributing to this edge (deduplicated by `from_dataset→to_dataset`); 0 for pure explicit edges |
| `edges[].system_edge_id` | Explicit edge primary key; `null` for pure projected edges (Kùzu internally uses `-1` as a sentinel; the API layer uniformly converts it to `null`) |
| `engine` | `kuzu` (main path) or `cte` (fallback); together with `graph_state`, used by the frontend for badge display |

> Evidence drill-down is not inlined in this response: after the frontend selects a system edge, it calls `GET /systems/{id}` or filters `GET /datasets` by the systems on both ends, then calls `GET /lineage/subgraph` to obtain the underlying dataset edges, avoiding the system graph response growing with the amount of evidence.

---

## 15. Designed but not implemented

Design document §6.2 once mapped the AI toolset to REST endpoints; the M4 implementation changed to "tools encapsulated in the backend + function calling" (§7 of ./04_frontend-backend-boundaries.md). The following REST endpoints are **not implemented**; their capabilities are provided by equivalent means, and whether to add REST equivalents is a `[TBD-BE]` item for the backend to decide in a later milestone:

| Designed endpoint (design document §6.2) | Status | Current equivalent capability |
|---|---|---|
| `GET /search?q=` (search_fields mapping) | Not implemented `[TBD-BE]` | AI tool `search_fields` (`ai/tools.py`); frontend sidebar search uses client-side filtering of `field_names` from `GET /datasets` |
| `GET /fields/{ds}.{f}` (get_field_details mapping; field details + locator + annotations) | Not implemented `[TBD-BE]` | Combination of `GET /datasets/{dataset_id}` (field list) + `GET /fields/{ds}/{f}/preview` (locator resolution and verification) + `GET /annotations?target_kind=field` (annotations); the AI tool `get_field_details` retrieves everything in one call |
| `GET /lineage/trace` (trace_upstream / trace_downstream mapping) | Not implemented `[TBD-BE]` | `GET /lineage/subgraph?direction=up|down`; AI tool `trace_lineage` |

Also: design document §3.6 mentions that source files are "accessed with permission control via `GET /files/{id}/download` / `/preview`" - the file-level `/preview` is not implemented; source preview is delivered as the **field-level** `GET /fields/{dataset_id}/{field_name}/preview` (previews the highlighted area according to the locator, rather than by file ID).

### 15.1 System-level lineage endpoints (added in the 2026-11 design; not implemented `[TBD-BE]`)

The following endpoints correspond to design document §4.7 / data model §9.6 and are **not currently implemented in code**; the contract is finalized first for M6 implementation and frontend integration. Roles and error semantics follow §1 General conventions.

| Method | Path | Minimum role | Semantics |
|---|---|---|---|
| GET | `/systems?q=&system_type=` | viewer | System list; `q` performs a LIKE on id/name/description; returns `id/name/system_type/owner/dataset_count` |
| GET | `/systems/{system_id}` | viewer | System details: attributes + dataset list + upstream/downstream summary + explicit edges; 404 if not found |
| POST | `/systems` | editor | Create a system; duplicate `id` → 409; invalid `system_type` → 422 |
| PATCH | `/systems/{system_id}` | editor | Update `name/description/system_type/owner`; 404 if not found |
| DELETE | `/systems/{system_id}` | admin | Delete a system; delete explicit edges first, set `dataset.system_id` to NULL; write a deleted log; 404 if not found |
| PATCH | `/datasets/{dataset_id}` | editor | Set/clear `system_id`; 404 if the system does not exist; write a dataset updated log |
| GET | `/lineage/systems?system=&hops=&direction=` | viewer | System-level N-hop subgraph; `hops` 1-5, default 3; `direction` both/up/down; returns `SystemGraphPayload` (A9); 404 if the seed does not exist |
| POST | `/ai/suggest/systems` | editor | System-level AI candidate edges; persisted to `system_edge` with `source='ai'` |
| POST | `/ai/suggest/systems/confirm` | editor | Convert to `manual` by `(from_system,to_system)` |
| POST | `/ai/suggest/systems/reject` | editor | Delete AI system candidate edges, 204 |

**Key conventions**:

- The `GET /datasets` and `GET /datasets/{dataset_id}` responses gain nullable `system_id` / `system_name`; `GET /datasets?system_id=` provides optional filtering (backward compatible);
- System edges from `GET /lineage/systems` must return `origin` (explicit/derived/both) and `dataset_edge_count`; pure projected edges have `system_edge_id=null`;
- If a system graph query fails, it falls back to the `v_system_edge` recursive CTE like the existing graph routes, the `engine` field returns `"cte"`, and no 5xx is returned (except on primary-database failure);
- System-level write operations (systems/ownership/explicit edges) set `graph_state.state='dirty'` after the primary-database commit, and read paths automatically rebuild Kùzu.

---

## 16. README and code discrepancy record

The API overview in the root `README.md` omits the following 4 registered endpoints (this document includes them per the code, and each endpoint section notes it); all other endpoints, roles, and paths match the code:

| Endpoint | Status |
|---|---|
| `GET /auth/me` | Implemented in code (`routes/auth.py`); not listed in README |
| `GET /import/batches/{batch_id}` | Implemented in code (`routes/imports.py`); not listed in README |
| `GET /datasets/{dataset_id}` | Implemented in code (`routes/datasets.py`); not listed in README |
| `GET /lineage/snapshot` | Implemented in code (`routes/imports.py`, legacy M1 verification); not listed in README |

---

## 17. Endpoint summary

**36** endpoints in total (excluding FastAPI's built-in `/docs` and `/openapi.json`). Role denotes the minimum role declared by the code dependency; "Logged in" means any valid JWT (no role tier check). The system-level lineage endpoints in §15.1 (`/systems`, `/lineage/systems`, `PATCH /datasets/{id}`, `/ai/suggest/systems*`) are newly added in the 2026-11 design and **not yet implemented**; they are not counted in this table. This table and the count must be updated after implementation.

| # | Method | Path | Role | Description |
|---|---|---|---|---|
| 1 | POST | /auth/login | anonymous | Log in and issue a JWT |
| 2 | GET | /auth/me | logged in | Current user (JWT decode only) Note: not listed in README |
| 3 | POST | /users | admin | Create a user |
| 4 | GET | /users | admin | User list |
| 5 | POST | /files | editor | Batch-upload source files (sha256 dedup) |
| 6 | GET | /files | viewer | Source file list |
| 7 | GET | /files/{file_id}/download | viewer | Controlled source file download |
| 8 | POST | /import | editor | Upload a manifest and import (multipart) |
| 9 | GET | /import/batches | viewer | Import batch list |
| 10 | GET | /import/batches/{batch_id} | viewer | Batch details (including report) Note: not listed in README |
| 11 | POST | /import/batches/{batch_id}/rollback | admin | Roll back by batch |
| 12 | GET | /datasets | viewer | Dataset list (including field_names) |
| 13 | GET | /datasets/{dataset_id} | viewer | Dataset details and fields Note: not listed in README |
| 14 | GET | /lineage/subgraph | viewer | N-hop lineage subgraph (GraphPayload) |
| 15 | GET | /lineage/snapshot | viewer | Full snapshot (legacy M1 verification) Note: not listed in README |
| 16 | GET | /fields/{dataset_id}/{field_name}/preview | viewer | Field source preview (csv/xlsx/json) |
| 17 | PATCH | /fields/{dataset_id}/{field_name} | editor | Field editing (locator re-verification; 409 on failure) |
| 18 | POST | /edges | editor | Manually create an edge (source=manual) |
| 19 | PATCH | /edges/{edge_id} | editor | Update transform/note/confidence |
| 20 | DELETE | /edges/{edge_id} | editor | Delete an edge (204) |
| 21 | POST | /annotations | editor | Append an annotation (polymorphic target) |
| 22 | GET | /annotations | viewer | Annotation query (filterable by target) |
| 23 | GET | /changes | viewer | Change history (descending id) |
| 24 | POST | /version-tags | editor | Create a business tag |
| 25 | GET | /version-tags | viewer | Tag list |
| 26 | GET | /version-tags/diff?from=&to= | viewer | Net changes between tags |
| 27 | POST | /version-tags/{name}/rollback | admin | Roll back to a tag (idempotent) |
| 28 | GET | /ai/status | viewer | LLM configuration status |
| 29 | POST | /ai/chat | viewer | AI conversation (function calling + graph output) |
| 30 | POST | /ai/suggest | editor | Generate and persist AI candidate edges (source=ai) |
| 31 | POST | /ai/suggest/confirm | editor | Confirm a candidate edge and convert it to manual |
| 32 | POST | /ai/suggest/reject | editor | Reject and delete a candidate edge (204) |
| 33 | POST | /ai/chat/stream | viewer | AI streaming conversation (SSE: token/tool/suggest/drafts/done/error + ping heartbeat; write-type tools pass through the role guard) |
| 34 | GET | /ai/description-drafts | viewer | Description draft list (dataset/status filtering) |
| 35 | POST | /ai/description-drafts/{id}/accept | editor | Accept a draft → annotation + accepted |
| 36 | POST | /ai/description-drafts/{id}/reject | editor | Reject a draft → rejected (204) |
