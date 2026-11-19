# Clew Documentation Index

This directory organizes project documentation in a "design → prototype → implementation" hierarchy; reading in numeric order is recommended.

> Product showcase home: [README](../README.md) (English by default) · [README.zh](../README.zh.md) (Chinese)
> Detailed project description (formerly the repository root README): [PROJECT.md](./PROJECT.md)

## Directory Structure

```
docs/
├── README.md                          # This index
├── PROJECT.md                         # Detailed project description (formerly the repository root README)
├── assets/                            # Brand icons and README demo GIFs (brand/, demo/)
├── 01_design/                         # Design documents (the sole basis for review and development)
│   ├── clew-design-proposal.md      # Overall plan: research findings, architecture, milestones, decision records
│   ├── clew-business-model.md      # Business layer: positioning, stakeholders, domain concepts, business rules and invariants
│   └── clew-data-model.md      # Data layer: ER diagram, table definitions, indexes, version rebuild rules
├── 02_prototype/
│   ├── clew-lofi-prototype.html # Lo-fi prototype (open directly in a browser, tabs across 6 screens, UI baseline confirmed 2026-10-23)
│   ├── clew-hifi-prototype.html # Hi-fi clickable prototype (supporting the 2026-11 SQLite+Kùzu dual-database plan: mock data, 7 interactive screens including the architecture overview)
│   └── clew-system-lineage-prototype.html # System-level lineage prototype (2026-11: system/dataset/field three-level switching, drill-down into system edge evidence)
└── 03_dev/                            # Development documents (compiled from the 01_design designs and the prototype implementation)
    ├── 01_architecture.md                   # System context, module breakdown, key data flows, deployment shape, architecture decision summary
    ├── 02_frontend-development.md               # Frontend tech stack, component inventory, lineage canvas implementation, authentication and state management
    ├── 03_backend-development.md               # Backend tech stack, module responsibilities, .env configuration, import/version/AI implementation notes
    ├── 04_frontend-backend-boundaries.md             # Frontend/backend responsibility matrix and security boundaries for 14 functional domains
    ├── 05_api-reference.md                # Contracts for all 36 endpoints (parameters, responses, errors, permissions)
    ├── 06_ai-canvas-highlight-fix.md          # AI answers driving canvas tracking highlights via mark_highlight: problem/root cause/contract/verification record
    ├── 07_ai-module-evolution-plan.md              # LangChain adoption / streaming / in-conversation suggestions / description drafts / MCP: decision records and technical design
    └── 08_review-fix-batch-2026-10-26.md      # Site-wide review fixes: AI permission guardrails and context budget, overlay foundation, TopBar responsiveness, keyboard-accessible edges

Below that is 04_hifi/ (hi-fi design spec, finalized 2026-10-24: white background + blue primary color, already implemented in prototype/frontend):
    ├── 00_design-overview-and-tokens.md      # Single source of tokens: color/typography/spacing/motion/common component specs + old→new mapping
    ├── 01_login.md                     # Split-pane large card: blue-900 brand panel + white form
    ├── 02_lineage-canvas-workspace.md             # Top bar/sidebar/canvas three-region skeleton with full specs for nodes, edges, overlays
    ├── 03_details-and-preview.md                 # Right-side detail panel, source preview modal, add-edge modal
    ├── 04_ai-assistant.md                     # AI conversation drawer: message bubbles, tool trace cards, candidate edge cards
    ├── 05_versions-and-users.md                 # Version drawer, change history timeline, user management modal
    ├── 06_import-wizard.md                   # [TBD-FE] Brand-new design baseline, not implemented in this round
    └── 07_system-level-ai-assistant.md               # AI integration for the system-level lineage prototype: system-level tools, graph linking, suggested edge lifecycle
```

## Reading Order

| Order | Document | Questions It Answers |
|---|---|---|
| 1 | [Design Plan](./01_design/clew-design-proposal.md) | Why we do it this way: research findings on the two open-source solutions, overall architecture (since 2026-11 a dual database of SQLite source of truth + Kùzu lineage graph), technology choices, milestones and confirmed decision records (§10) |
| 2 | [Business Model](./01_design/clew-business-model.md) | What it is in business terms: value proposition, role permissions, 14 domain concepts (including systems and system-level lineage), 8 business processes, 11 business invariants |
| 3 | [Data Model](./01_design/clew-data-model.md) | How data is stored: column-by-column definitions for 13 SQLite business tables + graph_state, locator JSON envelope, Kùzu graph schema (including System/LINEAGE_SYSTEM) and dual-write consistency (§10), rollback rebuild rules, M2–M6 API contract increments |
| 4 | [Lo-fi Prototype](./02_prototype/clew-lofi-prototype.html) | What it looks like (wireframe baseline): 6 screens — lineage canvas, source file preview, import wizard, AI chat, versions and users, login |
| 5 | [Hi-fi Clickable Prototype](./02_prototype/clew-hifi-prototype.html) | What it feels like to interact with (demo accompanying the 2026-11 dual-database plan): mock e-commerce order warehouse data, lineage canvas (trace chains/collapse/filter/zoom), source preview, import wizard, AI tool chat with suggestion confirmation, version tag diff/rollback (with linked graph rebuild), RBAC perspective switching, storage architecture overview |
| 6 | [System-Level Lineage Prototype](./02_prototype/clew-system-lineage-prototype.html) | What upstream/downstream relationships between systems look like (new in the 2026-11 design): system/dataset/field three-level view switching, distinction between explicit and projected edges, drill-down into system edge evidence, hints for unassigned datasets, cycle warnings; includes an AI assistant drawer (system-level tool calls, graph linking, suggested edge confirmation; see 04_hifi/07 for the interaction design) |

