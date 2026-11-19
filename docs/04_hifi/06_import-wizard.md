# 06 · Import Wizard

> **This screen is the design baseline for a [TBD-FE] feature gap: it is not implemented in this round of high-fidelity development and is provided only as a reference for future work.** The backend capabilities are all in place (`POST /files` source file upload, `POST /import` manifest import in three formats, batch report, rollback by batch); only the frontend entry point is missing (dev document §9.2 explicitly lists it as a frontend coverage gap). This document defines visual and layout specs only, with no implementation schedule.
>
> Positioning: the "data ingestion" entry point of the workbench. It presents the three-step import (① upload source files -> ② upload manifest -> ③ validate and ingest, backend document §6) as an **xl modal wizard** driven by a four-step bar: **upload source files -> upload manifest/choose format -> validate and execute -> batch report**. Compared with 01-05, this is the only entirely new screen; all controls reuse the 00 §7 general specs, with only a few new forms registered (see "Tokens to Be Added" at the end).
>
> Sources and references:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (sole source of tokens; references use the form "00 §x.x"; modal §7.6, buttons §7.1, inputs §7.2, badges §7.4, chip §7.5, empty state §7.9, loading §7.10, icons §7.11, layering §6)
> - `docs/02_prototype/clew-lofi-prototype.html` import wizard screen (information-architecture baseline: step bar + file chip row + four-cell stats + rejected-row table + report actions; the "Import Data" primary button in the canvas screen's top bar is this screen's entry point)
> - `docs/03_dev/02_frontend-development.md` §9.2 (POST /files, GET /files, POST /import, and rollback by batch all have no frontend entry, `[TBD-FE]`), §8 (the role pattern of "not rendering write entry points")
> - `docs/03_dev/05_api-reference.md` §3 (POST /files: csv/xlsx/json allowlist, sha256 dedup `deduped`, 413 limit, any file error fails the whole batch), §4 (POST /import: `format` + `source_file_ids` + manifest file; row-level failures go into the report without producing an HTTP error; response `{batch_id, version_no, report}`), §14 A5 (report `{summary: total/ok/merged/rejected, items: [{status, kind, ref, reason, source_row}]}`)
> - `docs/03_dev/03_backend-development.md` §6 (import pipeline: three-format normalization, row-level rejection, actual-file verification, batch persistence and reporting)
> - Component source: no corresponding component (entirely new design); icon references are limited to the 42 existing in `Icon.tsx` (gap noted in "Tokens to Be Added" #4 at the end)
>
> Scope constraint: a pure design document; functional logic is unchanged and no dependencies are added; backend endpoints and interaction flows follow the API document, and this document does not invent capabilities the backend lacks (the two differences between the low-fidelity design and backend capabilities are covered in the §3.5 mapping note and the §3.6 notes).

---

## 1. Page Positioning and Entry

| Item | Description |
|---|---|
| When it is shown | TopBar "Import Data" button (**to be added in the future**, see below) -> `Workspace` conditionally renders the modal; the entry is rendered only for editor and above (both POST /files and POST /import require editor; viewer "does not render write entry points", 02 §8 pattern) |
| Entry button (future spec) | primary `h-8 px-2.5` (00 §7.1) + upload icon at 14px, labeled "Import Data"; inserted between 02 §3.1#4 global search and #5 AI assistant button (matching the low-fidelity canvas screen top bar order); icon gap in "Tokens to Be Added" #4 at the end |
| Related components | No existing component. Suggested name `ImportWizardModal` (xl modal step, 00 §4.5/§7.6), containing a step bar and four step panels |
| When it closes | Esc / overlay / close button / the "Done" action in the completed state; **Esc and the overlay are locked during upload and submission** (same as the ConfirmDialog busy rules, 05 §8#2); if files have been uploaded, closing asks for confirmation first (reusing ConfirmDialog, 05 §3.4 non-danger branch) |
| Data contract | Step ① = `POST /files` (returns an array of source file records; `id` feeds `source_file_ids`); step ③ = `POST /import` (returns `{batch_id, version_no, report}`); step ④ only consumes that response, with no extra requests |
| Completion side effects | "Done" closes the modal and notifies `Workspace` to refresh the dataset list and subgraph; "View version drawer" reuses the TopBar "Versions" entry to open `VersionDrawer` (05 §1), with the new batch appearing first in the batch list |
| Implementation status | `[TBD-FE]` entirely new design, **not implemented in this round** (dev document §9.2) |

## 2. Layout Structure

Modal step: **xl `max-w-[880px]`** (the largest of the four modal steps in 00 §4.5; a form-heavy flow plus a report table needs horizontal space, same step as 03 PreviewModal). Layering: overlay `z-50` + panel `z-[51]` (00 §6/§7.6).

```
┌────────────────────────────────────────────────────────────────┐ Overlay z-50 bg-slate-900/40
│ ┌────────────────────────────────────────────────────────────┐ │ Panel z-[51] max-w-[880px] max-h-[85vh]
│ │ (1) Header  h-12  px-4  border-b border-line-soft          │ │ [upload icon block] Import Data · version pre-allocation badge │[✕]
│ ├────────────────────────────────────────────────────────────┤ │
│ │ (2) Step bar  py-3  px-4  border-b border-line-soft        │ │ (1) Upload source files ─ (2) Upload manifest ─ (3) Validate ─ (4) Report
│ ├────────────────────────────────────────────────────────────┤ │
│ │ (3) Step body  flex-1  overflow-y-auto  bg-page  px-4 py-4 │ │ four step panels (see §3.3-3.6)
│ │    · Step 1: dropzone + uploaded file list                 │ │
│ │    · Step 2: format radios + bound chips + manifest        │ │
│ │    · Step 3: summary card / running / file-level error     │ │
│ │    · Step 4: success bar + stats + rejects + actions       │ │
│ ├────────────────────────────────────────────────────────────┤ │
│ │ (4) Footer  h-12  px-4  border-t border-line-soft          │ │ [← Previous]  Step n/4  [Start validation and import →]
│ └────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

Area dimensions (all reference 00 tokens):

| Area | Size / spacing |
|---|---|
| Panel | `w-full max-w-[880px] max-h-[85vh] flex flex-col`, `rounded-xl border border-line bg-card shadow-modal` (00 §7.6 xl step) |
| Header | `h-12` (00 §7.6 modal header); title `text-[14px] font-semibold text-ink` |
| Step bar | `shrink-0 border-b border-line-soft px-4 py-3`; nodes `h-6 w-6`, connector lines `h-px flex-1` |
| Step body | `min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4` (00 §7.6 modal body; the `bg-page` page background sets off the white card, 00 §1.2 principle 2) |
| Footer | `h-12` (00 §7.6 modal footer); primary action `h-9` lg step (00 §4.5 "wizard primary action 36px"), secondary actions `h-8` |
| Content cards | White cards inside the step body are always `rounded-xl border border-line bg-card`; card spacing `space-y-4` (00 §4.1 16px between blocks) |

## 3. Area-by-Area Visual Specs

### 3.1 Modal Skeleton and Header (h-12)

- Overlay: `fixed inset-0 z-50 bg-slate-900/40 animate-fade-in` (clicks do not close it while an upload or submit is busy, §1); panel `relative z-[51] mx-auto flex max-h-[85vh] w-full max-w-[880px] flex-col overflow-hidden rounded-xl border border-line bg-card shadow-modal animate-modal-in`, `role="dialog" aria-modal="true" aria-labelledby`.
- Header (00 §7.6): left: icon block `flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700` (upload icon 16px, gap in Tokens to Be Added #4) + title `text-[14px] font-semibold text-ink` "Import Data" + a version pre-allocation badge on the right (shown from step ③) `rounded-full border border-line bg-subtle px-2 py-px font-mono text-[11px] text-ink-muted` reading "Will be stored as version v{n+1}" (n is the current highest version number; the report page replaces it with the actual value). Right: a ghost close icon button (spec same as 05 §3.1: `flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft` + shared ring).
- The header note "Three-step ingestion: source files -> manifest -> validation report" goes in the first note card of the step body before step ②, not in the header (consistent with the single-line header convention in 04/05).

### 3.2 Step Bar (Stepper)

```html
<nav aria-label="Import steps" class="flex items-center gap-2">
  <!-- Each step: node + label; connector line between nodes h-px flex-1 -->
  <ol class="flex w-full items-center gap-2">
    <li class="flex items-center gap-1.5">
      <span class="flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-medium leading-none
                   {state classes, see table below}">1</span>
      <span class="text-[12px] {label state classes}">Upload source files</span>
    </li>
    <span class="h-px flex-1 {completed bg-blue-300 | not yet bg-line}" aria-hidden="true" />
    <!-- ...steps 2/3/4 have the same shape; completed steps swap the node content for a check icon at 12px -->
  </ol>
</nav>
```

Four node states (the number sits inside the node; completed nodes show a 12px check instead; connector lines have two states, `bg-blue-300` / `bg-line`, 00 §2.1 blue-300 canvas decorative-line step):

| State | Node classes | Label classes |
|---|---|---|
| Completed | `bg-success-soft text-success-deep` (00 §2.3 success semantics) | `text-[12px] text-ink-soft` |
| Current | `bg-blue-600 text-white font-semibold` (current-item semantics, 00 §2.1) | `text-[12px] font-medium text-ink` |
| Upcoming | `border border-line bg-card text-ink-faint` | `text-[12px] text-ink-faint` |
| Completed after returning from an error | Same as completed (errors are presented inside the step body and the step bar never turns red - rejections in the report are a normal business result, not a flow failure) | Same as completed |

The step bar is display-only (`aria-current="step"` marks the current step) and does not support click navigation; going back only happens through "Previous" in the footer. The spec gap is registered in "Tokens to Be Added" #1 at the end.

### 3.3 Step ① · Upload Source Files

**Note card (first in the step body)**: `flex items-start gap-2 rounded-lg border border-line bg-card px-3 py-2.5 text-[12px] leading-5 text-ink-muted` (info icon 12px `text-ink-faint`) "Step one: upload first-hand source files. The import manifest references them by file ID or original file name; identical content (sha256) is deduplicated and reused automatically."

**Dropzone (main upload area, see "Tokens to Be Added" #2 at the end)**:

```html
<label class="group flex cursor-pointer flex-col items-center justify-center gap-2
             rounded-xl border-2 border-dashed border-line-strong bg-page px-6 py-10 text-center
             transition-colors duration-150 hover:border-blue-300 hover:bg-blue-50/40
             focus-within:ring-2 focus-within:ring-blue-600/60">
  <Icon name="file" size={24} className="text-ink-faint group-hover:text-blue-600" />
  <span class="text-[13px] font-medium text-ink-soft">Drag source files here, or click to choose</span>
  <span class="font-mono text-[11px] text-ink-faint">csv / xlsx / json · up to 50MB per file (MAX_UPLOAD_MB) · deduplicated by sha256</span>
  <input type="file" multiple accept=".csv,.xlsx,.json" class="sr-only" />
</label>
<!-- Drag-over: border-blue-400 bg-blue-50/60; disabled (uploading): opacity-50 cursor-not-allowed -->
```

(`border-2 border-dashed` is a functional drop-target border, not decoration (00 §4.3 bans decorative thick borders); to apply that rule strictly it can drop to `border` + `bg-subtle`, registered in Tokens to Be Added #2 for 00 to decide. Multi-select via `multiple`; whether the frontend calls `POST /files` per file or submits the whole batch at once follows API document §3.1 `files[]` - this document fixes visuals only and does not freeze the implementation `[TBD-FE]`.)

**Uploaded file list** (container `divide-y divide-line-soft overflow-hidden rounded-xl border border-line bg-card`, row `flex items-center gap-2.5 px-3 py-2.5`):

| Element | Spec |
|---|---|
| File icon | file 14px `shrink-0 text-ink-faint` |
| File name | `min-w-0 flex-1 truncate font-mono text-[13px] text-ink` (`title` holds the full name) |
| Size | `shrink-0 font-mono text-[11px] tabular-nums text-ink-faint` (e.g. 12.4MB) |
| Type chip | `rounded border border-line bg-page px-1.5 py-px font-mono text-[11px] uppercase text-ink-faint` (csv/xlsx/json; same spec as the format chip in 05 §3.1) |
| Dedup badge | Reused: `rounded-full border border-transparent bg-info-soft px-1.5 py-px font-mono text-[11px] text-info-deep` "reusing existing #id" (`deduped: true`); newly registered: `border-line bg-subtle text-ink-muted` "newly registered #id" (00 §7.4 status badge + 05 Tokens to Be Added #2 neutral step) |
| Remove button | icon button `h-6 w-6 rounded-md text-ink-faint hover:text-danger-deep hover:bg-danger-soft` (close 12px, `aria-label="Remove file {name}"`; this only drops the frontend reference, and already-registered records are covered by sha256 dedup) |
| Uploading row | a small spinner (00 §7.10) appended to the right of the name + `text-[11px] text-ink-faint` "Uploading..." |
| Single-file failure row | the whole row `bg-danger-soft`, reason `text-[12px] leading-4 text-danger-deep` (backend 400/413 detail; any file error fails the whole batch, so the list keeps successful items + a danger summary bar at the top, see §5) |

**Empty state** (no files and not uploading): the Dropzone itself is the empty state (icon + copy), so no separate 00 §7.9 empty-state block is used; the footer "Next" button is disabled (progress requires "at least one file uploaded", which fronts the 400 semantics of API §3.1).

### 3.4 Step ② · Upload Manifest / Choose Format

**Bound file echo** (the result of step ①, i.e. the source of `source_file_ids`): eyebrow `font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint` "Bound source files · N" + chips `flex flex-wrap gap-1.5`, chips per 00 §7.5: `inline-flex h-6 items-center gap-1 rounded-md border border-line bg-card px-2 font-mono text-[11px] text-ink-muted` "#3 · order_details.xlsx". At the end of the row, a "Change" ghost sm `h-7 px-2 text-[12px]` (chevron-left 12px, "go back to the previous step to change").

**Format selection** (`fieldset` + `legend` sr-only "Manifest format"; three radio cards in a row `grid gap-3 sm:grid-cols-3`):

```html
<label class="flex cursor-pointer items-start gap-2.5 rounded-lg border border-line bg-card px-3 py-2.5
             transition-colors duration-150 hover:border-blue-300
             {selected: border-blue-300 bg-blue-50}">
  <input type="radio" name="manifest-format" value="csv" class="mt-0.5 h-4 w-4 shrink-0 accent-blue-600" />
  <span class="min-w-0">
    <span class="flex items-center gap-1.5 font-mono text-[13px] font-medium text-ink">csv</span>
    <span class="mt-1 block text-[12px] leading-4 text-ink-muted">two files: datasets.csv + lineage.csv (UTF-8, BOM compatible)</span>
  </span>
</label>
<!-- xlsx: a single workbook with two sheets, datasets / lineage; json: a single file {"datasets": [], "lineage": []} (the JSON snippet is font-mono) -->
```

**Manifest file upload** (changes with the format; compact dropzone: `px-4 py-6`, otherwise the same spec as §3.3):

| Format | Upload slots |
|---|---|
| csv | two side-by-side slots (`grid gap-3 sm:grid-cols-2`): "datasets.csv (dataset and field manifest)" and "lineage.csv (lineage manifest)", each with a dropzone + selected-file row (file name + remove button) |
| xlsx / json | a single dropzone: "Manifest workbook (xlsx)" / "Manifest file (json)" + selected-file row |

**Column structure reference** (collapsible `<details>`, reusing the 03 §3.2⑩ spec: `rounded-xl border border-line-soft bg-card`; summary `flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13px] font-medium text-ink-muted hover:text-ink`, chevron `group-open:rotate-180`): datasets columns `dataset_id / dataset_name / field_name / field_type / src_file / src_type / src_locator / description`; lineage columns `from_dataset / from_field / to_dataset / to_field / transform / confidence / note`. Content `border-t border-line-soft px-3 py-2.5 font-mono text-[11px] leading-4 text-ink-muted bg-subtle/50`. The note that `src_file` accepts a source file ID or a file name in this batch (must be unique) is folded into this block (existing backend rule, API §4.1).

### 3.5 Step ③ · Validation and Execution

**Submit summary card** (`rounded-xl border border-line bg-card`, row `flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2.5` + `divide-y divide-line-soft`):

| Row | label (`text-[12px] text-ink-muted`) | Value |
|---|---|---|
| Manifest format | left | `font-mono text-[13px] font-medium text-ink` (csv/xlsx/json) |
| Bound source files | left | chips (§3.4 spec), with a `font-mono text-[11px] tabular-nums text-ink-faint` count "N" |
| Manifest files | left | `truncate font-mono text-[13px] text-ink` (for csv, the two file names joined with ", ", `title` holds the full value) |

Info bar below the summary card (00 §2.3 info group): `flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5 text-[12px] leading-5 text-blue-800` (info 12px `text-blue-700`) "After submission the backend performs row-level validation and ingestion in the same transaction: row-level failures go into the report and do not block successful rows; manifest file-level errors (missing sheet, missing header, root parse failure, etc.) fail the whole batch."

**Running state** (after clicking "Start validation and import" in the footer, replaces the entire step body):

```html
<div class="flex flex-col items-center justify-center gap-3 py-16" role="status" aria-live="polite">
  <span class="h-6 w-6 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" aria-hidden="true" />
  <p class="text-[13px] font-medium text-ink-soft">Validating and importing...</p>
  <p class="text-xs text-ink-muted">A large manifest may take tens of seconds; do not close this window</p>
</div>
```

(The backend `POST /import` returns once and offers no streaming progress endpoint, so the running state only has an indeterminate spinner + copy `[ASSUMPTION]`; the footer primary action is disabled and busy.)

**File-level error state** (400/404/413/422): danger card `rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3` (00 §2.3; `role="alert"`) - the title `text-[13px] font-medium text-danger-deep` "Import not executed" + the backend detail verbatim `mt-1 text-[12px] leading-5 text-danger-deep` + a "Back to previous step" action, secondary `h-8 px-3 text-[12px]` (a refresh 12px "retry upload" is not needed - errors are usually manifest problems, so go back to step ②, fix, and resubmit).

> **Low-fidelity -> backend capability mapping note**: the low-fidelity two-stage flow "validation report (pre-check) -> confirm ingestion as version v3" has no corresponding backend endpoint - `POST /import` completes validation and ingestion in the same transaction, and rejected rows do not block successful rows (backend document §6.4). This design therefore defines step ③ as "validation and execution" (submit means execute); the low-fidelity "confirm ingestion as version v3" button is **not kept**, while its "will be stored as version v3" badge is kept as the header's version pre-allocation hint (§3.1), with the actual version number presented on the step ④ report page. If a true two-stage flow (pre-check dry-run, then ingestion) is needed later, a new backend endpoint is required `[TBD-BE]`.

### 3.6 Step ④ · Batch Report (Completed State)

**Success bar**: `flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-success/25 bg-success-soft px-3 py-2.5 text-[13px] leading-5 text-success-deep` (check 12px) - "Import complete · stored as version v{version_no} · batch #{batch_id}" (`font-mono tabular-nums`).

**Stat row** (`grid grid-cols-2 gap-3 sm:grid-cols-4`, cards `rounded-xl border border-line bg-card p-3 text-center`; numbers `text-lg font-bold tabular-nums leading-6` (00 §3.2 18px stat-number step + §3.3 large stats 700), labels `mt-0.5 text-[12px] text-ink-muted`):

| Card | Number color | Notes (label text) |
|---|---|---|
| total | `text-ink` | Total rows in the manifest |
| ok | `text-success-deep` (00 §2.3 deep step as text on white, §2.6 6.81 same family passes) | Succeeded (created / updated / unchanged) |
| merged | `text-warning-deep` | Merged (same key in the same batch, later entry wins) |
| rejected | `text-danger-deep`; when rejected > 0 the card border switches to `border-danger/25` | Rejected (see table below) |

(The "succeeded / skipped / failed" semantics align with the backend's three states `ok / merged / rejected` plus total; the stat card spec gap is registered in Tokens to Be Added #3 at the end, sharing its origin with 05 Tokens to Be Added #4, the diff count pill.)

**Rejected-row table** (row-level error localization; rendered only when rejected > 0):

```html
<div class="overflow-hidden rounded-xl border border-line bg-card">
  <div class="flex items-center gap-2 border-b border-line bg-subtle px-3 py-2
               font-mono text-[11px] font-medium text-ink-muted">  <!-- header row bg-subtle, 00 §2.2 -->
    <span class="w-12 shrink-0">Row</span>
    <span class="w-16 shrink-0">Type</span>
    <span class="w-[220px] shrink-0">Object</span>
    <span class="min-w-0 flex-1">Reject reason</span>
  </div>
  <ul class="divide-y divide-line-soft" role="list">
    <li class="flex items-start gap-2 px-3 py-2.5 hover:bg-blue-50/70">  <!-- row hover same as 00 §2.5 field row -->
      <span class="w-12 shrink-0 font-mono text-[12px] tabular-nums text-ink-soft">{source_row}</span>
      <span class="w-16 shrink-0">{kind badge: field/lineage edge, neutral chip spec §3.3}</span>
      <span class="w-[220px] shrink-0 break-all font-mono text-[12px] text-ink">{ref}</span>
      <span class="min-w-0 flex-1 break-words text-[12px] leading-5 text-ink-soft">
        <span class="mr-1.5 inline-flex h-5 items-center rounded-full border border-transparent bg-danger-soft px-1.5 font-mono text-[11px] text-danger-deep">Rejected</span>
        {reason}
      </span>
    </li>
  </ul>
</div>
```

(The reject reason body uses `ink-soft` - the error semantics are already carried by the leading badge and the stat cards, so long text stays readable as body copy; `ref` is `dataset_id.field_name` for fields and `ds.field-->ds.field` for edges (API A5), in mono. The low-fidelity "validation stage" column has no corresponding field in the backend report item (it can only be inferred from the `reason` prefix), so this design omits that column; the full reason text serves as the locator, and a `stage` field can optionally be added `[TBD-BE]`.)

**Full results collapse** (optional): `<details>` (spec same as the column structure reference in §3.4) "All {total} results" - `ok` rows get a success-group status badge "Succeeded" + a reason that may be `unchanged`; `merged` rows get a warning-group badge "Merged" + an override note.

**Info bar**: info combination (same rules as §3.5) "Rejected rows do not block successful rows; all changes (including merges) are written to change_log one by one and can be rolled back by batch (admin)." - matching the low-fidelity copy; the closing note points the rollback entry to 05 (batch rows provide no rollback button; rollback by batch, `POST /import/batches/{id}/rollback`, is likewise an endpoint with no frontend entry and is out of scope for this page `[TBD-FE]`).

**Footer actions** (step ④ overrides the default footer): on the left, "Import again" ghost `h-8` (plus 12px; resets the wizard to step ①, with step ① files optionally kept), and "Download full report (JSON)" secondary `h-8` (download 12px; serializes the submit response's `{batch_id, version_no, report}` into a Blob download, with no second request `[ASSUMPTION]`); on the right, "View version drawer" secondary `h-8` (tag 12px) + "Done" primary `h-9` (check 12px; closes and refreshes).

## 4. Component State Specs

| Component | default | hover | active/focus | disabled/loading | selected |
|---|---|---|---|---|---|
| Header close | ghost `text-ink-faint` | `bg-subtle text-ink-soft` | shared ring (00 §7.1) | disabled `opacity-50` while upload/submit is busy | - |
| Step bar node | state table §3.2 | - (non-interactive) | - | - | current `bg-blue-600 text-white` |
| Dropzone | `border-2 dashed border-line-strong bg-page` | `border-blue-300 bg-blue-50/40` | `focus-within:ring-2 ring-blue-600/60` (carried by the label) | uploading `opacity-50 cursor-not-allowed` | drag-over `border-blue-400 bg-blue-50/60` |
| File remove button | `text-ink-faint` | `text-danger-deep bg-danger-soft` | shared ring | hidden while uploading | - |
| Format radio card | `border-line bg-card` | `border-blue-300` | shared ring (focus-visible on the input) | - | `border-blue-300 bg-blue-50` (radio `accent-blue-600`) |
| Previous | secondary `h-8` (hidden in step ①) | `border-blue-400 text-blue-700` | ring | disabled while submit is busy | - |
| Next / Start validation and import | primary `h-9` (lg step) | `bg-blue-700` | `active:bg-blue-800` + ring | disabled and neutralized when preconditions are not met (no files / no manifest); spinner "Importing..." while submit is busy | - |
| Rejected row | `bg-card` | `bg-blue-50/70` | - | - | - |
| Done | primary `h-9` | `bg-blue-700` | ring | - | - |
| Download report / View version / Import again | secondary / ghost | each with its own hover | ring | - | - |

## 5. Data States

| Area | Empty state | Loading state | Error state |
|---|---|---|---|
| Step ① | The Dropzone is the empty state (§3.3); "Next" is disabled | Per-file-row spinner "Uploading..." + Dropzone disabled | Single-file failure row in danger; whole-batch failure (400/413) shows a danger summary bar at the top with `role="alert"` + the backend detail; retry = choose files again (sha256 dedup covers already-successful items) |
| Step ② | No format selected: the three cards have equal weight and the manifest upload area is not rendered; "Next" is disabled | - (local file selection has no network state) | A format/file mismatch is local validation: the dropzone `accept` restricts it, and a wrong pick shows a row-level danger message "The manifest file must match the selected format" |
| Step ③ summary | - (steps ① and ② are mandatory, so there is no empty state) | Running state (§3.5 spinner panel, footer primary action busy) | File-level error danger card + "Back to previous step" (400 manifest parse failure / 404 source file not found / 413 over limit / 422 missing field); network errors use the same card + a retry button |
| Step ④ | rejected = 0: the rejected-row table is not rendered and a success note appears in its place, "All rows succeeded; no rejected rows." (`text-[12px] text-success-deep`) | - (the report arrives with the response in one go) | None (reaching this step means a 201 success; failures in later actions go through a Toast, 00 §7.8) |
| Whole window | - | - | No network request on open (starts purely local); the first request happens after a file is selected in step ① |

## 6. Interaction and Motion (00 §5)

| Interaction | Motion |
|---|---|
| Modal entrance | `animate-modal-in` 250ms `out-quint` (00 §5.2) |
| Overlay fade-in | `animate-fade-in` 200ms |
| Step change | step body content `animate-fade-in` 200ms (entrance as state feedback, same convention as 04 §6); step bar nodes/connectors `transition-colors duration-150` |
| Dropzone hover / drag-over | `transition-colors duration-150` |
| Button hover / rejected row hover | `transition-colors duration-150` |
| Running-state spinner | `animate-spin` (regular loading-semantics element) |
| Stat numbers appearing | no entrance animation (the report is a verification context; avoid flicker, same convention as 05 §6) |
| All | `prefers-reduced-motion` global off switch (current index.css rules) |

## 7. Change List for Existing Components

**Entirely new design, not implemented in this round** (the import UI is a `[TBD-FE]` feature gap, dev document §9.2; there are no existing components to change). Landing points for a future implementation:

| # | Component - current - target - tokens/classes involved |
|---|---|
| 1 | `TopBar.tsx` - no import entry (the low-fidelity canvas screen top bar has an "Import Data" primary button) - add a primary `h-8` button "Import Data" (rendered for editor+, inserted between 02 §3.1#4 and #5) - 00 §7.1 primary, upload icon (Tokens to Be Added #4) |
| 2 | (new component, suggested name `ImportWizardModal.tsx`) - does not exist - xl modal four-step wizard, full spec in this document - 00 §7.6 xl step, `shadow-modal`, Stepper/Dropzone/stat card (Tokens to Be Added #1-#3) |
| 3 | `Workspace.tsx` - does not hold import state - add `importOpen` state and a completion callback (refresh datasets/subgraph, optionally open VersionDrawer) - no visual tokens, pure wiring |

(All of the above are future work items and are not part of this round's high-fidelity delivery.)

## 8. Accessibility Notes (Page-Specific)

1. **Keyboard path for file selection**: the Dropzone wraps an `sr-only` input in a `label`, so tabbing to the label and pressing Enter opens the picker; the `focus-within` ring is visible (00 §10.3).
2. **Step semantics**: the step bar has `aria-label="Import steps"` and the current step has `aria-current="step"`; the step names carry the information, so progress does not rely on color alone (completed nodes have a check icon).
3. **Upload and execution are perceivable**: file upload rows and the running-state panel both use `role="status"` (the running state also has `aria-live="polite"`); error bars use `role="alert"`.
4. **Busy locking**: during upload/submission, Esc, the overlay, close, and footer buttons are all disabled (same as the ConfirmDialog busy rules); if files have been uploaded, closing goes through a ConfirmDialog confirmation (with text explanation, not relying on the dialog alone).
5. **Form labels**: format selection uses `fieldset` + `legend` (sr-only) + `label` wrapping the radio; each manifest upload slot has visible label text ("datasets.csv...").
6. **Report readability**: rejected rows are presented as a semantic list (`role="list"`) and row numbers align in mono `tabular-nums`; the full reject reason is reachable (not a truncated title).
7. **Color is never the only encoding**: ok/merged/rejected = three semantic colors + text labels (succeeded/merged/rejected); the stat card number colors are redundant and the label text carries the meaning.
8. **Contrast spot checks**: `blue-800` on `blue-50` (8.01), `danger-deep` on `danger-soft` (5.91), `warning-deep` on `card` white (about 5.9, same step family as §2.6 warning-deep on white), `success-deep` on `card` (6.81 family) - all combinations are in the 00 §2.6 table or extrapolated from the same step; `ink-soft` report body on card is 10.36.

## Tokens to Be Added (Recommended for Write-Back to 00)

| # | Gap | Suggested value | Notes |
|---|---|---|---|
| 1 | Stepper spec | node `h-6 w-6 rounded-full text-[11px]`, four states (done `bg-success-soft text-success-deep` / current `bg-blue-600 text-white` / upcoming `border border-line bg-card text-ink-faint`) + connectors `h-px bg-blue-300 | bg-line` | 00 §7 has no wizard step bar; this page is the first (and only) consumer, so adding it to §7 is recommended |
| 2 | Dropzone upload area spec | `rounded-xl border-2 border-dashed border-line-strong bg-page px-6 py-10` (compact `px-4 py-6`); hover `border-blue-300`; drag-over `border-blue-400 bg-blue-50/60`; whether `border-2` is exempt from 00 §4.3 "no 2px+ decorative thick borders" needs a 00 ruling (the drop-target hint is a functional border) | 00 §7 has no upload-area spec; the `blue-50/40 /60` translucent steps also need registering (04 already sets a `/60` precedent) |
| 3 | Stat card spec | `rounded-xl border border-line bg-card p-3 text-center` + numbers `text-lg font-bold tabular-nums` (semantic color variants) + labels `text-[12px] text-ink-muted` | Shares its origin with 05 Tokens to Be Added #4 (diff count pill) and the 02 sidebar stats; recommend registering the "stat number" scenario uniformly (including confirming where weight 700 applies, since 00 §3.3 lists only two places) |
| 4 | `Icon.tsx` upload icon gap | none of the 42 built-in icons is an "upload" icon | Needed by both the TopBar entry and the Dropzone; recommend adding `upload` to `Icon.tsx` in the future implementation (lucide-style stroke 1.5, same §7.11 system), without introducing an icon library |
| 5 | Generic table (report table) spec | header row `bg-subtle` + `text-[11px] font-medium text-ink-muted`; rows `px-3 py-2.5` + `divide-y divide-line-soft`; row hover `bg-blue-50/70` | 00 §7 has no table spec (§2.2 only mentions that "header rows" use subtle); the batch/user lists in 05 share this shape with this page's report table, so registering them together is recommended |
