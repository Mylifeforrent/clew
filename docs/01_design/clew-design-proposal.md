# Clew Design Plan (field-level AI data lineage tool; named Clew since 2026-10, early working name LineageLite)

> Based on research findings from two open-source solutions, OpenMetadata and DataHub, this is a lightweight data lineage tool oriented toward "file import + field-level source file location + AI assistance".
> Unconfirmed business facts in this document are marked with `[ASSUMPTION]` / `[TBD-*]`.
>
> **2026-11 storage redesign**: The storage layer evolved from a single SQLite database into a **dual embedded database** of **SQLite (single source of truth) + Kùzu 0.11.3 (lineage graph traversal layer)**; all REST contracts remain unchanged, with no frontend impact. For design motivation, the Kùzu graph model, dual-write consistency, and archival risk mitigation, see §4.3–4.5 and §10 (decisions #7/#8).
>
> **2026-11 system-level lineage extension (design finalized, implementation pending)**: An optional "system" layer is added above datasets/fields to show **upstream/downstream relationships between systems**. System ownership and system edge attributes are stored in SQLite, while system-level path traversal goes through Kùzu; system edges can either be automatically projected from dataset-level lineage (derived) or explicitly registered (explicit), and the two are merged into a single relationship view without introducing a new storage stack or rendering protocol. See §4.7, §5.3, §6.2, and §10 (decisions #9/#10).

---

## 1. Findings from the Two Open-Source Solutions

### 1.1 OpenMetadata Core Design

| Dimension | Design | Key evidence |
|---|---|---|
| Data model | Entity-agnostic "entity + edge" graph: every asset is an Entity; lineage edges carry a `LineageDetails` JSON (including column-level mapping `fromColumns[] -> toColumn + function`, raw SQL, source enum) | `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json` |
| Edge storage | `entity_relationship` table (fromId/toId/fromEntity/toEntity/relation), with `LineageDetails` stored entirely in a JSON column; ES additionally stores a "reverse lineage" document for search | `bootstrap/sql/migrations/.../v001__create_db_connection_info.sql` |
| Collection | Push-based: Python ingestion (SQL parser, dbt, Airflow, and 18+ connectors) + REST API + OpenLineage. **Lineage can only be exported as CSV, not imported from CSV** | `ingestion/src/metadata/ingestion/lineage/`, `LineageResource.java:632` |
| Query | Dual path: DB recursive expansion (depth≤3) + ES BFS (large graphs use four strategies: Small/Medium/Large/Streaming) | `LineageRepository.java`, `AbstractLineageGraphBuilder.java` |
| Versioning | Entity `Major.Minor` versioning + change_event table; **lineage edges independently emit `ENTITY_LINEAGE_ADDED/UPDATED/DELETED` change events**; edge IDs are generated as a deterministic hash of fromId+toId | `type/changeEventType.json:45`, `LineageRepository.java:2082` |
| Frontend | **reactflow**; column-level edges use sourceHandle/targetHandle, with `tracedColumns` highlighting; the new scene/hydrate architecture layers by LAYER/ASSET/FIELD and batch-fetches entities to eliminate N+1 | `openmetadata-ui/.../Lineage/Lineage.tsx`, `EntityLineageCanvas.tsx` |
| AI | Official MCP server (21 read/write tools, including `get_entity_lineage`, `root_cause_analysis`, `create_lineage`); output is deliberately verbose (full SQL + column-level mappings) for AI consumption | `openmetadata-mcp/src/main/java/org/openmetadata/mcp/tools/` |
| Deployment | Starts with four components—MySQL + Elasticsearch + Java backend + ingestion container—and targets enterprise-grade platforms | `docker/docker-compose-quickstart/` |

### 1.2 DataHub Core Design

| Dimension | Design | Key evidence |
|---|---|---|
| Data model | Lineage is an Aspect (`UpstreamLineage`) on an entity; the PDL annotation `@Relationship(isLineage=true)` declares edges, which the system automatically materializes into the ES graph index `graph_service_v1`; field-level uses `FineGrainedLineage`: **many-to-many + transformOperation + confidenceScore(0~1)**; schemaField is a first-class entity | `metadata-models/.../dataset/UpstreamLineage.pdl`, `FineGrainedLineage.pdl` |
| Storage pipeline | MCP event → Kafka/REST → GMS → MySQL `metadata_aspect_v2` (urn+aspect+version+JSON) → MCL → MAE consumer writes ES graph/search indices | `metadata-io/.../EbeanAspectDao.java:81` |
| Versioning | Three layers: MCP pre-write proposals (with CAS version) → MCL post-write logs (previous/next values) → aspect row-level history (latest is always version=0, history increments); supports **rollback by ingestion run**; edges carry createdOn to support PIT time lookback | `metadata-models/.../mxe/`, `EbeanAspectDao.java:643`, `TimelineServiceImpl.java` |
| Collection | YAML recipe (source→transformer→sink) framework; SQL lineage is based on sqlglot; **JSON files can be imported (file source/sink round-trip); CSV can only enrich descriptions/tags, not import lineage** | `metadata-ingestion/src/datahub/ingestion/source/file.py`, `csv_enricher.py` |
| Query | GraphQL → GraphService → ES graph index hop-by-hop BFS (sharding, budget, timeout truncation) + `searchAcrossLineage` translates filters into ES queries | `ESGraphQueryDAO.java:56`, `GraphQueryPITDAO.java` |
| Frontend | Also **reactflow** (lineageV3): `ColumnLineageControl` column-level edges, `LineageExplorer` collapse/expand, `manualLineage/` manual editing | `datahub-web-react/src/app/lineageV3/` |
| AI | `datahub-agent-context` PyPI package: wraps search/fetch details/**trace lineage**/changes as MCP + LangChain tools for AI agents | `datahub-agent-context/README.md` |
| Deployment | Kafka + MySQL + OpenSearch + GMS/frontend, 7 services; has a datahub-lite single-file embedded lightweight variant | `docker/quickstart/docker-compose.quickstart-profile.yml` |

### 1.3 Implications for This Design

**Borrow**:
1. Entity+edge with details attached to edges (column-level mapping, transform function, source enum) — OpenMetadata's `entityLineage.json` structure can be directly trimmed and reused;
2. `FineGrainedLineage`'s `confidenceScore` — AI-inferred lineage must carry confidence and be promoted after human confirmation; this is the correct form of "AI optimization";
3. Each edge records its source (Manual/Imported/AIInferred) + edge-level change event + deterministic edge ID — a cheap version management scheme;
4. reactflow's sourceHandle/targetHandle column-level edges — both solutions validated this approach;
5. MCP/tool-based interface (verbose lineage output + column-level scope trimming) — the correct interface form for AI conversation consumption of lineage.

**Avoid**:
1. Kafka + ES/OpenSearch dual writes and denormalization — still insist on no message queue, no search cluster, and no service-based middleware; but shrink DataHub's "MySQL + ES graph index" form to "SQLite + embedded graph database Kùzu": SQLite as the single source of truth, with lineage topology stored in Kùzu as a **derived index that can be rebuilt at any time** (see 4.3–4.5), gaining native variable-length path query capability without introducing any operational component;
2. PDL/AVRO/JSON Schema compile-time codegen chain and multi-module engineering — pydantic models suffice;
3. Hardcoded depth≤3 recursion + per-node N+1 queries — go straight to "graph engine batch variable-length traversal (Kùzu Cypher primary + CTE fallback) + single hydrate", so the frontend gets the full subgraph in one request;
4. The gap that CSV cannot import lineage — this design makes "files as first-class citizens for import" a core feature.

---

## 2. Goals and Scope

**Goals**: A field-level data lineage tool that a single person or small team can operate independently:
- Users import CSV / XLSX / JSON data they have organized themselves (not first-hand);
- Each field carries a precise location in the original file (file path + worksheet/row/column / JSONPath), for others to trace back and verify;
- Relational database storage with version management;
- Visual lineage graph (node/field collapse, field-level edges);
- **System-level upstream/downstream view**: after assigning datasets to business systems, users can view inter-system upstream/downstream on the same canvas; system edges can come from automatic projection of dataset-level lineage or explicit registration, and can drill down to dataset/field evidence;
- AI chat to query lineage and generate graphs dynamically;
- Manual correction and supplementary notes based on first-hand materials.

**Non-goals** (explicitly trimmed from the heavyweight capabilities of the two solutions):
- No SQL parsing for automatic collection, no scheduler/connector ecosystem;
- No service-based components such as Elasticsearch/OpenSearch; search uses SQLite FTS5 / LIKE, graph traversal uses embedded Kùzu (see 4.3–4.5);
- No fine-grained object-level ACL; multi-user adopts a "workspace-level RBAC (admin / editor / viewer) + full operation audit" model (see 4.6). If dataset-level privacy/authorization is needed in the future, introduce a `dataset_acl` table extension.

**Tech stack** (following personal default preferences):
- Backend: Python + FastAPI + uv; storage is a **dual embedded database**—SQLite (single source of truth for metadata/fields/versions/search, with a reserved Postgres upgrade path, writing to a compatible SQL subset) + Kùzu 0.11.3 (dedicated traversal layer for lineage graphs, in-process Cypher, no service process);
- The graph database uses Kùzu **final archived release 0.11.3** (repository archived read-only in 2025-10, MIT, PyPI wheels cover cp38–cp314 including macOS arm64): features are frozen but availability is unaffected; its role is a "derived layer that can be removed wholesale"—it can be fully rebuilt from SQLite at any time, and one can also fall back to the pure SQLite recursive CTE path (risk mitigation in 4.5);
- Frontend: React + TypeScript + Vite + Tailwind + shadcn/ui, graph rendering with **@xyflow/react (reactflow 11+)**;
- AI: OpenAI-compatible Chat API + function calling (tools are thin wrappers over this system's REST API); provider and model configured via repository-root `.env` (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`), `.env.example` committed, `.env` added to .gitignore, secrets never committed;
- Auth: JWT (username/password login), passwords stored only as salted hashes.

---

## 3. Import Data Format Specification (Requirement 1)

Designed as **two file types**: `dataset manifest` (describes nodes and fields) and `lineage relationships` (describes edges). A single submission is bound to one import batch. User data is mostly second-hand transformed data, so the core of the format specification is: **every field must carry a "source file locator"**.

### 3.1 Dataset Manifest (datasets & fields)

Each row describes one field in one dataset:

| Column | Required | Description |
|---|---|---|
| `dataset_id` | Yes | Dataset unique identifier (user-defined string, e.g. `dwd_order`) |
| `dataset_name` | No | Display name |
| `field_name` | Yes | Field name (unique within the dataset) |
| `field_type` | No | Type description (free text) |
| `src_file` | **Yes** | Identifier of the referenced **managed source file** (see 3.6): source file library ID or original file name (must be uniquely locatable within the uploaded file set bound to this import batch) |
| `src_type` | **Yes** | `csv` / `xlsx` / `json`, determines the locator structure |
| `src_locator` | **Yes** | Location within the source file (structure see 3.2) |
| `description` | No | Field description |
| `system_id` | No | Owning system identifier (see 3.7); absent means unassigned. The reference must exist in this batch's `systems` manifest or the existing `system` table |

### 3.2 Source File Locator `src_locator` (validated by `src_type`)

```jsonc
// src_type = csv: field = one column of the original CSV
{ "column": 3 }                    // column ordinal (1-based)
{ "header": "order_no" }           // or header name (choose one, validated on import)

// src_type = xlsx: field = one column of a worksheet, optionally with a data row range
{ "sheet": "Order Details", "column": "D", "row_start": 2, "row_end": 15000 }

// src_type = xlsx + multi-level header (Multi-header):
// header_path matches header rows by level; a merged parent header is automatically expanded to cover all its columns
{ "sheet": "Orders", "header_path": ["Product Info", "Order No."], "header_rows": 2, "row_start": 3 }

// src_type = json: field = some path in the JSON document
{ "json_path": "$.data.items[*].order_no" }
```

> Design rationale: OpenMetadata's FQN system has no `file:line`-level location; this is the differentiating core of this design. Locators are stored in a JSON column, but **structurally validated per src_type on import**; a row failing validation is rejected entirely with a readable error report (file name, row number, reason).

**XLSX merged cell / complex header normalization rules** (executed uniformly during locator parsing):

1. **Anchor normalization**: Any cell falling inside a merged region has its locator normalized to the region's **top-left anchor**; storage records both the anchor address and the merged range (`anchor: "D2", merged_range: "D2:G8"`), ensuring a one-to-one correspondence between "the merged cell the user sees" and "the stored locator";
2. **Multi-level header expansion**: `header_path` matches row by row by level; if a header at some level is a merged cell, all columns it covers are considered to belong to that parent (e.g. if row 1 "Product Info" merges over columns B:F, then `["Product Info","Order No."]` continues matching "Order No." in row 2 within the B:F range);
3. **Materialization of parse results**: On import, openpyxl parses the real file and materializes the `header_path` resolution into a concrete `column + row_start`, stored together with anchor information in `src_locator`—so even if the source file's headers are later modified, historical locators remain viewable (while the validation step reports "locator no longer valid").

### 3.3 Lineage Relationships (lineage)

Each row describes one field-level lineage edge (dataset-level edges are automatically derived from field-level edges; table-level-only entries are also allowed):

| Column | Required | Description |
|---|---|---|
| `from_dataset` / `from_field` | Yes | Upstream; empty `from_field` means table-level lineage |
| `to_dataset` / `to_field` | Yes | Downstream |
| `transform` | No | Transform description (SQL snippet/formula/text description), borrowing OpenMetadata's `function` + `sqlQuery` |
| `confidence` | No | 0~1 confidence, borrowing DataHub `FineGrainedLineage.confidenceScore`; default 1.0 |
| `note` | No | Remarks |

### 3.4 Carrying the Three Physical Formats

| Format | Carrying |
|---|---|
| CSV | Two files: `datasets.csv` + `lineage.csv`, UTF-8 |
| XLSX | One workbook with two sheets: `datasets` / `lineage` (cells can carry comments, suitable for business users) |
| JSON | Single file: `{ "datasets": [...], "lineage": [...] }`, fields correspond one-to-one with the table above, `src_locator` is a nested object |

The importer normalizes everything into the same pydantic models (`DatasetFieldRecord` / `LineageEdgeRecord`); subsequent processing is format-agnostic.

### 3.5 Import Validation Rules

1. Structural validation: missing required columns, `src_type` and `src_locator` structure mismatch → reject;
2. **Real-file verification** (source files are managed, see 3.6): on import, open the first-hand file directly for mechanical verification—whether the sheet exists, whether `header_path`/`column` can be resolved, merged cell normalization, whether `json_path` can retrieve a value. Rows failing verification enter the report and are rejected; this step turns "is the user's hand-filled locator correct" from manual checking into automatic system checking;
3. Reference validation: datasets/fields referenced by lineage must exist in this batch or an existing version;
4. Duplicate conflict: duplicate `from→to` field pairs are merged (later ones overwrite transform/note) and listed in the report;
5. Produce an **import report** (per-item success/skipped/failed + failure reason + real-file verification result), borrowing the ingestion report pattern; the report itself is downloadable as JSON.

### 3.6 Managed Source File Upload

Source files (first-hand materials) are managed by the system, no longer stored only as path references:

- **Upload API**: `POST /files` (multipart, batch supported), recording original file name, size, uploader;
- **File library table**: `source_file` (see 4.1), deduplicated by **sha256**—the same file uploaded multiple times references one record (lineage scenarios often have multiple fields from the same source file);
- **Storage backend**: local `data/files/` by default (directory configured via `.env`); storage paths are not exposed directly; access is permission-controlled via `GET /files/{id}/download` / `/preview`; the backend is abstracted into an interface, with an S3/MinIO-compatible implementation reserved `[TBD-INFRA]` (determined by the deployment environment; M1 implements local first);
- **Import flow** becomes three steps: ① upload source files (get a file set) → ② upload manifest (datasets/lineage, `src_file` references files in the set) → ③ validate + persist (bound to the same `import_batch`);
- **Source verification loop**: after clicking a locator card, users can **preview the corresponding region of the source file** directly in the system (highlighting sheet / header path / column and row range / JSONPath matched value), with no need to locate the original file.

### 3.7 System Manifest and System-Level Lineage (Optional Extension)

The system layer is **optional**: when no system manifest is provided, the system-level view is empty and dataset/field-level functionality is entirely unaffected. When provided, the system manifest and system-level lineage are persisted under the same `import_batch` and participate in versions and rollback.

**System manifest (systems)**:

| Column | Required | Description |
|---|---|---|
| `system_id` | Yes | System unique identifier (user-defined, e.g. `crm` / `dw_platform`) |
| `system_name` | No | Display name |
| `system_type` | No | `source` (business source system) / `application` (business application) / `warehouse` (data warehouse/lake) / `bi` (analytics/reporting) / `external` (external/third-party) / `other`; default `other` |
| `owner` | No | Business owner (free text, not used in permission decisions) |
| `description` | No | System description |

**System-level lineage (system_lineage)**:

| Column | Required | Description |
|---|---|---|
| `from_system` / `to_system` | Yes | Upstream/downstream system identifiers; must exist in this batch's `systems` or the existing `system` table; self-loops prohibited |
| `transform` | No | Description of the inter-system interface/processing method (e.g. "T+1 batch file", "Kafka real-time sync") |
| `confidence` | No | 0~1, default 1.0; AI suggested edges < 1.0 |
| `note` | No | Remarks |

**Three physical formats**:

- CSV: in addition to `datasets.csv` / `lineage.csv`, optional `systems.csv` + `system_lineage.csv`;
- XLSX: optional `systems` / `system_lineage` two sheets;
- JSON: `{ "systems": [...], "datasets": [...], "lineage": [...], "system_lineage": [...] }`.

**Relationship to automatic projection**: `system_lineage` only registers coarse-grained relationships that **cannot be derived from dataset-level lineage** (e.g. "Finance system → Data Warehouse: monthly reconciliation Excel"). System relationships derivable from dataset edges need not be written by hand; at query time, `v_system_edge` merges "explicit edges ∪ projected edges" into a single relationship view (see 4.7). When the same system pair has both an explicit edge and a projected edge, the explicit edge's `transform/confidence/source/note` take precedence, and the projected edge's dataset edge count is returned as evidence.

**Validation rules**:

1. System identifiers are unique; `system_type` enum is valid;
2. The `system_id` reference of a dataset row must exist (this batch or an existing version), otherwise the row is rejected with a reason;
3. System-level lineage upstream/downstream must exist, and `from_system = to_system` is prohibited; duplicates for the same system pair use later-overwrites `transform/confidence/note` and are counted in the report as `merged`;
4. System-level lineage does not require dataset-level evidence to exist—it is itself a "coarse-grained relationship instance";
5. The import report adds `kind=system|system_edge` entries, following the per-item ok/merged/rejected structure of 3.5.

---

## 4. Storage and Version Management (Requirement 2): SQLite Source of Truth + Kùzu Lineage Graph

### 4.1 Table Structure (common to SQLite/Postgres)

```sql
-- Users (multi-user RBAC)
user(id INTEGER PK AUTOINCREMENT,
     username TEXT UNIQUE NOT NULL,
     password_hash TEXT NOT NULL,          -- salted hash, never plaintext
     display_name TEXT,
     role TEXT NOT NULL CHECK(role IN ('admin','editor','viewer')),
     created_at)

-- Source file management (first-hand material file library)
source_file(id INTEGER PK AUTOINCREMENT,
            original_name TEXT NOT NULL,
            storage_path TEXT NOT NULL,     -- actual storage path, not exposed
            sha256 TEXT UNIQUE NOT NULL,   -- dedup key: store one copy per file
            size_bytes INTEGER,
            src_type TEXT NOT NULL CHECK(src_type IN ('csv','xlsx','json')),
            uploaded_by TEXT NOT NULL,
            created_at)

-- Datasets (nodes)
dataset(id TEXT PK,            -- i.e. dataset_id
        name TEXT, description TEXT,
        created_at, updated_at)

-- Fields (with source file locator)
field(id INTEGER PK AUTOINCREMENT,
      dataset_id TEXT NOT NULL REFERENCES dataset(id),
      name TEXT NOT NULL,
      field_type TEXT,
      source_file_id INTEGER NOT NULL REFERENCES source_file(id),
      src_locator TEXT NOT NULL,      -- JSON: locator + materialized real-file parse result (anchor/merged range/row/column)
      description TEXT,
      UNIQUE(dataset_id, name))

-- Lineage edges (table-level + field-level in one table; field is NULL for table-level edges)
edge(id INTEGER PK AUTOINCREMENT,
     from_dataset TEXT NOT NULL, from_field TEXT NULL,
     to_dataset   TEXT NOT NULL, to_field   TEXT NULL,
     transform TEXT, confidence REAL DEFAULT 1.0,
     source TEXT NOT NULL CHECK(source IN ('imported','manual','ai')),
     note TEXT,
     created_by TEXT, updated_by TEXT,
     created_at, updated_at,
     UNIQUE(from_dataset, from_field, to_dataset, to_field))
-- Deterministic semantics: one edge per from→to (equivalent to OpenMetadata's (fromId,toId,relation) primary key)

-- Import batch = version (borrowing DataHub's ingestion run)
import_batch(id INTEGER PK, version_no INTEGER NOT NULL UNIQUE,  -- v1, v2, ...
             file_names TEXT, format TEXT, report TEXT,  -- import report JSON
             created_by TEXT NOT NULL,
             created_at)

-- Version business tag (release version number, e.g. v2.1-r1)
version_tag(id INTEGER PK,
            name TEXT UNIQUE NOT NULL,       -- business tag name
            note TEXT,                       -- tag description (e.g. "Q3 metric definition correction release")
            batch_id INTEGER,                 -- corresponding import batch at tag time
            change_seq INTEGER NOT NULL,      -- position in change_log (time-point anchor)
            created_by TEXT NOT NULL, created_at)

-- Field-level/edge-level overlay: edit notes and manual corrections
annotation(id INTEGER PK, target_kind TEXT CHECK(target_kind IN ('field','edge','dataset')),
           target_id TEXT,          -- field:"ds.field" / edge:"from->to" / dataset:id
           body TEXT NOT NULL, author TEXT, created_at)

-- Change log (borrowing OpenMetadata ENTITY_LINEAGE_* change event + DataHub MCL)
change_log(id INTEGER PK, batch_id INTEGER NULL,  -- associated import batch; NULL for manual edits
           entity_kind TEXT, entity_key TEXT,
           op TEXT CHECK(op IN ('added','updated','deleted')),
           before TEXT, after TEXT,   -- JSON snapshot
           actor TEXT, created_at)
```

> The 2026-11 system-level lineage adds two tables, `system` / `system_edge`, and adds a nullable `system_id` to `dataset`; see 4.7.1 for the complete DDL and §2.13/§2.14 of the Data Model for column-by-column definitions. They belong to the same SQLite source of truth as the existing tables and do not change the "single process + dual embedded databases" deployment form.

### 4.2 Version Management Design
Uses four layers: **"current state + import batches + version tags + change log"**, rather than full snapshots (the most economical and rollback-capable approach for small-to-medium data volumes):

1. **Import creates a new version**: Each import creates an `import_batch` with an incrementing `version_no` (v1, v2...);
2. **Pre-write proposal / post-write log** (a lightweight version of DataHub's approach): Every row change from import or edit writes `change_log` (op + before/after JSON); batches and logs naturally support "**rollback by version**"—reverse-delete the added rows produced by that batch and restore updated rows to their before state;
3. **Version business tags**: Tags can be applied at any time (e.g. `v2.1-r1 / Q3 metric definition correction release`), anchoring a `change_seq` position. **Rollback to a tag = undo all change_log entries after that seq**; **diff between tags = change_log range comparison**; tags are created by editor or above and retained permanently;
4. **Edit source traceability**: The `source` field on edges distinguishes `imported` (from user files) / `manual` (manual correction) / `ai` (AI inference, confidence < 1), resolving to a specific user together with `created_by`.

### 4.3 Kùzu Lineage Graph (topology derived layer, added 2026-11)

**Responsibility boundary (an iron rule)**: SQLite is the single source of truth (metadata, fields, edges, versions, audit all in SQLite); Kùzu stores only **lineage topology + a few filter columns** and is "a graph index that can be fully rebuilt from SQLite at any time". It occupies the position of the ES `graph_service_v1` graph index in DataHub's architecture, merely shrunk from a service-based search engine to an in-process embedded graph database.

**Selection highlights**:

- Kùzu is an embedded property graph database (in the form of "the SQLite/DuckDB of graph databases"): no service process, no port, starts with the Python process, and is ready via `pip install kuzu`;
- Native Cypher supports **variable-length paths** (`*1..n`) and path functions, exactly the core operators of lineage traversal—SQLite recursive CTEs can also do it, but variable hop control, path deduplication, and per-hop filtering all have to be hand-expanded;
- The archived final release 0.11.3 includes the built-in `algo` extension (cycle detection, PageRank, etc.), reserving a native algorithm entry point for "impact ranking" style AI tools;
- Archival risk accepted (see §10 decision #8): MIT + complete source code + wheels available on all platforms; frozen features have no impact on stable workloads such as lineage graphs; and Kùzu data can **always be derived from SQLite**, so in the worst case wholesale removal reverts to the CTE single-database solution with no data loss risk.

**Graph model DDL** (nodes store only identity keys and display names; all full metadata is fetched from SQLite):

```cypher
CREATE NODE TABLE Dataset (id STRING, name STRING, PRIMARY KEY (id));
CREATE NODE TABLE Field   (id STRING, name STRING, PRIMARY KEY (id));  -- id = "<dataset_id>.<field_name>", consistent with the natural key in §5.2

CREATE REL TABLE LINEAGE_FIELD (FROM Field TO Field,
    edge_id INT64,          -- SQLite edge.id: stable key linking back to the primary DB (edits/deletes/promotions locate by it)
    source STRING,          -- imported / manual / ai (needed for canvas filtering)
    confidence DOUBLE);     -- confidence (needed for low-confidence filtering)
CREATE REL TABLE LINEAGE_TABLE (FROM Dataset TO Dataset,
    edge_id INT64, source STRING, confidence DOUBLE);
```

> Kùzu relation table endpoints are fixed, so field-level/table-level lineage is split into two REL tables (semantically equivalent to SQLite `edge`'s single-table NULL-field model; mapping rules see §10 of the Data Model). Business attributes such as transform/note/annotation **do not enter the graph**—queries first traverse the graph for topology and edge_id, then hydrate from SQLite, keeping the dual-write drift surface minimal.

### 4.4 Graph Traversal: Kùzu Cypher Primary Path + Recursive CTE Fallback

Lessons from the two solutions: OpenMetadata's initial version hardcoded depth≤3 + N+1 queries; DataHub uses an ES graph index + sharding budget. This design's query routing:

| Query | Engine | Description |
|---|---|---|
| Metadata/search/details/history | **SQLite** | Field details, annotation, change_log, FTS5/LIKE search always go to the primary DB |
| Lineage topology (trace/subgraph/impact) | **Kùzu (primary)** | Cypher variable-length paths retrieve the N-hop subgraph in one go; after hitting edge_id, hydrate from SQLite |
| Lineage topology (fallback) | SQLite recursive CTE | Automatically switches when Kùzu is unavailable / the graph state is dirty and rebuild fails (same REST contract) |

Core query shapes (shared by `trace_lineage` / `get_subgraph` / `analyze_impact`):

```cypher
-- 1-hop upstream (field detail panel)
MATCH (src:Field)-[r:LINEAGE_FIELD]->(f:Field {id: $fid})
RETURN src.id, r.edge_id, r.confidence ORDER BY r.confidence DESC;

-- Full N-hop upstream chain (variable-length path, hop limit injected from the server-side whitelist)
MATCH p = (src:Field)<-[:LINEAGE_FIELD*1..3]-(f:Field {id: $fid})
RETURN src.id, r.edge_id, length(p) AS hop ORDER BY hop;

-- Downstream impact surface (analyze_impact tool)
MATCH p = (f:Field {id: $fid})-[:LINEAGE_FIELD*1..5]->(down:Field)
RETURN down.id, length(p) AS hop;
```

Query results are still assembled into the same `GraphPayload` (nodes + edges + fields) and returned; **the REST contract and frontend rendering protocol remain completely unchanged**—engine swaps are transparent to the frontend. The recursive CTE implementation is retained in `lineage.py` as the fallback path and is not removed.

### 4.5 Dual Writes and Consistency: SQLite as the Single Source of Truth

All write paths (import, canvas editing, AI suggestion confirm/reject, rollback) dual-write in the order "**primary database first, graph database second, mark dirty on failure**":

```
Write request → ① SQLite transaction (edge + change_log, etc.)
              → on success → ② Kùzu transaction (CREATE/DELETE corresponding Rel)
                             ├─ success → respond 200 (normal)
                             └─ failure → graph_state.state = 'dirty' → still respond 200 (derived-layer failure does not block business writes)
Lineage read request → graph_state is clean → go to Kùzu
                     → is dirty → automatically trigger a full rebuild (seconds) → continue if successful; otherwise fall back to CTE
```

- **Why the primary database first**: The authenticity of write operations is guaranteed by SQLite + change_log; if Kùzu goes down, only graph query performance is lost, with no loss of business data—this is the direct benefit of defining Kùzu as a "derived layer" rather than a "joint source of truth";
- **Full rebuild instead of incremental sync**: This design's data scale is small (within tens of thousands of edges); a rebuild = full export from SQLite `edge` → clear REL tables → Kùzu `COPY FROM` bulk import, completing in seconds and **idempotent with no drift accumulation**; per-row incremental sync is deliberately avoided (the sync logic itself is a drift source). change_log watermark-based incremental optimization will be introduced when data volume grows in the future `[TBD-BE]`;
- **State and audit**: The single-row `graph_state` table (SQLite) records the `last_edge_id` watermark, `state('clean'|'dirty')`, and `rebuilt_at`; `/health` and the canvas top bar show a graph state badge (normal / rebuilding / CTE fallback), and rebuild actions write `change_log` (`entity_kind='graph'`) for traceability;
- **Drift audit**: Provide a `clew graph audit` command: compare the Kùzu edge set with the SQLite edge set (by edge_id set difference); on mismatch, mark dirty and rebuild; a background task runs it once after each import completes.

### 4.6 Users and Permissions (Multi-User)

JWT authentication + workspace-level RBAC with three roles; all write operations (import, edit, annotation, tagging) record the operator in change_log / each table's `created_by`:

| Role | Permissions |
|---|---|
| `viewer` | Browse the lineage graph, view field details and source file preview, AI read-only Q&A (trace/search/get_subgraph) |
| `editor` | viewer + upload source files, import manifests, canvas editing (corrections/connections/change locators), annotation, create version tags, confirm AI suggested edges |
| `admin` | editor + user and role management, rollback by batch/tag, delete datasets, reset imports |

Implemented as FastAPI dependency-injected role guards (each route declares its minimum role); no row-level/object-level ACL; author/actor in `annotation` and `change_log` are both taken from the JWT and cannot be forged.

### 4.7 System-Level Lineage: A "Third-Layer View" on the Same Layered Architecture (new design for 2026-11)

**Current-state assessment (2026-11-16)**: The current data model only has `dataset` / `field` / `edge`, with no system entity, dataset ownership, or system edges; the API and canvas also only offer dataset/field-level views. Therefore **the current system does not support out-of-the-box inter-system upstream/downstream display**. Bypassing this by "modeling systems as datasets and simulating with table-level edges" would lose system catalog semantics (type/owner), dataset ownership, system edge origin and evidence counts, system-level N-hop traversal, etc., and is not recommended as a formal solution.

**Positioning**: System-level upstream/downstream does not start from scratch; it lifts the existing layering "entity attributes and entry search → relational DB; relationship instances and path traversal → graph DB" up one level as-is:

| Layer | Entity attributes / entry search (SQLite) | Relationship instances / path traversal (Kùzu) | Rendering protocol |
|---|---|---|---|
| System level | `system` catalog, `dataset.system_id` ownership, system search | `System` node + `LINEAGE_SYSTEM` relationship, N-hop system paths | `SystemGraphPayload` |
| Dataset level | `dataset` metadata, `v_dataset_edge` projection | `Dataset` node + `LINEAGE_TABLE` relationship | `GraphPayload` |
| Field level | `field` metadata, locator, annotation, history | `Field` node + `LINEAGE_FIELD` relationship | `GraphPayload` |

All three layers share the same FastAPI process, the same SQLite source of truth, the same Kùzu derived graph, and the same canvas interactions; **no new services, message queues, or search clusters are added**. The system view simply changes the `GraphPayload` node type from dataset/field to system, and the frontend selects the renderer by `level`.

**4.7.1 Table Structure**

```sql
-- System catalog (entity attributes + entry search in SQLite)
system(id TEXT PRIMARY KEY,        -- user-defined identifier, e.g. crm / dw_platform
       name TEXT, description TEXT,
       system_type TEXT NOT NULL DEFAULT 'other'
         CHECK(system_type IN ('source','application','warehouse','bi','external','other')),
       owner TEXT,                 -- business owner, free text
       created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

-- Dataset ownership (optional; NULL = no system assignment)
ALTER TABLE dataset ADD COLUMN system_id TEXT REFERENCES system(id) ON DELETE SET NULL;

-- Explicit system-level lineage (only coarse-grained relationships that cannot be derived from dataset edges)
system_edge(id INTEGER PK AUTOINCREMENT,
            from_system TEXT NOT NULL REFERENCES system(id),
            to_system   TEXT NOT NULL REFERENCES system(id),
            transform TEXT, confidence REAL DEFAULT 1.0 CHECK(0 <= confidence <= 1),
            source TEXT NOT NULL CHECK(source IN ('imported','manual','ai')),
            note TEXT,
            created_by TEXT, updated_by TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK(from_system <> to_system));
CREATE UNIQUE INDEX uq_system_edge ON system_edge(from_system, to_system);
```

**4.7.2 Relationship View: Explicit Edges ∪ Projected Edges**

System-level relationships have two sources, merged at query time, **not dual-written**:

1. **explicit**: Inter-system relationships registered in `system_edge`, which may carry an interface description/confidence/source; dataset-level evidence is not required;
2. **derived**: Map the datasets on both ends of `edge` to systems via `dataset.system_id`, aggregating with `COUNT(DISTINCT dataset pair)` into one system edge; dataset edges within the same system do not produce a system edge (self-loops excluded);
3. **both**: The same system pair has both an explicit edge and a projected edge; the explicit edge's business attributes take precedence, and the projected edge only provides the `dataset_edge_count` evidence count.

```sql
CREATE VIEW v_system_edge AS
WITH derived AS (
  SELECT d_from.system_id AS from_system,
         d_to.system_id   AS to_system,
         COUNT(DISTINCT e.from_dataset || '->' || e.to_dataset) AS dataset_edge_count,
         MIN(e.confidence) AS confidence
  FROM edge e
  JOIN dataset d_from ON d_from.id = e.from_dataset
  JOIN dataset d_to   ON d_to.id   = e.to_dataset
  WHERE d_from.system_id IS NOT NULL
    AND d_to.system_id IS NOT NULL
    AND d_from.system_id <> d_to.system_id
  GROUP BY d_from.system_id, d_to.system_id
),
explicit AS (
  SELECT id, from_system, to_system, transform, confidence, source, note
  FROM system_edge
)
SELECT e.from_system, e.to_system,
       CASE WHEN d.from_system IS NOT NULL THEN 'both' ELSE 'explicit' END AS origin,
       COALESCE(d.dataset_edge_count, 0) AS dataset_edge_count,
       e.id AS system_edge_id,
       e.transform, e.confidence, e.source, e.note
FROM explicit e
LEFT JOIN derived d ON d.from_system = e.from_system AND d.to_system = e.to_system
UNION ALL
SELECT d.from_system, d.to_system, 'derived', d.dataset_edge_count,
       NULL, NULL, d.confidence, 'derived', NULL
FROM derived d
LEFT JOIN explicit e ON e.from_system = d.from_system AND e.to_system = d.to_system
WHERE e.id IS NULL;
```

> Design trade-off: Projected edges **are not persisted**, avoiding dual-write drift where "dataset edges changed but system edges were forgotten"; system-level edge counts stay below tens of thousands, so the cost of the view + graph rebuild is negligible. Explicit edges are persisted because they carry business information that projection cannot express (interface method, owner, coarse-grained relationships without dataset details) and must participate in versions and rollback.

**4.7.3 Kùzu Graph Model**

```cypher
CREATE NODE TABLE System (id STRING, name STRING, system_type STRING, PRIMARY KEY (id));
-- Dataset node gains a system_id property (empty string means unassigned), used for system drill-down and ownership filtering
CREATE NODE TABLE Dataset (id STRING, name STRING, system_id STRING, PRIMARY KEY (id));

CREATE REL TABLE LINEAGE_SYSTEM (FROM System TO System,
    system_edge_id INT64,        -- explicit edge = system_edge.id; purely projected edge = -1
    origin STRING,               -- explicit / derived / both
    source STRING,               -- imported / manual / ai / derived
    confidence DOUBLE,
    dataset_edge_count INT64);   -- projected evidence count (0 for explicit edges)
```

- Each `LINEAGE_SYSTEM` relationship corresponds to one row of `v_system_edge`; on rebuild it is fully `COPY FROM` the view, following the same "SQLite single source of truth + Kùzu rebuildable derived layer" process as dataset/field graphs (4.5);
- Purely projected edges use `system_edge_id = -1` (Kùzu attributes use a sentinel value rather than NULL, for easier audit and filtering); explicit edges link back to `system_edge.id`, which editing/deletion/promotion locate by;
- `Dataset.system_id` is an ownership attribute, not a lineage relationship: system drill-down filters datasets by it, and it does not participate in `LINEAGE_*` traversal.

**4.7.4 Query Routing and Cycle Handling**

| Query | Engine | Description |
|---|---|---|
| System list/details/search | SQLite | `system` + `dataset.system_id` aggregation; `search_systems` uses LIKE |
| System N-hop upstream/downstream | Kùzu (primary) | `MATCH p=(s:System {id:$sid})<-[:LINEAGE_SYSTEM*1..n]-(up:System)`, downstream in the same direction; `RETURN DISTINCT up.id, min(length(p)) AS hop` |
| System edge evidence | SQLite | Read `dataset_edge_count` from `v_system_edge`, then reverse-look up `edge` details by both-end systems (drill-down panel) |
| Fallback | SQLite recursive CTE | When Kùzu is unavailable / the graph is dirty and rebuild fails, compute the recursive closure over `v_system_edge`; same REST contract |

**Cycle handling (mandatory)**: Dataset-level lineage should be acyclic by business rules, but **cycles may appear after projection to the system level** (e.g. two datasets in system A reference each other, or X→Y and Y→X both exist). Therefore system-level traversal must: ① deduplicate with `DISTINCT` + `min(hop)`; ② keep the 1~5 hop whitelist limit; ③ have `clew graph audit` report system-level cycles, with the UI showing a hint on the cycle; ④ not infer dataset-level cycles from system-level cycles.

**4.7.5 Versions, Rollback, and Consistency**

- `system` and `system_edge` are **first-class versioned entities**: create/modify/delete writes `change_log` (`entity_kind='system'|'system_edge'`) and participates in rollback by batch/tag;
- `dataset.system_id` changes write `change_log(entity_kind='dataset', op='updated')`; dataset snapshots gain a `system_id` key. Datasets created by import write an `added` snapshot; rollback executes in the reverse order "delete edges first, then fields, and finally datasets";
- After rollback completes, `graph_state.state='dirty'`, and the next system-level read request automatically fully rebuilds Kùzu (system nodes/relationships rebuilt together with dataset/field graphs), with no per-row reverse operations needed;
- `graph_state` gains `system_rel_count`; after import completes, a cheap reconciliation is done against `SELECT COUNT(*) FROM v_system_edge`; `clew graph audit` then performs an exact `system_edge_id` set-level comparison;
- Deleting a system: `ON DELETE SET NULL` removes dataset ownership; explicit `system_edge` entries are cascade-cleaned with system deletion (the application layer deletes edges first, then the system, and writes a `deleted` log); projected edges naturally disappear as ownership is cleared.

**4.7.6 Invariants**

1. System identifiers are unique; `system_edge` is unique per upstream/downstream pair; self-loops prohibited;
2. System-level edges **do not require** dataset-level evidence (explicit edges can have only an interface description); however, once `origin=derived/both` is displayed, `dataset_edge_count` must match the underlying `edge` projection;
3. System-level cycles are allowed, but must be detectable, indicated, and non-blocking for queries;
4. Datasets without an assigned system do not enter the system graph; the UI shows a count hint "N datasets unassigned" and does not fabricate virtual system nodes;
5. The system-level view uses the same permission model as dataset/field-level views (viewer read-only, editor editable, admin can delete systems/roll back).

---

## 5. Visualization UI (Requirement 3)

Tech choice: **@xyflow/react (reactflow)**—both solutions chose it; column-level edges (sourceHandle/targetHandle), node collapse, and the layout ecosystem have all been validated, so reusing this proven approach carries the lowest risk. zustand manages canvas state.

### 5.1 Core Interactions

| Requirement | Implementation |
|---|---|
| Display datasets of interest | Search/select a starting dataset at the top → `GET /lineage/subgraph` (Kùzu Cypher, CTE fallback) to fetch the N-hop upstream/downstream subgraph |
| Upstream/downstream relationships | Left-to-right flow layout (dagre auto-layout), upstream on the left, downstream on the right |
| Field-level edges | Each field in a node card renders as a connectable handle row; field-level edges draw handle→handle connections; table-level edges draw node→node |
| Collapse fields/nodes | `collapsed` state inside reactflow nodes: collapsing a node hides its field list (showing only table-level edges); collapsing a group of nodes collapses them into a group placeholder node (the OpenMetadata `LoadMoreNode` idea) |
| Source file location | Hovering/clicking a field row opens a locator card: source file name + human-readable locator (e.g. `order_details.xlsx #sheet "Order Details" D2:D15000`). Since source files are managed (3.6), clicking the locator card can **preview the corresponding source file region directly in the system** (highlighting header path/column/row range/JSONPath matched value), with one-click copy |
| Filtering | Filter by dataset name, field name, confidence (hide low-confidence AI edges), and edit source |

### 5.2 Shared Rendering Protocol with AI Graph Generation

All backend "fetch subgraph" capabilities uniformly return one `GraphPayload` (nodes + edges + fields), and the frontend has a single rendering entry point; search-driven graph generation, click-to-expand, and AI chat graph generation all go through it, avoiding OpenMetadata's situation of two coexisting old and new graph architectures.

### 5.3 System-Level View and Drill-Down (added 2026-11)

A **level switcher** is added at the top of the canvas: `System / Dataset / Field`; all three share the same canvas skeleton (zoom, pan, filter, detail panel, edge list), switching only the data source and node renderer:

| Level | Nodes | Edges | Drill-down |
|---|---|---|---|
| System | System card: name, type badge (source system/application/warehouse/BI/external), dataset count, owner | Inter-system upstream/downstream; explicit edges solid, projected edges dashed; edges labeled with `dataset edge count` | Double-click a system → dataset view (filtered by that system); click "Evidence" → expand underlying dataset edges |
| Dataset | Dataset card (collapsible fields) | Table-level/field-level projection; existing styles retained | Double-click a dataset → field view; field details/source preview unchanged |
| Field | Existing field-level canvas | Field-level edges | — |

**Key interactions in the system view**:

1. **Direction**: Left-to-right layout, upstream on the left, downstream on the right; the toolbar provides `both / up / down` directions and 1~5 hops;
2. **Explainable edge origin**: Edge details must show `origin` (explicit / derived / both), `dataset_edge_count`, the underlying dataset edge list (from SQLite), and the explicit edge's `transform/note/confidence/source`; drawing a line whose origin cannot be explained is not allowed;
3. **Evidence drill-down**: Select a system edge → the "Relationship Evidence" panel on the right lists the dataset-level edges contributing to it (`from_dataset.field → to_dataset.field`); clicking any entry jumps to the dataset/field view and highlights it;
4. **Unassigned datasets**: The sidebar shows "N datasets without a system"; clicking lists them; the system graph generates no virtual nodes;
5. **Cycle indication**: System-level cycles (produced by projection) are marked with a "cycle" badge on the canvas and edge list, with the hint "system-level aggregate cycle, not equivalent to a dataset-level cycle";
6. **AI candidates**: System edges with `source='ai'` are rendered dashed with a low-confidence style and do not count toward "confirmed paths" statistics until confirmed;
7. **Same rendering protocol**: The system graph responds with `SystemGraphPayload` (isomorphic to the GraphPayload in §5.2: `systems[]` + `edges[]` + `seed` + `level`); AI graph generation and manual browsing share the frontend `applyGraph` entry point.

> Interaction prototype: [clew-system-lineage-prototype.html](../02_prototype/clew-system-lineage-prototype.html) (three-level switching between system/dataset/field, explicit vs. projected edge distinction, evidence drill-down, unassigned hints, system-level cycle demo). The prototype only validates the information architecture and does not mean the backend is implemented.

---

## 6. AI Chat (Requirement 4)

### 6.1 Form

Chat panel (side drawer) + canvas linkage. The AI calls this system's API tools via **function calling**; tools return structured data, the AI composes an answer, and the frontend renders the `graph` from tool results onto the canvas.

### 6.2 Tool Set (thin REST wrappers, borrowing OpenMetadata MCP's verbose principle + datahub-agent-context's interface form)

| Tool | Corresponding API | Description |
|---|---|---|
| `search_fields` | `GET /search?q=` | Fuzzy-find fields by name/description/notes |
| `get_field_details` | `GET /fields/{ds}.{f}` | Field details + source file locator + annotation history |
| `trace_upstream` / `trace_downstream` | `GET /lineage/trace` | Fetch upstream/downstream via Kùzu Cypher variable-length paths (recursive CTE fallback); parameters: starting field, direction, max hops, whether to include table-level edges |
| `get_subgraph` | `GET /lineage/subgraph` | Fetch subgraph `GraphPayload` for frontend rendering |
| `get_field_history` | `GET /changes?entity=` | Version change history of a field |
| `search_systems` | `GET /systems?q=` | Search systems by system name/identifier/description |
| `trace_system_lineage` | `GET /lineage/systems` | System-level N-hop upstream/downstream (Kùzu `LINEAGE_SYSTEM`, fallback `v_system_edge` recursive CTE); returns the system graph |
| `get_system_details` | `GET /systems/{id}` | System attributes + dataset list + upstream/downstream systems + explicit edge evidence |
| `suggest_lineage` | `POST /ai/suggest` | **AI reverse optimization**: The AI proposes potentially missing lineage edges based on field names/descriptions/similarity (low confidence, source='ai'); users confirm/reject on the graph |
| `suggest_system_lineage` | `POST /ai/suggest/systems` | System-level candidate edges (e.g. "CRM → Marketing Platform"), source='ai', must be manually confirmed before converting to manual |

> System-level tools follow the same permission and security rules as field-level tools: `search_systems` / `trace_system_lineage` / `get_system_details` are read-only; `suggest_system_lineage` is a write-type tool validated at the tool layer against the caller's role; viewer triggers only return an error and persist nothing; AI suggested system edges must be manually confirmed (editor+) before converting to `manual` (invariant #4).

### 6.3 Example Conversation Flow

> User: `Where does order_no in the orders table come from?`
> AI calls `search_fields("order_no")` → `trace_upstream(ds=xxx, field=order_no, hops=3)`
> Answer: "`order_no` is derived from `ods_raw.order_id` via `cast/trim` (2 hops, confidence 1.0); the source field is in `order_details.xlsx`, sheet "Order Details", column D" + the frontend canvas automatically switches to that field's upstream/downstream subgraph.

### 6.4 Two Paths for AI Optimization

1. **Query side** (the main body of Requirement 4): natural language → tool calls → dynamic graph generation;
2. **Data quality side** (auxiliary to Requirement 5): `suggest_lineage` uses same-name/semantic similarity/upstream-downstream proximity heuristics + LLM judgment to produce low-confidence candidate edges; **manual confirmation is mandatory** before converting to `source='manual'`—this is the key safety design borrowed from DataHub's `confidenceScore`.

---

## 7. Manual Correction and Annotation (Requirement 5)

| Capability | Design |
|---|---|
| Edit nodes/fields | Canvas node detail panel: rename, edit description, **correct src_locator** (change the locator after verifying against first-hand materials) |
| Edit edges | Change transform/note, delete incorrect edges, add edges (drag handle connections on the graph, equivalent to DataHub `manualLineage`) |
| Supplementary notes | `annotation` table: add note entries to any field/edge/dataset (body + author + time), **append-only and never overwriting original imported values**—original imported data is separated from human insights, making it easier for others to understand |
| Full traceability | Every edit writes `change_log` (before/after), supporting "who changed what and when" for a given field |
| Rollback | Roll back by import batch (4.2); a single edit can be restored to before via change_log |

---

## 8. Overall Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Frontend SPA (React + Vite)                                   │
│  ├─ Login/Users (JWT)                                          │
│  ├─ Lineage canvas (@xyflow/react)                             │
│  ├─ Import wizard (upload source files → manifest → report)    │
│  └─ AI chat drawer (tool calls drive the canvas)               │
└───────────────────────────────┬────────────────────────────────┘
        REST / JSON (JWT auth + RBAC guards, contract unchanged)
┌───────────────────────────────┴────────────────────────────────┐
│  FastAPI backend (single process)                              │
│  ├─ auth: JWT + role guards                                    │
│  ├─ importer: csv/xlsx/json                                    │
│  │   normalization + pydantic validation                       │
│  │   + real-file locator verification (openpyxl)               │
│  ├─ files: source file management/dedup/preview                │
│  ├─ lineage: graph query routing                               │
│  │   Kùzu Cypher (primary)                                     │
│  │   ├─ Field/Dataset lineage                                  │
│  │   └─ System system-level lineage                            │
│  │   ↘ recursive CTE (fallback)                                │
│  ├─ systems: system catalog/ownership                          │
│  │   explicit edges + projected view merge                     │
│  ├─ graph: dual write / mark dirty / rebuild                   │
│  ├─ versioning: batches/tags/log                               │
│  └─ ai: function calling orchestration                         │
└───────────────────────────────┬────────────────────────────────┘
   ┌────────────────────────────┴──────────────────────────┐
   ▼                                                       ▼
SQLite (single source of truth)     Kùzu 0.11.3 (lineage graph derived layer)
 user/dataset/field/                 Dataset/Field node tables
 system/system_edge/                 System node table
 edge/import_batch/                  LINEAGE_FIELD/TABLE/SYSTEM
 version_tag/annotation/             (edge_id/system_edge_id link back to primary DB)
 change_log/...+FTS5                 │ unavailable → mark dirty → auto rebuild
 data/files/ source file hosting     │ rebuild failed → read path falls back to CTE
   (sha256 dedup)
[Reserved Postgres (primary DB upgrade path) / S3; Kùzu can be removed wholesale with fallback to CTE]
```

The biggest architectural difference from the two solutions: **single process, dual embedded storage, no message queue, no search cluster**. DataHub's event-driven approach (Kafka+MCP+MCL) is replaced by "synchronous writes + change_log table"; OpenMetadata/DataHub's ES graph index is shrunk to an in-process Kùzu graph layer—**the primary query entry is always SQLite**, and Kùzu only serves lineage topology traversal and can be rebuilt from SQLite at any time (4.5). System-level lineage follows the same layering: system attributes/ownership/search in SQLite, system relationship instances and N-hop traversal in Kùzu; system edges are not a third storage stack but a projection of `v_system_edge` (explicit ∪ projected) in the graph layer (4.7).

---

## 9. Milestones (Suggested)

| Phase | Content | Acceptance criteria |
|---|---|---|
| M1 Data foundation | Table structure (including user/source_file/version_tag/graph_state), JWT auth + RBAC, source file upload with sha256 dedup, CSV/JSON/XLSX importers (including merged cell/multi-level header locator parsing and real-file verification), version batches/change_log, Kùzu graph initialization and dual write (write the graph on import, mark dirty on failure) | All three formats pass import with one sample each (including an xlsx with complex headers); erroneous locators are rejected by real-file verification; rollback v2 → restores v1 state and the Kùzu graph is rebuilt in sync; the viewer role cannot write |
| M2 Graph query + canvas | Kùzu Cypher graph query API (trace/subgraph/impact, CTE fallback) + `clew graph audit/rebuild` + reactflow canvas: subgraph rendering, field-level edges, collapse, locator card + source file region preview, graph status badge | Manually build a 5-dataset sample; 3-hop upstream/downstream expansion is correct (Cypher and CTE paths produce identical results), collapse works, and clicking the locator card highlights the source file region; after deleting the Kùzu file, automatic rebuild succeeds |
| M3 Editing and annotation | Canvas edge/field editing (editor+), annotation, history viewing, version business tags with tag diff/rollback | Edit traceability (operator recorded), rollback by tag is correct, manual annotations are not lost |
| M4 AI chat | Tool set + chat drawer + linked graph generation + suggest_lineage (confirmation permission editor+) | Questions like "where does order_no come from" produce the correct graph; AI suggested edges take effect only after manual confirmation |
| M6 System-level lineage (design added 2026-11, implementation pending) | `system` / `system_edge` tables and migrations, `dataset.system_id` ownership, `v_system_edge` (explicit ∪ projected), Kùzu `System` node and `LINEAGE_SYSTEM`, system graph API + fallback CTE, canvas level switching and evidence drill-down, import manifest extension, system-level AI read-only tools | Dataset edges within the same system produce no self-loops; system edges projected from dataset edges match `dataset_edge_count`; explicit and projected edges merge into `both` with explicit attributes taking precedence; system-level N-hop (including cycles) returns no duplicate nodes and correct hop counts; after deleting the Kùzu file, the system graph is automatically rebuilt; system/system edge/ownership changes can be rolled back by batch and tag |

---

## 10. Confirmed Decision Record (2026-10-23)

| # | Item | Decision | Design reference |
|---|---|---|---|
| 1 | Multi-user permissions | **Required**. Workspace-level RBAC (admin/editor/viewer) + JWT + full operation audit; no object-level ACL | 4.4 Users and Permissions |
| 2 | Version business tags | **Required**. `version_tag` table; tags anchor change_log positions, supporting tag-to-tag diff and rollback to a tag | 4.1 / 4.2 |
| 3 | Managed source file upload | **Required**. `source_file` table + sha256 dedup + controlled preview/download; side benefit: locators can be verified against first-hand files on import, and canvas locator cards support region preview | 3.5 / 3.6 |
| 4 | XLSX complex headers | **Required**. Merged cell anchor normalization + multi-level header `header_path` expansion + materialized parse result storage | 3.2 Normalization Rules |
| 5 | LLM provider | OpenAI-compatible API, configured in repository-root `.env` (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`), `.env` not committed | 2 Tech Stack |
| 6 | UI layout | **Lo-fi prototype confirmed (2026-10-23)**, serving as the UI baseline. Six screens in total: lineage canvas (core), source file preview (source verification modal), import wizard (three steps + validation report), AI chat (tool trace + suggestion confirmation), version and users (batches/tags/rollback + RBAC matrix), login | 5 Visualization UI |

**New decisions on 2026-11-16 (storage redesign)**:

| # | Item | Decision | Design reference |
|---|---|---|---|
| 7 | Storage solution | **SQLite + Kùzu dual embedded database combination**: SQLite serves as the underlying data storage layer for the primary query entry (single source of truth for metadata/search/versions/audit); Kùzu serves as the dedicated storage layer for lineage relationship queries (topology traversal + a few filter columns). REST contract unchanged, frontend unaffected | 4.3 Graph Model / 4.4 Query Routing / 4.5 Dual-Write Consistency |
| 8 | Kùzu archival risk | Accept using the final archived release 0.11.3 (repository read-only since 2025-10, MIT, cp38–cp314 wheels available on all platforms). Mitigations: ① Kùzu is defined as a derived layer that can be rebuilt at any time, with SQLite always the single source of truth; ② automatic rebuild on dirty + `clew graph audit/rebuild`; ③ the recursive CTE path is retained permanently, allowing wholesale fallback to the single-database solution with no data loss risk | 4.5 / §2 Tech Stack |
| 9 | System-level upstream/downstream | **Required**. Add an optional `system` layer: `system` catalog + `dataset.system_id` ownership + `system_edge` explicit edges; system graph = explicit edges ∪ dataset edge projection (`v_system_edge`), no dual write. System attributes/search go to SQLite, system-level N-hop goes to Kùzu `LINEAGE_SYSTEM`, falling back to `v_system_edge` recursive CTE; existing GraphPayload rendering protocol reused | 3.7 / 4.7 / 5.3 / 6.2 |
| 10 | System edge origin and evidence | System edges must be explainable: `origin=explicit/derived/both`, `dataset_edge_count`, underlying dataset edge list; explicit edge attributes take precedence, projected edges only provide evidence counts; system-level aggregate cycles are allowed but must be detected, indicated, and non-blocking; unassigned datasets generate no virtual system nodes | 4.7.2 / 4.7.4 / 5.3 |

Remaining open items (not blocking M1 development):
- `[TBD-INFRA]` The source file storage backend uses local `data/files/` in M1; when the S3/MinIO abstraction interface will be implemented is determined by the deployment environment;
- `[TBD-BIZ]` Whether dataset-level privacy/authorization is needed (currently all users in the workspace can see all datasets); introduce `dataset_acl` when a real need arises.
