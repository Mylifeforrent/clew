# Clew Frontend Development Document

> Purpose: an **implementation description** for frontend developers, written against the current state of `prototype/frontend/` — tech stack and dependencies, directory responsibilities, development workflow, authentication and state management, the API access layer, the 22 components, the lineage canvas implementation, the UI representation of role permissions, and known gaps. For the architecture overview see [./01_architecture.md](./01_architecture.md); for the field-level API contract see [./05_api-reference.md](./05_api-reference.md) (this document summarizes only and does not restate the field tables); for the frontend/backend split see [./04_frontend-backend-boundaries.md](./04_frontend-backend-boundaries.md).

---

## 0. Basis and Sources

The facts in this document come only from the following materials; where they conflict, the current state of the code prevails (differences are listed together in [§9](#9-known-gaps-and-frontend-coverage-gaps)):

| Basis | Purpose |
|---|---|
| [docs/01_design/clew-design-proposal.md](../01_design/clew-design-proposal.md) (hereinafter the "design document") | §3.2 source file locator; §5 visualization UI (5.1 core interactions, 5.2 unified rendering protocol); §6 AI conversation; §7 manual correction and annotation |
| [docs/01_design/clew-business-model.md](../01_design/clew-business-model.md) (hereinafter the "business model") | §2 stakeholders and roles (viewer/editor/admin responsibilities); §5 core business flows |
| Root [README.md](../../README.md) | Frontend subsection, tech stack conventions ("component source code built in, no additional UI component library"), known gaps |
| `prototype/frontend/package.json` + `package-lock.json` | The single source of truth for dependencies and versions (declared versions + locked versions) |
| `prototype/frontend/vite.config.ts`, `tsconfig.json`, `tailwind.config.cjs`, `postcss.config.cjs`, `index.html` | Build, type checking, and style theme configuration |
| `prototype/frontend/src/` (main.tsx, App.tsx, types.ts, all 6 files under lib/, all 22 components under components/) | Implementation facts (all references in this document are repository-relative paths) |

For the UI visual and layout baseline, see also [docs/02_prototype/clew-lofi-prototype.html](../02_prototype/clew-lofi-prototype.html) (low-fidelity prototype, confirmed 2026-10-23); its "import wizard" screen has no corresponding implementation yet, see §9.

---

## 1. Tech Stack and Dependencies

The frontend is a React 19 single-page application (SPA), developed and built with Vite, TypeScript in strict mode, Tailwind CSS atomic styles, the `@xyflow/react` canvas, and `@dagrejs/dagre` layered layout. Package management uses **npm** (a `package-lock.json` exists; pnpm / yarn are prohibited).

Runtime dependencies (declarations in `prototype/frontend/package.json`, locked versions from `package-lock.json`, lockfileVersion 3):

| Dependency | Declared version | Locked version | Purpose |
|---|---|---|---|
| react | ^19.2.9 | 19.3.1 | UI framework (function components + Hooks) |
| react-dom | ^19.2.9 | 19.3.1 | DOM rendering (`createRoot`, `src/main.tsx`) |
| @xyflow/react | ^12.12.0 | 12.12.0 | Lineage canvas: ReactFlow container, custom nodes/edges, Handle, MiniMap/Controls/Panel, `useNodesState`/`useEdgesState` |
| @dagrejs/dagre | ^1.1.8 | 1.1.8 | Directed graph layered layout (`lib/layout.ts`, LR left-to-right flow) |

Development dependencies:

| Dependency | Declared version | Locked version | Purpose |
|---|---|---|---|
| typescript | ~5.9.3 | 5.9.3 | Type checking (`tsc -b`, all `strict` options enabled, see below) |
| vite | ^7.3.7 | 7.3.7 | Dev server (port 5173), build, proxy |
| @vitejs/plugin-react | ^5.2.0 | 5.2.0 | React plugin for Vite (Fast Refresh) |
| tailwindcss | ^3.4.19 | 3.4.19 | Atomic CSS (v3, config in `tailwind.config.cjs`) |
| postcss | ^8.5.6 | 8.5.31 | PostCSS pipeline for Tailwind |
| autoprefixer | ^10.4.21 | 10.6.1 | CSS vendor prefixes |
| @types/react | ^19.2.0 | 19.3.0 | React types |
| @types/react-dom | ^19.2.0 | 19.3.0 | react-dom types |
| @types/node | ^24.19.2 | 24.19.2 | Node types (`tsconfig.json` `types` includes `node`) |

**Deliberately not included** (per the code):

- **No UI component library**: the tech stack subsection of the root README states explicitly "component source code built in, no additional UI component library" — buttons, inputs (`.field-input`, `src/index.css`), modals, drawers, Toast, etc. are all implemented with in-project components and Tailwind classes;
- **No state management library**: design document §5 once proposed "zustand for canvas state", but the implementation does not use it (React built-in `useState`/`useRef`, see §4; the difference is recorded in §9);
- **No routing library**: no react-router; `App.tsx` conditionally renders between the `LoginPage` and `Workspace` screens based on "whether a session exists";
- **No HTTP library**: only `fetch` is used (the README states explicitly that "the frontend uses only `fetch` to access the API");
- **No icon library**: `components/Icon.tsx` provides 42 built-in inline SVG icons (the `IconName` union type).

TypeScript configuration highlights (`tsconfig.json`): `target: ES2022`, `moduleResolution: "bundler"`, `verbatimModuleSyntax`, `strict` + `noUnusedLocals` + `noUnusedParameters` + `noFallthroughCasesInSwitch` + `erasableSyntaxOnly`, `jsx: "react-jsx"`, `types: ["vite/client", "node"]`, `include: ["src", "vite.config.ts"]`.

Tailwind theme highlights (`tailwind.config.cjs`; content covers `index.html` and `src/**/*.{ts,tsx}`):

- Custom palette: `canvas`/`surface` (beige paper), `ink` (dark green text, 4 shades), `line` (dividers, 3 shades), `pine` (primary color, 50–900), `ember`/`ochre`/`rosewood` (accent colors), `ai` (AI-specific blue `#2f64d8` family);
- Fonts: `sans` (Noto Sans SC, etc.), `display` (Newsreader/Song typeface family), `mono` (IBM Plex Mono, etc., loaded via the Google Fonts `@import` in `index.css`);
- Shadows `card`/`float`/`node`/`node-active`, background `fine-grid` (28px grid), animations `fade-up`/`fade-in`/`modal-in`/`soft-pulse`.

---

## 2. Directory Structure and Responsibilities

```
prototype/frontend/
├── index.html            # Vite entry: zh-CN, favicon.svg, Google Fonts preconnect, #root mount point
├── package.json          # Dependencies and scripts (single source of truth for versions)
├── package-lock.json     # npm locked versions
├── tsconfig.json         # TypeScript config (strict)
├── vite.config.ts        # Port 5173 + proxy for 12 API prefixes → 127.0.0.1:8000
├── tailwind.config.cjs   # Tailwind theme (palette/fonts/shadows/animations)
├── postcss.config.cjs    # postcss pipeline: tailwindcss + autoprefixer
├── public/               # Static assets (favicon.svg)
├── dist/                 # Build output (npm run build output, not committed)
└── src/
    ├── main.tsx          # React entry: StrictMode + createRoot, imports @xyflow/react styles before index.css
    ├── App.tsx           # Top level: session state, 401 expiry event listener, LoginPage/Workspace switch
    ├── index.css         # Tailwind directives + global base styles + .field-input component class + React Flow canvas customization
    ├── types.ts          # All API types and request payload types (single type export point)
    ├── lib/              # UI-free utility layer (7 files)
    │   ├── api.ts        # API access layer: fetch wrapper, ApiError, session persistence, 401 global event, all request functions
    │   ├── entities.ts   # Entity key rules for annotations / change_log (field `<ds>.<field>`, edge `<from>--><to>`)
    │   ├── fieldChain.ts # Canvas view derivation: same-name field match line derivation from table-level lineage + upstream/downstream trace chain on field click (BFS)
    │   ├── format.ts     # Display formatting: human-readable locator, column number→letter, confidence, date, cell
    │   ├── handles.ts    # Canvas handle id constants and generator functions (table-level/field-level)
    │   ├── layout.ts     # dagre layered layout + node height estimation constants
    │   └── roles.ts      # Role checks (isEditor/isAdmin/roleLabel), UI layer only
    └── components/       # 22 React components (list in §6)
```

Responsibilities and key exports of each `lib/` file:

| File | Responsibility | Key exports |
|---|---|---|
| `lib/api.ts` | The single API access layer: request wrapper, error conventions, session read/write, request functions grouped by domain, controlled file download | `ApiError`, `SESSION_STORAGE_KEY`, `AUTH_EXPIRED_EVENT`, `login`, `getDatasets`, `getSubgraph`, `getFieldPreview`, `getAnnotations`/`createAnnotation`, `patchField`, `createEdge`/`patchEdge`/`deleteEdge`, `getChanges`, `getVersionTags`/`createVersionTag`/`getVersionTagDiff`/`rollbackVersionTag`, `getImportBatches`, `getUsers`/`createUser`, `getAiStatus`/`sendAiChat`/`suggestAiEdges`/`confirmAiSuggestion`/`rejectAiSuggestion`, `downloadSourceFile`, `loadSession`/`persistSession`/`clearSession`, `isAbortError` |
| `lib/entities.ts` | Annotation/change log entity naming rules consistent with the backend | `fieldEntityKey`, `edgeEntityKey` |
| `lib/fieldChain.ts` | Canvas view derivation (not a backend contract, not persisted): `deriveFieldMatches` derives same-name field match lines from table-level edges; `computeFieldChain` starts from the clicked field and performs an undirected BFS along "stored field-level edges + derived lines" to collect the entire upstream/downstream chain | `deriveFieldMatches`, `computeFieldChain`, `derivedLinkKey` |
| `lib/format.ts` | Display-oriented formatting: `humanizeLocator` (CSV/XLSX/JSON locator → locale-aware human-readable text, including merged-header anchors), `columnIndexToLabel` (1→A), `locatorTypeLabel`, `formatConfidence`, `formatDateTime` (ISO → `2026-10-23 14:30`), `displayCell` (empty string→`∅`), `formatJsonValue`, `formatCount` | See left |
| `lib/handles.ts` | Single convention for canvas handle ids | `TABLE_TARGET_HANDLE` (`table:in`), `TABLE_SOURCE_HANDLE` (`table:out`), `fieldTargetHandle` (`field:in:<name>`), `fieldSourceHandle` (`field:out:<name>`) |
| `lib/layout.ts` | dagre layout and node size estimation (constants: `NODE_WIDTH=288`, `NODE_HEADER_HEIGHT=56`, `FIELD_ROW_HEIGHT=34`, `FIELD_PREVIEW_LIMIT=5`, etc.) | `layoutDatasets`, `estimateNodeHeight`, `visibleFieldCount` |
| `lib/roles.ts` | Role visibility checks; the comment states explicitly "it only decides whether write entry points are shown; real permission checks are in the backend" | `isEditor` (editor or admin), `isAdmin`, `roleLabel` |

Besides the Tailwind directives, `src/index.css` maintains three kinds of global styles: the `.field-input` input component class; React Flow override styles (`.lineage-flow` canvas background, `.react-flow__node-dataset` node container default frame removal, `.table-handle`/`.field-handle` handle appearances, `.lineage-controls`/`.lineage-minimap`, `.edge-tooltip`); `prefers-reduced-motion` and mobile (MiniMap hidden) adaptations.

---

## 3. Development Workflow

### 3.1 Commands

```bash
cd prototype/frontend
npm install        # Install dependencies (npm, generates/uses package-lock.json)
npm run dev        # vite dev server → http://localhost:5173
npm run build      # tsc -b && vite build (type check first, then build; output in dist/)
npm run preview    # vite preview (preview the build output locally)
npm run typecheck  # tsc -b (type check only; not listed in the README, see package.json scripts)
```

### 3.2 Vite Proxy and Backend Dependency

`vite.config.ts` forwards all of the following **12 prefixes** to `http://127.0.0.1:8000` (`changeOrigin: true`):

`/auth`, `/datasets`, `/lineage`, `/fields`, `/edges`, `/annotations`, `/changes`, `/version-tags`, `/users`, `/ai`, `/files`, `/import`

That is, in development the frontend and backend are same-origin (relative-path requests), with no CORS configuration. The API base URL in `lib/api.ts` comes from `import.meta.env.VITE_API_BASE_URL` (default empty string = same-origin relative paths; can be used in build mode to point to a separately deployed backend).

**Dependency on the backend being up**: all data (login, datasets, subgraph, preview, AI) comes from the backend, so the backend must be started before development (see the backend subsection of the root README: at the repository root, `cp .env.example .env` → `cd prototype/backend && uv sync && uv run uvicorn lineagelite.main:app --reload`). When the backend is not running, the frontend does not go blank: the login page shows "Unable to connect to the service, please try again later", and after entering the workspace the dataset list shows an error card and a "Retry" button (with the hint "Please check whether the backend service has been started"). To get demo data, run the backend command `uv run python -m lineagelite.seed_demo`.

---

## 4. Authentication and Global State Management

### 4.1 Login Flow and JWT Storage

1. At initialization, `App.tsx` calls `loadSession()` to read the session from `localStorage` (key `clew.session`, JSON: `access_token`/`token_type`/`username`/`role`; if the structure is invalid or corrupted it is discarded and null is returned);
2. No session → render `LoginPage`: submitting the form calls `login(username, password)` (`POST /auth/login`); on success, `persistSession(session)` writes to `localStorage` and calls back into `App`; on failure (including 401 wrong password) the error is shown inline on the login page only and does **not** trigger the expiry event (this request carries no token);
3. Session exists → render `Workspace`, mounted with `key={session.access_token}` — switching accounts / logging in again forces a full-tree rebuild, leaving no page state from the old session;
4. All subsequent authenticated requests get `Authorization: Bearer <access_token>` attached uniformly by `lib/api.ts` (the `token_type` field is stored for display only; the header always uses `Bearer`);
5. Logout: "Sign out" in the `TopBar` user menu → `clearSession()` (removes the `localStorage` key) → back to the login page.

### 4.2 Global 401 Handling

When the response is 401 **and the request carried a token**, `request()` in `lib/api.ts` (and `downloadSourceFile`) dispatches the custom event `clew:auth-expired` on `window` (constant `AUTH_EXPIRED_EVENT`); `App.tsx` listens for it, runs `clearSession()`, clears the session, and shows "Your session has expired. Please sign in again to continue." at the top of the login page. This is the README's "any authenticated request returning 401 returns to the login page".

### 4.3 Global State Inventory and Storage

The frontend has **no** state management library and no React Context: the session is the only state persisted across reloads; everything else is React state inside components, passed down one-way via props.

| State | Location | Notes |
|---|---|---|
| Login session (token/username/role) | `App` `useState` + `localStorage['clew.session']` | Restored after page reload; `loadSession` validates field completeness |
| 401 expiry notice text | `App` `useState` (`notice`) | Shown when returning to the login page |
| Dataset list / load error / reload key | `Workspace` | `GET /datasets`, cancellable via AbortController |
| Search term, selected dataset (seed), hop count (default 3, selectable 1–5) | `Workspace` + controlled `TopBar`/`DatasetSidebar` | A change of seed or hop count refetches the subgraph |
| Current subgraph `graph` and AI subgraph `aiGraph` | `Workspace` | `displayGraph = aiGraph ?? graph`; the AI graph takes precedence; `aiGraph` is cleared when the dataset/hop count/refresh changes |
| Canvas filters (`minConfidence`/`hideAiEdges`/`confirmedOnly`) | `Workspace`, controls in `DatasetSidebar` | Display filtering only; backend data is not modified |
| Collapsed node set `collapsedIds` / expanded field set `fieldsExpandedIds` | `Workspace` → `LineageCanvas` props | Not persisted; reset when the seed changes |
| Collapsed groups `groups`, selected nodes, drag position cache | `LineageCanvas` internal state/`useRef` | Canvas-local lifecycle only |
| Selected field / selected edge / source preview target / new edge draft / edge pending deletion | `Workspace` | Drives the right-hand panel and modals |
| Drawer and modal switches (versions/users/AI) | `Workspace` | Conditional rendering |
| Toast messages | `Workspace` (auto-dismiss after 4.2s) | Global operation feedback |

---

## 5. API Access Layer (lib/api.ts and types.ts)

### 5.1 Request Wrapper and Error Conventions

- `request<T>(path, init, token?)` is the only JSON request entry point: it adds `Content-Type: application/json` automatically when a `body` is present and the header is not already set; adds the Bearer header when a token is present; throws `ApiError(status, message)` when `!response.ok`; returns `undefined` for `204`.
- Error message parsing (`readErrorDetail`): the backend `detail` string is preferred; for FastAPI validation errors (`detail` is an array), the individual `msg` values are concatenated (separated by ";"); when no usable detail is available, fall back by status code: 401 "Session expired", 403 "The current account is not authorized to perform this operation", 404, 409 "Operation conflict", 422 "Invalid request parameters", otherwise "Request failed (HTTP n)". Non-JSON error bodies (such as an HTML error page) are not passed through verbatim, to avoid displaying them directly to users.
- All request functions accept an optional `AbortSignal`; components call `abort()` on unmount or when starting a new request; `isAbortError()` is used to handle cancellation silently in a uniform way.
- `downloadSourceFile(token, fileId, filename)` is separate from `request` (it needs a blob): fetch → `URL.createObjectURL` → click a hidden `<a download>` → `revokeObjectURL`; storage paths never pass through the frontend, only source file IDs are accepted (see the trailing note in `lib/api.ts`).

### 5.2 types.ts and Its Correspondence to the Backend Contract

`src/types.ts` is the frontend's only type export point and maps one-to-one to the backend REST contract (field-level definitions in [./05_api-reference.md](./05_api-reference.md); only groupings are listed here):

| Type group | Types | Corresponding backend |
|---|---|---|
| Authentication | `Session` / `LoginResponse` | `POST /auth/login` response |
| Datasets | `DatasetSummary` (including `field_names`) | `GET /datasets` |
| Subgraph (GraphPayload) | `LineageGraph` = `LineageDataset[]` + `LineageEdge[]`; `DatasetField` embeds `LocatorEnvelope{type, input, resolved}` and `SourceFileRef` | `GET /lineage/subgraph`; the unified rendering protocol of design document §5.2, with a single consumption entry point in the frontend (`Workspace.applyGraph`) |
| Edges | `LineageEdge` (`id` is the database primary key, used to locate an edge for manual edit/delete; `from_field`/`to_field` being null means a table-level edge); `EdgeDraft`/`EdgeCreatePayload`/`EdgePatchPayload` | `POST /edges`, `PATCH/DELETE /edges/{id}` |
| Fields | `FieldPatchPayload` (description/field_type/src_locator) | `PATCH /fields/{dataset_id}/{field_name}` |
| Source preview | `PreviewResponse` = `PreviewFileRef` + `PreviewVerification` + `LocatorEnvelope` + (`CsvPreview` \| `XlsxPreview` \| `JsonPreview`) | `GET /fields/{dataset_id}/{field_name}/preview` |
| Annotations | `Annotation`, `AnnotationCreatePayload`, `TargetKind` (dataset/field/edge) | `GET/POST /annotations` |
| Change history | `ChangeEntry`, `ChangeOp` | `GET /changes` |
| Versions | `VersionTag`, `VersionTagDiff(Item)`, `ImportBatch` | `GET/POST /version-tags`, `/version-tags/diff`, `/version-tags/{name}/rollback`, `GET /import/batches` |
| Users | `UserAccount` | `GET/POST /users` (admin) |
| AI | `AiStatus`, `AiChatMessage`, `AiFocus`, `AiToolTrace`, `AiChatResponse{answer, tool_trace, graph?}`, `AiSuggestion`, `AiEdgeKey`, `AiStreamEvent` (SSE events, M5), `AiDraftItem` (M5) | `/ai/status`, `/ai/chat`, `/ai/chat/stream`, `/ai/suggest`, `/ai/suggest/confirm`, `/ai/suggest/reject`, `/ai/description-drafts*` |

Frontend-specific (not a backend contract): `FieldSelection` (a dataset+field pair selected on the canvas).

---

## 6. Component Inventory

All components are function components and live in `prototype/frontend/src/components/`. Organized by layer:

**Page layer**

| Component | Responsibility | Key interactions / Used by |
|---|---|---|
| `LoginPage` | Login screen: form (username/password, password visibility toggle), error display, brand and canvas illustration decoration (`MiniNode`) | Rendered by `App` when there is no session; on success `persistSession` + callback |
| `Workspace` | Main workspace container: holds all page state (datasets/subgraph/AI subgraph/filters/selection/drawer switches), organizes data loading (AbortController), the `applyGraph` unified rendering entry point, and refresh after edge add/delete and rollback | Rendered by `App` when a session exists (`key={token}`); composes all components below |
| `TopBar` | Top bar: brand, global search (`/` shortcut to focus, match count), "AI Assistant" and "Versions" buttons, hop count switch (1–5), user menu (role label, admin-only "User Management", sign out) | Props supplied by `Workspace` |
| `DatasetSidebar` | Left sidebar: dataset list (selection sets the seed; skeleton/error/empty states), canvas filter controls (confidence threshold, hide AI suggested edges, show confirmed lineage only), current subgraph statistics, edge legend and source badges | `Workspace` |

**Canvas layer**

| Component | Responsibility | Key interactions / Used by |
|---|---|---|
| `LineageCanvas` | `ReactFlow` canvas: builds `LineageGraph` into nodes/edges (including collapsed groups and aggregate edges, same-name field match derived lines), dagre layout, drag position memory, box-select collapse, validation of edge creation by dragging handles, highlighting the upstream/downstream trace chain on field click (dimming other edges), loading/error overlays, fitView, tool panel (collapse all/expand all, collapse selection/expand all groups) | `Workspace`; see §7 for implementation details |
| `DatasetNode` | Custom dataset node: header (name/id/field count, seed badge, collapse button) + field rows (one field-level handle on each side of every row; clicking a row selects the field; red-family highlighting in trace state — focused row with red ring and red dot, chain rows with a light red background) + "N more fields collapsed" toggle | Registered by `LineageCanvas` as `nodeTypes.dataset` |
| `GroupNode` | "Collapsed to group" placeholder node: dashed card showing group name and member count, table-level handles on both sides (not connectable), clicking dissolves the group | Registered by `LineageCanvas` as `nodeTypes.group` |
| `LineageEdge` | Custom edge: `getSmoothStepPath` rounded polyline + arrow, visuals differentiated by source (`getEdgeVisual`) and support for trace focus state (`focusState`: chain hits turn red, thicker, and animated / non-hits dimmed), hover/selection opens a tooltip card (endpoints, transformation, confidence, source, view details/edit/delete buttons); aggregate edges and same-name field match derived lines (`derived`) are read-only, and derived line tooltips have no action buttons | Registered by `LineageCanvas` as `edgeTypes.lineage` |

**Drawers and modals**

| Component | Responsibility | Key interactions / Used by |
|---|---|---|
| `DetailPanel` | Field detail right panel: field attributes, human-readable locator + raw JSON, copy locator, upstream field-level edge cards, field editor (description/type/locator, form depending on src_type with either-or validation), AI suggestion generation and candidate card confirm/reject, annotations, change history entry | `Workspace` (shown when no edge is selected; empty state shows guidance) |
| `EdgeDetailPanel` | Edge detail right panel: endpoints and metadata, transformation/confidence/notes editor (`EdgeEditor`), "Confirm as manual edge" for `source='ai'` candidates, delete entry, annotations, change history entry | `Workspace` (replaces `DetailPanel` when an edge is selected) |
| `PreviewModal` | Source preview modal: calls the preview API and renders by type — CSV table (target column highlighted, first 50 rows), XLSX (header rows + merged-cell anchor normalization + highlighted column and data row range), JSON (JSONPath match count and samples); failures distinguish 404 (locator invalid)/403 and other statuses; "Copy locator", "Download source file" | `Workspace`, triggered by the preview button in `DetailPanel` |
| `EdgeCreateModal` | Confirmation modal after creating an edge by dragging handles: shows the draft endpoints (field-level/table-level determined automatically), transformation/confidence (0–1 validation)/notes, and submits `POST /edges` | `Workspace`, triggered by the `LineageCanvas.onConnect` chain |
| `HistoryDrawer` | Change history drawer: `GET /changes` (limit 50), displaying for each entry the operation type/operator/time and the before→after field-level differences (locators go through `humanizeLocator`) | Opened embedded from `DetailPanel` and `EdgeDetailPanel` |
| `VersionDrawer` | Versions drawer: import batch list (version number/format/file/status), business tag list and creation (editor+), diff between tags (net change summary + details), admin rollback to a tag (`ConfirmDialog` confirmation) | `Workspace`, opened from the `TopBar` "Versions" |
| `AiAssistantDrawer` | AI assistant drawer (M5 + No. 08 R17): `GET /ai/status` status check (not-configured/unknown-status branches and retry), SSE streaming chat (Enter to send, history truncated to the latest 50 messages, 8000 characters each), **the send button switches to "Stop" during streaming**, closing the drawer soft-interrupts the in-flight stream, "Clear conversation" (`ConfirmDialog` confirmation), tool call trace chips, **inline candidate confirmation cards** for `suggest` events (confirm/reject call the API directly; grayed out for viewer with a hint that editor is required), `drafts` draft cards (accept/reject), `graph` results wiring `onGraph` to switch the canvas + `highlights` wiring trace highlighting, falls back to the not-configured state on 503; header badge "Queries available in real time; write operations require editor" | `Workspace`, opened from the `TopBar` "AI Assistant" |
| `UserManagementModal` | Admin user management modal: user list + new user form (username ≥2, password ≥6, one of three roles); fixed footer notice "No API is available yet for role changes or disabling accounts" (see §9) | `Workspace`, opened from the `TopBar` user menu (visible to admin only) |
| `ConfirmDialog` | Generic confirmation modal (danger style, busy state, Esc/backdrop close, focus management) | Deleting lineage edges (`Workspace`), rolling back tags (`VersionDrawer`) |

**Overlay behavior baseline (No. 08 R13)**: the 8 overlays are all wired through `lib/useOverlayBehavior.ts` + `components/ModalShell.tsx` — the former handles the Esc stack (a module-level overlay stack; **only the top of the stack responds to Esc**, so one Esc press with two drawers open closes only one layer), saving focus on open and restoring it on close, Tab focus trapping, and the `body` scroll lock; the latter provides the overlay container (centered modal / right-side drawer variants) and unified header (icon badge + title + close button) / body / footer slots. Each overlay only declares its content and `requestClose` (may refuse to close while busy), no longer hand-writing keydown, focus management, or scroll locks. The `onClose` supplied by `Workspace` is always a stable `useCallback` reference, preventing parent renders from remounting drawer-level effects and stealing focus.

**Base UI**

| Component | Responsibility | Key interactions / Used by |
|---|---|---|
| `Toast` | Global toast (three tones: success/error/info, `role=alert/status`) | `Workspace` owns the message and renders it |
| `Brand` / `BrandMark` | Brand logo (inline SVG ball of thread) and the "Clew. · Field-level lineage · Trace along the line" wordmark | `TopBar`, `LoginPage` |
| `Icon` | Unified export of 42 built-in inline SVG icons (the `IconName` union type) | Almost all components |
| `ModalShell` | Unified overlay base (No. 08 R13): overlay (`fixed inset-0`) + card container + header/body/footer slots; `variant` supports centered modal and right-side drawer; used together with `useOverlayBehavior` | All 8 overlays |
| `SourceBadge` | Lineage source badge: three-color styles for imported (file import)/manual (manual confirmation)/ai (AI suggestion), with a fallback for unknown sources; `sourceMeta` is also exported | Canvas edge tooltips, `EdgeDetailPanel`, `DetailPanel`, `DatasetSidebar` legend |
| `AnnotationSection` | Append-only annotation section: list (author/time) + input (4000-character limit), read-only for viewer; no edit/delete provided (consistent with the business model) | Reused by `DetailPanel` (field) and `EdgeDetailPanel` (edge) |

---

## 7. Lineage Canvas Implementation

Corresponds to design document §5 (visualization UI). Core chain: `Workspace` holds the `LineageGraph` → `LineageCanvas` converts it to ReactFlow nodes/edges → custom components render.

### 7.1 Custom Nodes and Edges

- `nodeTypes = { dataset: DatasetNode, group: GroupNode }`, `edgeTypes = { lineage: LineageEdgeView }` (registered at the top of `LineageCanvas.tsx`).
- **DatasetNode**: a card with fixed width 288px; one **table-level** handle on each side of the header (`table:in` / `table:out`, at the title row height); one **field-level** handle on each side of every field row (`field:in:<name>` / `field:out:<name>`, with ids generated by `lib/handles.ts`). `isConnectable={connectable}` — a viewer's handles cannot be dragged to create lines (`nodesConnectable={canEdit}` also disables canvas connections). The seed node is highlighted in pine with a "Seed" badge and a raised `zIndex`.
- **GroupNode**: table-level handles only, with `isConnectable={false}`; cross-group aggregate edges point to it.
- **LineageEdgeView**: `getSmoothStepPath` (borderRadius 18 / offset 30) + `MarkerType.ArrowClosed` arrow; an 18px-wide transparent hit path makes thin lines hoverable; the tooltip is rendered outside ReactFlow with `EdgeLabelRenderer` (`nodrag nopan`). Visual rules `getEdgeVisual(edge)` (color values consistent with the single source in `lib/edgeColors.ts`; the table below is synchronized with the current values after the hi-fi migration):

| Source/form | Color | Line style | Width | Other |
|---|---|---|---|---|
| `source='ai'` | `#4F46E5` (`EDGE_COLORS.ai`) | dashed `6 5` | 1.8 | `animated` (flow animation) |
| `source='manual'` | `#D97706` (`EDGE_COLORS.manual`) | field-level solid; table-level dashed `4 5` | 1.7 | - |
| imported field-level | `#475569` (`EDGE_COLORS.imported`) | solid | 1.55 | - |
| imported table-level | `#64748B` (`EDGE_COLORS.importedWeak`) | dashed `4 5` | 1.4 | - |
| Same-name field match (derived, view-derived) | `#94A3B8` (`EDGE_COLORS.derived`) | dotted dashed `2 4` | 1.3 | Not selectable/editable; tooltip is read-only |
| Trace chain hit (`focusState='chain'`) | `#DC2626` (`EDGE_COLORS.focus`) | inherits the original line style | 2.6 | `animated`; `zIndex: 2`; other edges dimmed to opacity 0.15 |

### 7.2 dagre Layered Layout (lib/layout.ts)

- Graph parameters: `rankdir: 'LR'` (upstream on the left, downstream on the right, design document §5.1), `align: 'UL'`, `nodesep: 42`, `ranksep: 124`, `marginx/y: 36`, `acyclicer: 'greedy'` (self-loop/back-edge handling), `ranker: 'network-simplex'`, `multigraph: true` (multiple edges between the same node pair).
- Self-loop edges (`from_dataset === to_dataset`) and edges whose endpoints are not both in the subgraph do not participate in layout; layout positions only **dataset nodes** (group nodes take the center of their members' bounding box, see 7.4).
- Node height is estimated from content (`estimateNodeHeight`): constants `NODE_HEADER_HEIGHT=56`, `FIELD_ROW_HEIGHT=34`, `FIELD_PREVIEW_LIMIT=5` (only the first 5 fields inside a node are shown by default), collapsed state `COLLAPSED_BODY_HEIGHT=48`, empty fields 42, expand/collapse toggle row 26.
- **Drag position memory**: `LineageCanvas` uses a `draggedPositions` ref to record nodes the user has manually dragged; these are reused first when nodes are rebuilt, while nodes never dragged follow the new dagre layout. A seed or hop count change is treated as a new graph — the drag cache and groups are cleared and everything is re-laid out.

### 7.3 Field-Level/Table-Level Connections and Handle Conventions

- Edge construction rules (`LineageCanvas` effect): if either `from_field`/`to_field` is null → table-level edge, routed `table:out → table:in`; if both ends are fields → field-level edge, routed `field:out:<f> → field:in:<f>`.
- **Collapse coupling**: if either endpoint node is collapsed (`collapsedIds`) → field-level edges are hidden (table-level edges remain); when fields are partially collapsed (first 5 by default), if the field at either end is not in the visible set → that edge is hidden as well.
- **Same-name field match derived lines (derived, view-derived, not persisted)**: `deriveFieldMatches` in `lib/fieldChain.ts` derives, for each **table-level edge** (either `from_field`/`to_field` is null) — field names shared by both datasets and not already used as an endpoint by any explicit field-level edge between that pair of datasets — generating an `A.f → B.f` derived line (direction follows the table-level edge). Explicit field-level edges represent single-field mappings only and do not participate in derivation, avoiding contradictions with manually/AI-confirmed mappings. Derived lines are not selectable/editable (`selectable: false`, no action buttons), and their tooltip is labeled "Same-name field match · derived"; collapse/visibility coupling is the same as for field-level edges, and when either end is in a collapsed group the relationship is expressed by a cross-group aggregate edge instead of being rendered separately. Derivation is based on the edge set the canvas actually receives (confidence/AI filtering also reduces derived lines).
- **Field trace chain (`focusedField` focus state)**: clicking a field row → `computeFieldChain` starts from that field and performs an undirected BFS along "stored field-level edges + derived lines" to collect the entire upstream/downstream chain (propagating to the end of the chain, not just one hop): hit edges (`focusState='chain'`) change stroke to `#DC2626`, width 2.6, `animated`, `zIndex: 2`; all other connections (including table-level and aggregate edges) are dimmed to opacity 0.15, and arrow markers go through `withAlpha(color, 0.3)` for reduced alpha. Hit field rows are highlighted at the same time: the focused row gets `bg-red-50` + red ring + red dot, chain rows get `bg-red-50/70`, and field-level handles switch to the red `.field-handle-traced`. Clearing triggers: clicking empty canvas (`onPaneClick`), clicking an edge (opens edge details), box-selecting nodes (group collapse flow), changing the seed/hop count, or the focused field not existing after a subgraph refresh. Before tracing, the chain is automatically made visible: collapsed nodes are expanded (`onToggleCollapse`), and field lists beyond the first 5 are expanded (`onToggleFields`); a field with no field-level associations is neither highlighted nor dimmed.
- **Adding lineage by dragging handles** (`onConnect`): validates that "field-level and table-level connections cannot be mixed", "self-connections on the same field/node are rejected", and "handle prefix parse failures prompt a re-drag"; on success it produces an `EdgeDraft` (field-level/table-level determined by the handle type) → `Workspace` opens `EdgeCreateModal` to fill in transformation/confidence/notes → `POST /edges` (the backend persists manual edges with `source='manual'`).
- Box-selection interactions: `selectionKeyCode="Shift"` (box select), `multiSelectionKeyCode={['Meta','Control','Shift']}` (multi-select), `deleteKeyCode={null}` (Delete-to-delete-edge disabled; deletion must go through the detail panel + confirmation).

### 7.4 Field Collapsing and "Box-Select to Collapse into a Group"

- **Node collapse** (`collapsedIds`): the header button collapses the entire field list; the node becomes shorter and field-level edges are hidden;
- **Field collapse** (`fieldsExpandedIds`): only the first `FIELD_PREVIEW_LIMIT=5` fields are shown by default; the "N more fields collapsed" label toggles expand/collapse in one click; the "Collapse all/Expand all" control at the top left of the canvas toggles them in bulk;
- **Box-select to collapse into a group**: Shift box-select or multi-select ≥2 dataset nodes → the tool panel shows "Collapse selected (N)"; member nodes are hidden at the **view layer** (nothing is written to the backend) and replaced by a `GroupNode` placeholder (placed at the center of the members' bounding box, excluded from dagre). Edges among group members cancel each other out; cross-group edges are aggregated per "group/dataset pair" into a single dashed edge (tooltip shows "Cross-group aggregate · N edges", not individually operable). Clicking the group node or "Expand all groups" dissolves it; after a seed/hop count change or subgraph refresh, disappeared members are removed automatically and groups with fewer than 2 members dissolve automatically. This is the M3 frontend minimal-implementation trade-off (header comment in `GroupNode.tsx`).

### 7.5 Hop Count and Direction Parameters

- Hop count: `TopBar` offers 1–5 levels (`HOP_OPTIONS`; the comment states explicitly that this matches the backend `/lineage/subgraph` `hops 1..5` contract), `Workspace` defaults to 3; a change refetches the subgraph and clears the AI overlay graph.
- Direction: `getSubgraph` always passes `direction: 'both'` (both upstream and downstream; the canvas uses LR layout to distinguish direction); the backend `hops` defaults to 3 with `ge=1, le=5`.

### 7.6 AI Graph Integration and the Unified Rendering Protocol

- All subgraph consumption goes through `Workspace.applyGraph` (design document §5.2 "single rendering entry point"): regular subgraphs and AI graphs share the same canvas state cleanup (keeping collapse/selection state that still exists, clearing invalid selections).
- When `AiAssistantDrawer` receives a response carrying `graph` (the subgraph returned by the last `trace_lineage` tool call) → `onGraph` → `Workspace.setAiGraph` + `applyGraph` + Toast "Canvas updated: N datasets · M connections". The AI subgraph takes precedence over the seed-fetched subgraph until the user switches dataset/hop count or refreshes.
- **AI highlight integration** (added 2026-10-24; see [06_ai-canvas-highlight-fix](./06_ai-canvas-highlight-fix.md) for details): when the response carries `highlights` (declared by the model through the `mark_highlight` tool), `Workspace` stores `{seq, fields}` in `aiFieldFocus` and passes it to the canvas; after validating that the fields exist in the subgraph, `LineageCanvas` reuses `revealChainFields` to expand automatically and applies the fields as the trace focus (same effect as clicking a field: the chain turns red and the rest is dimmed). When a round of answers does not declare `highlights`, seq increments and the previous round's trace state is explicitly cleared.
- When rendering an AI graph, if the original seed is not in the subgraph, the current focus (selected field/dataset) or the subgraph's first node is used as the canvas seed (`canvasSeedId`).

### 7.7 Confirming source='ai' Edges as Manual

Corresponds to design document §6.4 and the business model invariant "AI cannot take effect directly":

1. **Generate**: "Generate AI candidates" in `DetailPanel` (field details) → `POST /ai/suggest {dataset, field}` → the backend heuristically generates candidate edges by same-name fields (0.7)/containment relationships (0.6) and **persists them with `source='ai'`**; the frontend then calls `onRefresh` to refresh the subgraph, and the candidate edges (blue dashed line + flow animation) appear on the canvas immediately;
2. **Candidate card handling**: candidate cards in `DetailPanel` offer "Confirm" (`POST /ai/suggest/confirm` → converted to a manual edge with `source='manual'`) and "Reject" (`POST /ai/suggest/reject` → deletes the candidate edge); after handling, the card is removed from the list and the canvas is refreshed;
3. **No reliance on in-memory cards**: any `source='ai'` edge on the canvas can be "confirmed as a manual edge" in `EdgeDetailPanel` (also via `/ai/suggest/confirm`, located by the four-tuple of edge endpoints); deleting the edge goes through `DELETE /edges/{id}` (the panel notes "deleting is equivalent to rejecting the candidate");
4. All of the above confirm/reject/generate entry points require `canEdit` (editor+); viewer is read-only.
5. Filter fallback: the two `DatasetSidebar` switches "Hide AI suggested edges" and "Show confirmed lineage only" remove `source='ai'` edges at the display layer (confidence filtering treats edges without confidence as 1).

---

## 8. Frontend Representation of Role Permissions

The role system is described in business model §2 (viewer read-only / editor can write business data / admin manages the system). `lib/roles.ts` provides three pure functions: `isEditor` (editor or admin), `isAdmin`, `roleLabel` (Administrator/Editor/Read-only).

> **Important boundary**: role control in the frontend is **only a UX layer** — hiding write entry points and disabling handle connections so users encounter fewer 403s. Real permission checks always live in the backend `require_role` guard (each route declares its minimum role; the role is read from the current database value). Calling the API directly to bypass the frontend UI is still rejected by the backend; see [./04_frontend-backend-boundaries.md](./04_frontend-backend-boundaries.md) (P3 principle). The header comment in `lib/roles.ts` also states this.

UI behavior per role (all are "do not render the write entry point" rather than graying out):

| Capability | viewer | editor | admin | Implementation location |
|---|---|---|---|---|
| Create edges by dragging handles on the canvas | handles not connectable (`nodesConnectable=false`, `DatasetNode.connectable=false`) | Yes | Yes | `Workspace` → `LineageCanvas` / `DatasetNode` |
| "Edit/Delete" buttons in the edge hover tooltip | Hidden | Shown | Shown | `LineageEdge.tsx` (`canEdit`) |
| Field editing (description/type/locator) | Edit button hidden | Yes | Yes | `DetailPanel` (`canEdit`) |
| Edge edit/delete, AI candidate confirmation | Hidden | Yes | Yes | `EdgeDetailPanel` (`canEdit`) |
| Annotation input | Shows read-only notice "The current role is read-only and cannot add annotations" | Yes | Yes | `AnnotationSection` (`canWrite=canEdit`) |
| Generate AI candidate lineage | Hidden | Yes | Yes | `DetailPanel` |
| Create version tags | Shows "Read-only roles cannot create tags or roll back versions" | Yes | Yes | `VersionDrawer` (`canWrite=isEditor`) |
| Roll back to a version tag | Hidden | Hidden | Yes (`ConfirmDialog` confirmation) | `VersionDrawer` (`canRollback=isAdmin`) |
| User management entry | No menu item | No menu item | User menu shows "User Management"; only admin can open the modal | `TopBar` + `Workspace` (`usersOpen && admin` double guard) |
| AI assistant chat | Yes (backend viewer+) | Yes | Yes | `AiAssistantDrawer` (no role gate; follows the backend) |
| Sign out | Yes | Yes | Yes | `TopBar` user menu |

The role labels themselves (`roleLabel`) are displayed in the `TopBar` user area and user menu, and in the `UserManagementModal` list.

---

## 9. Known Gaps and Frontend Coverage Gaps

### 9.1 Frontend Entries in the Root README "Known Gaps" (Retained As-Is)

- **User management prototype fidelity**: `UserManagementModal` currently supports only the user list + adding users (including role selection at creation); the per-row role dropdown and RBAC permission matrix on the prototype's "Versions and Users" screen are not implemented yet. Role changes require a new admin API and involve business rules such as "whether administrators may change their own role / how to guarantee at least one admin remains" (`[TBD-BIZ]`, to be implemented after product confirmation); the UI already marks this limitation explicitly (fixed footer notice in the modal: "No API is available yet for role changes or disabling accounts; the per-row role dropdown and RBAC permission matrix from the prototype are not implemented yet; if adjustments are needed, the backend must add the admin API").
- **Annotation management**: annotations are append-only; there is currently no edit/delete entry (consistent with the business model).

### 9.2 Frontend Coverage Gaps Not Mentioned in the README (Backend Endpoints Without Frontend Entry Points)

The following backend endpoints (see the root README "API Overview") have **no frontend UI entry point at all** and can currently only be operated with API tools (curl, etc.); whether to add an "import wizard" UI is `[TBD-FE]` (the low-fidelity prototype `docs/02_prototype/clew-lofi-prototype.html` already includes an "import wizard" screen as the UI baseline, but it is not implemented):

| Endpoint | Description | Frontend status |
|---|---|---|
| `POST /files` | Upload/register a managed source file | No entry point; the frontend can only download existing files via `downloadSourceFile` in `PreviewModal` |
| `GET /files` | Source file list | No entry point |
| `POST /import` | Submit an import manifest (multipart) | No entry point — the entire M1 "upload source file + import manifest" flow has no UI; demo data relies on the backend `seed_demo` |
| `POST /import/batches/{id}/rollback` | Roll back by import batch (admin) | No entry point; `VersionDrawer` only lists batches, and the only rollback entry is "roll back by version tag" |

All other endpoints (auth/datasets/lineage/fields/edges/annotations/changes/version-tags/users/ai and file download) have corresponding frontend entry points (see §5, §6).

### 9.3 Behavioral Differences Between the Design Document and the Implementation (Code Prevails)

| # | Design document statement | Implementation status |
|---|---|---|
| 1 | §5 "zustand for canvas state" | zustand is not used (`package.json` has no such dependency); all canvas and page state is React built-in `useState`/`useRef`, held centrally by `Workspace` (§4) |
| 2 | §5.2 three graph entry points: "search to graph, click to expand, AI conversation to graph" | Two are implemented: "dataset selection/search" and "AI conversation to graph"; **clicking a node on the canvas to expand its neighborhood** is not implemented (the subgraph is driven only by the seed dataset + hop count) `[TBD-FE]` |
| 3 | §6.2 lists tools such as `trace_upstream`/`trace_downstream`/`get_subgraph`/`suggest_lineage` | The actual tool set is 5 read-only tools: `search_fields`/`get_field_details`/`trace_lineage`/`get_field_history`/`mark_highlight` (consistent with `TOOL_LABELS` in `AiAssistantDrawer` and the backend README M4); graphs are wired through the `graph` returned by `trace_lineage`, and highlights through the `highlights` returned by `mark_highlight`; lineage suggestions use REST `POST /ai/suggest` (triggered from field details) and are not part of the chat tool set. The root README and the code prevail |
| 4 | §5.1 filtering "by dataset name, field name, confidence, **edit source**" | Confidence threshold, hide AI suggested edges, and show confirmed lineage only are implemented (equivalent to excluding `source='ai'`); filtering separately by `manual`/`imported` source is not supported |
| 5 | §5.1 field locating "hover/click opens a locator card" | Different form: clicking a field row opens the persistent `DetailPanel` on the right (with human-readable locator, copy locator, source preview entry); capability is equivalent (the preview includes highlighted column/header path/row range/JSONPath hits), but there is no hover card |

Items 1–3 above are inconsistencies between the design document and the code (the design document was written before implementation); 4–5 are interaction-form trade-offs that do not change the capability surface. If these are later completed according to the design document, this document and [./04_frontend-backend-boundaries.md](./04_frontend-backend-boundaries.md) must be updated in sync.

---

## 10. Internationalization (i18n, Added 2026-10)

### 10.1 Approach and Structure

A self-built lightweight i18n, with no third-party dependencies (aligned with 00 §7.12 and the repository rule "unaudited dependencies are prohibited"):

```
src/i18n/
├── index.tsx    # I18nProvider + useI18n() → { locale, setLocale, t }; {var} interpolation;
│                # localStorage['clew.locale'] persistence; syncs <html lang> and document.title
├── zh.ts / en.ts  # Aggregate dictionaries (spread only, no entries)
└── dicts/       # Modules by namespace: common.ts (shared across components) + one <ns>.ts per component
```

- Dictionary module pattern: `export const zhXxx = { 'ns.key': '中文' } as const;` + `export const enXxx: Record<XxxKey, string> = { ... }` — en is constrained by a local type so its keys exactly match zh, and a missing key fails at `tsc` build time.
- `t(key, params?)`: `{var}` placeholder interpolation; plural semantics are avoided through wording (e.g. `'{count} fields'`); no ICU plural rules.
- Any React component (including subcomponents within a file) calls `useI18n()` directly; module-level utility functions (such as `humanizeLocator`, `roleLabel`, HistoryDrawer's `valueText`) receive `t` explicitly as a parameter.
- Defaults to `zh`, with no automatic browser language detection; switching takes effect immediately (React state), and the preference is persisted to `localStorage['clew.locale']`.

### 10.2 Conventions and Boundaries

- Entry keys use flat naming `namespace.entry` (`topbar.searchPlaceholder`, `importWiz.title`, …); entries reused across components go into `dicts/common.ts` (`common.*`), and a new shared entry must be checked to ensure no existing key has the same name with different semantics.
- Parallel refactoring convention: each component refactor touches only "the component's own file + its namespace dictionary module"; `zh.ts`/`en.ts` aggregate registration is done once by the infrastructure work, and `common.ts` must not be edited in parallel.
- Not translated (displayed as-is): backend error messages (`ApiError.message` is passed through verbatim; the backend has no error-code contract and emits English `detail` strings, shown as-is in both UI locales — follow-up: backend error codes + frontend mapping), AI answer content (the backend SYSTEM_PROMPT already answers in the language of the question), business data (dataset/field names), technical identifiers (source values, csv/xlsx/json, sheet names), and code comments.
- Locale-aware utility functions: `formatCount(value, locale)` (`Intl.NumberFormat` zh-CN/en-US); `<html lang>` and `document.title` are synchronized by the Provider's effect.