## Development Documents (03_dev/)

Compiled from the 01_design documents and the prototype/ implementation, aimed at developers. Where design documents and implementation disagree, the current code prevails; differences are recorded in each document's "Known Gaps / Differences" section. The official project directories are `backend/` and `frontend/` at the repository root (ported from the same prototype sources; see each README for differences); path references in this document still point to the prototype baseline.

| Document | Contents |
|---|---|
| [Architecture Design](./03_dev/01_architecture.md) | System positioning and context, overall architecture and module breakdown, key data flows (import/subgraph/preview/AI/rollback), external dependencies, deployment shape, architecture decision summary |
| [Frontend Development](./03_dev/02_frontend-development.md) | Frontend tech stack and versions, directory structure, development workflow, authentication and global state, API access layer, component inventory, lineage canvas implementation, UI representation of role permissions |
| [Backend Development](./03_dev/03_backend-development.md) | Backend tech stack and versions, module responsibility table, .env configuration, database and RBAC, import pipeline, versions and rollback, AI module, error handling conventions, test and operations commands |
| [Frontend/Backend Responsibility Boundary](./03_dev/04_frontend-backend-boundaries.md) | General boundary principles, responsibility matrix for 14 functional domains, authentication and authorization boundaries, data contract boundaries, AI boundaries, list of prohibitions |
| [API Reference](./03_dev/05_api-reference.md) | General conventions (authentication/error structure/status code semantics), contracts for all 36 endpoints grouped by functional domain, data structure appendix, endpoint summary table (§15.1 separately lists endpoints added by the system-level lineage design) |
| [AI Canvas Linking Highlight Fix](./03_dev/06_ai-canvas-highlight-fix.md) | A complete record of one defect fix: the problem of AI answer highlights not taking effect and its root cause, the `mark_highlight` tool and `highlights` contract, the frontend linking chain, verification record and known boundaries |
| [AI Module Evolution Plan](./03_dev/07_ai-module-evolution-plan.md) | Blueprint for AI evolving from a query engine into a governance copilot: LangChain integration (OpenAI/DashScope dual providers), SSE streaming, in-conversation suggestions, description draft stream, MCP server, and decision records such as not adopting LangGraph |
| [Review Fix Batch 2026-10-26](./03_dev/08_review-fix-batch-2026-10-26.md) | Fix batch from the site-wide review (layout/interaction/AI): AI tool role guardrails, SSE heartbeat/stop on disconnect, context budget, rate limiting, overlay foundation (ModalShell + useOverlayBehavior), TopBar responsiveness, canvas performance and empty states, keyboard-accessible edges, AI drawer stop/clear/inline confirmation cards |

## Document-to-Code Mapping

| Document Section | Code Location |
|---|---|
| Data Model §2 Table Definitions | `prototype/backend/src/lineagelite/db.py` (DDL aligned table by table with the document, including rollback_record) |
| Data Model §4 JSON Structures | `prototype/backend/src/lineagelite/locator.py`, `manifest.py` (locator envelope + actual file verification) |
| Design Plan §3.5-3.6 Import Flow | `prototype/backend/src/lineagelite/import_service.py`, `routes/imports.py` |
| Design Plan §4.4 Users and Permissions | `prototype/backend/src/lineagelite/security.py`, `routes/auth.py` |
| Data Model §7 Version Rebuild | `prototype/backend/src/lineagelite/versioning.py` (rollback by batch/by tag, tag diff, idempotent undo) |
| Data Model §9 M2 Contract Increments | `prototype/backend/src/lineagelite/routes/datasets.py` (field_names), `preview.py` (file/verification), `lineage.py` (edge.id) |
| Data Model §9 M3 Editing and Annotation | `prototype/backend/src/lineagelite/routes/annotations.py`, `routes/fields.py`, `routes/edges.py`, `routes/changes.py`, `routes/version_tags.py`, `changes.py` |
| Data Model §9 M4 AI Interfaces | `prototype/backend/src/lineagelite/routes/ai.py`, `ai/suggest.py`, `ai/tools.py`, `ai/chat.py`, `ai/llm.py`; frontend `components/AiAssistantDrawer.tsx`, `components/EdgeDetailPanel.tsx` |
| Data Model §10 Kùzu Graph Storage | Design finalized, code migration pending (the current `backend/src/clew`/`prototype` still use a single SQLite recursive CTE; when implemented, add `graph.py` dual-write and rebuild; see that section for read-path routing) |
| Design Plan §4.7 System-Level Lineage | Design finalized, code pending implementation; prototype at `docs/02_prototype/clew-system-lineage-prototype.html`, target modules `routes/systems.py`, `lineage.system_subgraph()`, `graph.py` |
| Business Model §6 Invariants | Partly guaranteed by database constraints (partial unique index on edges), partly by service-layer validation, each covered by corresponding tests (`prototype/backend/tests/test_m3_api.py` and others) |

## Maintenance Conventions

- When documents conflict, resolve in the data-layer-first order "Data Model → Design Plan → Business Model", and mark the conflict point with `[CONFLICT]` per the AGENTS.md conventions;
- Code changes involving table structures, invariants, or interface semantics must update the corresponding document sections in the same change;
- The prototype is the UI baseline confirmed on 2026-10-23 (Design Plan §10 Decision #6); M2 frontend development uses it as the layout basis.
