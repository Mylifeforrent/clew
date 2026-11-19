# Clew Frontend (production directory)

Clew's production frontend: a React SPA for field-level data lineage verification and collaboration. Visuals and interactions take `docs/04_hifi/00_design-overview-and-tokens.md` plus the 01–06 page documents as the single design source of truth; the API contract follows `docs/03_dev/05_api-reference.md`; implementation notes live in `docs/03_dev/02_frontend-development.md`.

## Relationship with prototype

- `prototype/frontend/` is the prototype workspace whose visual migration to the hi-fi spec is already complete; this directory was **ported** from it as the baseline (config and `src/` copied from the same source), then checked screen by screen against hi-fi 01–05 with a few deviations corrected.
- Incremental capability in this directory over prototype: the **import wizard** (full hi-fi 06 spec, `ImportWizardModal`) — source file upload (`POST /files`), manifest import (`POST /import`), batch report and report download; there was no frontend entry for these in prototype before.
- Both directories currently coexist; prototype is kept for reference only, and future work evolves in `frontend/`.

## Development commands

```bash
cd frontend
npm install        # npm is the only package manager (pnpm / yarn are forbidden)
npm run dev        # vite dev server → http://localhost:5173 (proxy → 127.0.0.1:8000)
npm run build      # tsc -b && vite build (type check + dist/ build output)
npm run typecheck  # type check only
npm run preview    # preview the build output locally
```

Dependencies are frozen to match prototype (react 19 / @xyflow/react / @dagrejs/dagre + Vite + Tailwind v3) and no dependencies are added: no UI component library, no router, no state management library, no HTTP library (fetch only), no icon library (`components/Icon.tsx` ships 43 SVG icons).

Start the backend before development (see the repository root README); when it is not running, the sign-in page and workspace show an error card with a retry entry instead of a blank screen.

## Directory structure

```
frontend/
├── index.html / vite.config.ts / tsconfig.json / tailwind.config.cjs / postcss.config.cjs
├── public/favicon.svg
└── src/
    ├── main.tsx / App.tsx      # entry and session switching (401 expiry event → back to sign-in)
    ├── index.css               # Tailwind directives + .field-input + React Flow canvas customization + reduced-motion
    ├── types.ts                # all API types (single type export point)
    ├── lib/                    # api.ts (fetch wrapper/ApiError/session), layout, format, roles, etc. — 7 files
    └── components/             # 23 components (22 ported + new ImportWizardModal)
```

## Import wizard (new in this directory)

- Entry: the TopBar primary "Import" button, rendered only for editor and above (the "do not render write entries" pattern; real authorization is in the backend).
- Four-step wizard: ① upload source files (per-file `POST /files`, sha256 dedup) → ② upload manifest / pick format (csv two-file / xlsx / json, validate format match locally) → ③ validate and execute (`POST /import` completes in one transaction) → ④ batch report (four stat cards, rejected-row table, report JSON download).
- While busy uploading/submitting, Esc, the mask and close are locked; when files are already uploaded, closing goes through a ConfirmDialog first; the "Done" callback makes Workspace refresh the dataset list and subgraph.

## Known gaps

- "Roll back by batch" (`POST /import/batches/{id}/rollback`) still has no frontend entry — hi-fi 06 explicitly omits a rollback button on batch rows, a follow-up item `[TBD-FE]`; the versions drawer keeps "roll back by version tag".
- The header's pre-allocated "will be imported as version v{n+1}" badge takes the max `version_no + 1` from `GET /import/batches`; it is a hint-only prediction, and the actual version comes from the `POST /import` response. When the batch list cannot be fetched, the badge is omitted.
- User management still supports only listing + creating users (role changes have no backend API, `[TBD-BIZ]`, same as prototype).
- Design §5.1 "click a node to expand its neighborhood" and other differences from the current code are recorded in `docs/03_dev/02_frontend-development.md` §9.3 (this directory has not changed these trade-offs).
