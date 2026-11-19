# 03 · Details and Preview

> Positioning: the "verification and write operations" layer of the workspace. Covers three forms: ① the persistent right-side field details `DetailPanel` and edge details `EdgeDetailPanel` (switched when clicking a canvas field row/edge); ② the source preview `PreviewModal` (CSV/XLSX/JSON three formats + highlight locator + real-file verification status); ③ `EdgeCreateModal` after dragging a handle to create an edge. All three share the same "right column/overlay" structural spec (header h-12, white background, `border-line` layering, `shadow-float`/`shadow-modal`), isomorphic to the modal and drawer skeletons in 00 §7.6/§7.7. `AnnotationSection` (annotation area) is reused inside field/edge details and is finalized on this page as well.
>
> Basis and sources:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (single source of tokens, cited as "00 §x.x"; modal §7.6, drawer §7.7, button §7.1, input §7.2, badge §7.4, chip §7.5, empty state §7.9, loading §7.10)
> - `docs/02_prototype/clew-lofi-prototype.html` lineage canvas screen right column (field details information architecture: type/description/source/source file/locator/annotation/change history) and source file preview screen (XLSX highlighted column, merged cells, anchor normalization, real-file verification)
> - `docs/03_dev/02_frontend-development.md` §6 (component responsibilities), §7.7 (AI candidate confirmation flow), §8 (UI representation of role permissions)
> - Component source: `DetailPanel.tsx`, `EdgeDetailPanel.tsx`, `PreviewModal.tsx`, `EdgeCreateModal.tsx`, `AnnotationSection.tsx`
> - Related docs: 02 (Workspace skeleton, SourceBadge spec, lineage edge colors), 06 (HistoryDrawer / ConfirmDialog detailed spec)
>
> Scope constraint: only visual and layout changes; no functional logic changes (form validation, AI confirm/reject chain, preview parsing, focus management behavior all preserved); no new dependencies, no new components.
>
> **[CONFLICT] registered item (right column width)**: 00 §4.5 explicitly states "right-side detail panel width 320px", while drawer width tiers are 360/480, and the task requires the detail panel to "align with drawer width tiers". When the two bases conflict, 00 prevails: this page implements **320px** (02 doc skeleton uses the same value), and the internal structure spec aligns with the 00 §7.7 drawer skeleton to keep the "right column family" isomorphic; whether to unify the detail right column to 360px awaits a decision from the 00 maintainers (see pending item #1 at the end), and before that decision, do not change it to 360 on your own.

---

## 1. Page positioning and entry points

| Component | Form | Entry timing | Exit timing |
|---|---|---|---|
| `DetailPanel` | Persistent right column (w-320, bottom block below xl) | Shown by default (empty-state guidance); clicking a canvas field row | Clicking an edge / close button / switching seed clears selection |
| `EdgeDetailPanel` | Same as above (mutually exclusive replacement with DetailPanel) | Clicking a canvas edge or edge tooltip "View details/Edit" | Close button / switching to a field / edge deletion success |
| `PreviewModal` | Modal (xl tier 880px, centered) | DetailPanel "Source preview" button | Esc / overlay / close button |
| `EdgeCreateModal` | Modal (md tier 560px, centered) | Canvas drag handle passes validation (editor+) | Creation success / Esc / cancel (cannot close while submitting) |
| `AnnotationSection` | Embedded block in right column | DetailPanel / EdgeDetailPanel scrolled into position | Follows panel |

## 2. Layout structure

### 2.1 Right-side detail column (DetailPanel / EdgeDetailPanel shared skeleton)

Isomorphic to the 00 §7.7 drawer (header h-12 / scroll body / sectioned content), but **persistent and space-taking** (occupies layout space, not an overlay slide-out):

```
┌────────────────────────────────────────────┐  Right column  w-[320px]  bg-card  border-l border-line
│ Header h-12  px-4  border-b                │  Left: eyebrow 11px mono + breadcrumb mono 12px
│ ┌─────────────────────────────────┬──────┐ │  Right: icon button group (history/edit/close, h-7 w-7 ghost)
│ │ Field check                     │ ⧉ ✎ ✕│ │
│ └─────────────────────────────────┴──────┘ │
│ Scroll body  flex-1  px-4 py-4             │
│  ① Badge row (type/file/source)            │
│  ② Entity title (mono 18px) + description  │
│  ③ Source file card (DetailPanel)          │
│  ④ Locator envelope card (blue-50)         │
│  ⑤ Action row: source preview / edit       │
│  ⑥ AI suggestion area (ai-soft, edit mode) │
│  ⑦ Upstream lineage card list (fields)     │
│  ⑧ AnnotationSection area                  │
│  ⑨ Change history entry row                │
│  ⑩ Raw locator <details>                   │
│  (edit mode: ② and below replaced by form) │
└────────────────────────────────────────────┘
```

### 2.2 PreviewModal (modal xl tier)

```
┌────────────────────────────────────────────────────────────────────────────┐ max-w-[880px]  max-h-[85vh]
│ Overlay z-50 bg-slate-900/40 · panel z-[51], z layers see 00 §6            │
│ ┌ Header h-12 ───────────────────────────────────────── [Copy locator][✕]┐ │ border-b border-line-soft
│ │ ⌕ icon block │ eyebrow "Source file origin / read-only" + type chip    │ │
│ │              │ title "Source preview · ds.field" 14px semibold         │ │
│ ├─ Body flex-1 overflow-y-auto bg-page px-4 py-4 ────────────────────────┤ │
│ │ ① Info card: source file + sha256 │ locator │ real-file verification   │ │
│ │ ② Preview body (aria-live): loading skeleton / error card /            │ │
│ │    CSV table / XLSX table / JSON samples                               │ │
│ ├─ Footer h-12  border-t border-line-soft ──────────────────────────────┤ │ border-t border-line-soft
│ │ Read-only note · type    [Download source file][Close]                 │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 EdgeCreateModal (modal md tier max-w-[560px])

Header h-12 (icon block + eyebrow "Manual edge creation · field-level/table-level" + title "Add lineage") → draft endpoint row at top of body (mono) → form (transformation note / confidence / remark) → hint bar → footer h-12 (Cancel / Create lineage edge).

## 3. Per-area visual spec

### 3.1 Shared right column skeleton (identical for both panels)

- Container: `relative flex w-full shrink-0 flex-col border-t border-line bg-card xl:h-full xl:w-[320px] xl:border-l xl:border-t-0` (replaces `bg-[#f8f5ed]/70/80`, `xl:w-[340px]`, `relative z-10` - z removal see 02 §2).
- Header (h-12, aligned with 00 §7.7): `flex h-12 shrink-0 items-center justify-between border-b border-line-soft px-4`.
  - Left: eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` ("Field check" / "Lineage edge check") + breadcrumb row `mt-1 flex min-w-0 items-center gap-1.5 font-mono text-[12px] text-ink-muted` (icon 12px + `dataset.id › field.name`, current segment `text-blue-700`).
  - Right: icon button group, unified spec: `flex h-7 w-7 items-center justify-center rounded-md text-ink-faint transition-colors duration-150 hover:border-line hover:bg-card hover:text-ink-soft` + unified focus ring (edit button hover `text-blue-700`); existing `aria-label` / `title` preserved.
- Scroll body: `min-h-0 flex-1 overflow-y-auto px-4 py-4 pb-7`; content switch `animate-fade-in` (200ms) preserved.

### 3.2 DetailPanel · Field details

**① Badge row**: type tag `rounded border border-line bg-card px-1.5 py-0.5 font-mono text-[11px] uppercase text-ink-muted`; file type tag (`FileTypeBadge`) same spec + file icon 12px; source badge = `SourceBadge` (02 §3.6 spec).

**② Entity title**: field name `break-all font-mono text-lg font-semibold text-ink` (the 18px "modal/drawer title" semantic is borrowed for the panel entity title; replaces the 22px `font-display`); description `mt-1.5 text-[13px] leading-5 text-ink-muted` with the "No field description" fallback preserved.

**③ Source file card**: `rounded-xl border border-line bg-card`; header row `flex items-center gap-2 border-b border-line-soft px-3 py-2` (file icon 12px `text-blue-600` + eyebrow "Source file" `text-[11px] font-medium uppercase tracking-[0.12em] text-ink-faint`); body: filename `truncate font-mono text-[13px] font-medium text-ink` + "Managed file" badge `rounded border border-line bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-muted` (neutral info badge); subline `font-mono text-[11px] text-ink-faint` "Source file #id".

**④ Locator envelope card (visual anchor of this panel)** - human-readable locator + envelope type + copy button:

```html
<section class="mt-4">
  <div class="mb-2 flex items-center justify-between">
    <h3 class="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">Source file locator</h3>
    <span class="rounded-full border border-line bg-page px-1.5 py-px font-mono text-[11px] text-ink-faint">Readable locator</span>
  </div>
  <div class="rounded-xl border border-blue-100 bg-blue-50 p-3">
    <p class="text-[13px] leading-relaxed text-blue-800">{locatorText}</p>
    <div class="mt-2.5 flex items-center justify-between gap-2 border-t border-blue-100 pt-2">
      <span class="font-mono text-[11px] text-blue-700">Locator envelope · {type}</span>
      <button class="flex items-center gap-1 rounded px-1 py-0.5 font-mono text-[11px] text-blue-700 transition-colors duration-150 hover:bg-blue-100/70 + focus ring">Copy locator</button>
    </div>
  </div>
</section>
```

Copy button three-state copy: "Copy locator" (default) / "Copied" (success semantics, icon switches to check, restores after 1600ms - existing duration preserved) / "Copy failed" (`text-danger-deep`, 1800ms).

**⑤ Action row**: `mt-4 flex items-stretch gap-2` - "Source preview" primary (`h-9 flex-1 ... bg-blue-600`, icon 14px, remove existing brand-color shadow); "Edit" secondary `h-9 px-3` (rendered only when canEdit). Bottom permission note `mt-2 flex items-center justify-center gap-1.5 text-[11px] text-ink-faint` (lock/edit icon 12px + existing two copy variants preserved).

**⑥ AI suggestion area (rendered only when canEdit, ai-color dedicated area)**:

- Outer card: `rounded-xl border border-ai/25 bg-ai-soft/40 p-3` (border opacity follows the current value `/25`; is this outside the 00 §8.1 opacity extension tiers? - see pending item #4; register the current value for now). Title row `flex items-center gap-1.5 text-[13px] font-semibold text-ai-deep` (sparkles 12px `text-ai`) + description `text-[12px] leading-4 text-ink-muted`.
- "AI suggest" trigger button: `h-8 rounded-lg border border-ai/25 bg-card px-2 text-[12px] font-medium text-ai-deep hover:border-ai/40 hover:bg-ai-soft` + unified ring; while loading, spinner `h-3 w-3 border-[1.5px] border-ai/25 border-t-ai` + "Analyzing...".
- Error bar: danger combination (00 §2.3), `text-[12px] leading-4`.
- **Candidate card**: `rounded-xl border border-ai/20 bg-card p-2.5`; endpoints on two lines `font-mono text-[12px] leading-4` (from `text-ink-faint` + field `text-ink-soft font-medium`; to field `text-blue-700`); confidence badge `rounded-full border border-ai/20 bg-ai-soft px-1.5 py-px font-mono text-[11px] text-ai-deep`; reason `text-[12px] leading-4 text-ink-muted`; **confirm/reject button group** (footer row `mt-2 flex items-center justify-between border-t border-line-soft pt-2`, busy-state mutual exclusion disable behavior preserved):
  - Confirm: primary sm `h-7 px-2 text-[12px]` (check icon 12px; busy "Confirming..." + small white spinner);
  - Reject: secondary sm `h-7 px-2 text-[12px]` + `hover:border-danger/30 hover:text-danger-deep` (trash 12px; busy "Rejecting...").
- Empty result note (suggestNote): `rounded-lg border border-dashed border-line bg-page px-2.5 py-2 text-center text-[12px] text-ink-muted`.

**⑦ Upstream lineage card (IncomingEdgeCard)**: `rounded-xl border border-line-soft bg-card p-3`; endpoint `font-mono text-[12px] leading-4 text-ink-soft` (`from_dataset.` prefix `text-ink-faint`, field name `font-medium text-ink`); meta row `font-mono text-[11px] text-ink-faint` (confidence `tabular-nums text-ink-soft`) + `SourceBadge`; transformation area `mt-2 border-t border-line-soft pt-2 font-mono text-[11px] leading-4 text-ink-muted` ("Transformation · " prefix `text-ink-faint`). Empty branch (root field): `rounded-xl border border-dashed border-line px-3 py-3 text-center`, main line `font-mono text-[12px] text-ink-muted`, description `text-[11px] leading-4 text-ink-muted`. Section title row: eyebrow "Upstream lineage" + count `font-mono text-[11px] tabular-nums text-ink-faint`.

**⑧ AnnotationSection (annotation area, reused by both panels)**:

- Title row: `flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint` "Annotations (N)" (message-square 12px) + "Append-only" chip `rounded-full border border-line bg-page px-1.5 py-px font-mono text-[11px] text-ink-faint`.
- Entry card: `rounded-lg border border-line-soft bg-card px-3 py-2.5`; body `whitespace-pre-wrap break-words text-[13px] leading-relaxed text-ink-soft`; meta row `mt-1.5 flex items-center gap-1.5 font-mono text-[11px] text-ink-faint` (author · separator dot `h-2 w-px bg-line` · time).
- Loading row: `animate-soft-pulse rounded-lg border border-line-soft bg-subtle px-3 py-3 text-[12px] text-ink-muted` "Reading annotations...".
- Load failure: danger combination `rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[12px] leading-4 text-danger-deep`.
- Empty state: `rounded-lg border border-dashed border-line px-3 py-3 text-center text-[12px] text-ink-muted` "No annotations".
- Input form (canEdit): textarea `.field-input` (`min-h-[62px]` current value preserved, `text-[13px]`); counter row `flex items-center justify-between` - character count `font-mono text-[11px] text-ink-faint` "n/4000 · Annotations are not deleted on version rollback" + submit button primary sm `h-7 px-2.5 text-[12px]` (plus 12px; busy "Submitting..." + spinner; empty text disabled neutralized); submit error `role="alert"` danger combination `text-[11px]`.
- viewer read-only hint: `mt-2 flex items-center gap-1.5 text-[11px] text-ink-faint` (lock 10px + existing copy preserved).

**⑨ Change history entry row**: `flex w-full items-center justify-between rounded-xl border border-line bg-card px-3 py-2.5 text-[13px] font-medium text-ink-muted transition-colors duration-150 hover:border-blue-400 hover:text-blue-700` + unified ring (history 12px / chevron-right 12px `text-ink-faint`).

**⑩ Raw locator `<details>`**: `rounded-xl border border-line-soft bg-card`; summary `flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13px] font-medium text-ink-muted hover:text-ink` (chevron `group-open:rotate-180`, `transition-transform duration-150` preserved); `pre`: `max-h-52 overflow-auto border-t border-line-soft px-3 py-2.5 font-mono text-[11px] leading-4 text-ink-muted bg-subtle/50` (code block background subtle, 00 §2.2).

**Empty state (no field selected)**: panel header + guidance body (00 §7.9 extension): icon block `relative mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-line bg-page text-blue-600` (file-search 24px + corner count circle `border-line bg-card text-[11px] text-ink-faint`); main copy `text-xl font-medium text-ink` "Verify where fields come from" (replaces 25px display); description `text-[13px] leading-5 text-ink-muted`; three hint cards `flex items-center gap-2.5 rounded-lg border border-line-soft bg-card px-3 py-2.5` (icon block `h-7 w-7 rounded-lg border-line-soft bg-page text-ink-faint` + title `text-[13px] font-medium text-ink-soft` + description `font-mono text-[11px] text-ink-faint`); bottom dashed hint `text-[11px] leading-4 text-ink-muted`.

### 3.3 DetailPanel · Field edit form (FieldEditor)

- Top hint card (info combination): `rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5`; eyebrow row `flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-blue-700` (edit 11px) "Edit field attributes"; description `mt-1 text-[12px] leading-4 text-blue-800` "When the locator is saved, the backend re-runs structural validation and real-file verification; on failure it returns 409 and keeps the original value.".
- Form (`mt-4 space-y-3`): labels always per 00 §7.2 (`mb-1.5 block text-[12px] font-medium text-ink-soft`); description textarea `.field-input resize-y py-2 text-[13px]` (rows 2 preserved); field type input `.field-input h-8 font-mono text-[13px]` (compact 32px inside the panel).
- Source locator sub-card: `rounded-xl border border-line bg-card`; header row `flex items-center justify-between border-b border-line-soft px-3 py-2` (code icon 11px `text-blue-600` + "Source locator" `text-[12px] font-medium text-ink-soft` + `FileTypeBadge`); body branches by src_type (csv column number/header either-one, xlsx sheet/column/start-end row/header path/header row count, json JSONPath) - all inputs `.field-input h-8 text-[13px]` (numeric and code fields add `font-mono`), inline note `text-[11px] leading-4 text-ink-muted`; either-or mutually exclusive interaction and validation copy fully preserved.
- Error bar: danger combination `text-[12px] leading-4`, `role="alert"`.
- Button row: Save primary `h-8 flex-1 text-[13px]` (busy "Save and verify..." + spinner; replace pine-800 and `disabled:opacity-65`, use §7.1 disabled neutralization) + Cancel secondary `h-8 px-3`.

### 3.4 EdgeDetailPanel · Edge details

Skeleton, header icon group, AnnotationSection, and change history entry are identical to DetailPanel (§3.1/§3.2⑧⑨); the following are the differing areas:

- Badge row: level tag ("Field-level lineage/Table-level lineage") + `SourceBadge` + confidence tag `rounded border border-line bg-page px-1.5 py-0.5 font-mono text-[11px] text-ink-muted`.
- Title: `mt-2.5 text-lg font-semibold text-ink` "Lineage edge #id" (replaces `font-display text-[22px]`).
- **Upstream/downstream endpoint card**: `rounded-xl border border-line bg-card`; header row "Upstream/downstream endpoints" eyebrow (same spec as the source file card); two rows `divide-y divide-line-soft` - row `flex items-start gap-2 px-3 py-2`: direction chip `rounded bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-muted` ("Upstream/Downstream") + endpoint `break-all font-mono text-[13px] leading-5 text-ink-soft` (downstream row endpoint `text-blue-800`, existing emphasis preserved).
- **AI candidate confirmation area (when source='ai')**: `rounded-xl border border-ai/25 bg-ai-soft/40 p-3`; title row `flex items-center gap-1.5 text-[13px] font-semibold text-ai-deep` (sparkles 12px) "AI candidate lineage"; description `text-[12px] leading-4 text-ink-muted` (contains existing copy "Deleting is equivalent to rejecting"); **Confirm button**: primary `h-8 w-full text-[13px]` "Confirm as manual edge" (check 12px; busy spinner + "Confirming..."); viewer branch: `flex items-center gap-1.5 text-[11px] text-ink-faint` (lock 12px); confirmation error `role="alert"` danger combination `text-[12px]`.
- Display card group (non-edit state): `grid gap-2` - transformation note / remark cards `rounded-xl border border-line-soft bg-card px-3 py-2.5`: eyebrow `font-mono text-[11px] uppercase text-ink-faint` + value `break-words font-mono text-[13px] leading-5 text-ink-soft` (remark uses body font, "Not filled" fallback preserved).
- Action row (canEdit): `mt-4 flex items-stretch gap-2` - "Edit transformation and remark" secondary `h-9 flex-1` (edit 13px) + **Delete** danger ghost: `h-9 rounded-lg border border-danger/25 bg-danger-soft px-3 text-[13px] font-medium text-danger-deep transition-colors duration-150 hover:border-danger/45` (trash 13px; replace the whole rosewood set and hardcoded hover background `#f4dfe1`) + unified ring. Delete goes through ConfirmDialog (06 doc).
- Bottom permission note: same spec as DetailPanel⑤ (lock/edit icon + three existing copy variants preserved).
- **Edge edit form (EdgeEditor)**: structure isomorphic to FieldEditor - info hint card "Edit transformation and remark"; transformation textarea `.field-input resize-y py-2 font-mono text-[13px]`; confidence input `.field-input h-8 font-mono text-[13px]` (number, 0-1 step 0.05); remark textarea; error bar danger; Save primary `h-8 flex-1` + Cancel secondary `h-8`. Validation copy and logic unchanged.

### 3.5 PreviewModal · Source preview (modal xl tier)

- Overlay: `fixed inset-0 z-50 bg-slate-900/40 animate-fade-in` (replaces `z-[80] bg-ink/45 backdrop-blur-[3px]`; click-overlay-to-close preserved).
- Panel: `relative z-[51] mx-auto flex max-h-[85vh] w-full max-w-[880px] flex-col overflow-hidden rounded-xl border border-line bg-card shadow-modal animate-modal-in` (980→880 mapped to 00 §7.6 xl tier; `rounded-2xl`→`rounded-xl`; `shadow-float`→`shadow-modal`).
- **Header (h-12)**: `flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4` - left: icon block `flex h-8 w-8 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700` (file-search 16px) + title group (eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Source file origin / read-only" + type chip; title `text-[14px] font-semibold text-ink` "Source preview" + entity `font-mono text-[12px] font-normal text-ink-muted` "ds.field"); right: "Copy locator" secondary `h-8` (copy 12px; three-state copy same as §3.2④) + close icon button `h-8 w-8 rounded-lg` (close 16px, ghost spec). Initial focus lands on the close button (existing behavior preserved).
- **Body**: `min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4` (replaces `bg-[#fbf9f3]`).
- **① Info card**: `mb-3.5 grid gap-3 rounded-xl border border-line bg-card p-3.5 sm:grid-cols-2` - source file cell (eyebrow "Source file" 11px mono faint; filename `font-mono text-[13px] font-medium text-ink` + file icon 13px `text-blue-600`; subline "Managed file · Source file #id" and sha256 line `font-mono text-[11px] text-ink-faint`); locator cell (`border-t border-line-soft pt-2 sm:border-l sm:border-t-0 sm:pl-3.5`; value `text-[13px] leading-relaxed text-ink-soft`); verification row (spanning columns): eyebrow "Real-file verification" - **Passed** badge `inline-flex items-center gap-1 rounded-full border border-transparent bg-success-soft px-1.5 py-px font-mono text-[11px] text-success-deep` (check 12px "Passed", 00 §7.4 status badge) + validation info `text-[12px] text-ink-faint` "Verified on import vN · date · operator"; other states are plain text `text-[12px] text-ink-muted`.
- **② Loading skeleton** (§7.10): two blocks `animate-soft-pulse rounded-xl border border-line bg-subtle` (h-[86px] / h-[260px], current sizes preserved), `aria-hidden`.
- **③ Error card**: `rounded-xl border border-line bg-card p-6` centered column - icon block `h-12 w-12 rounded-2xl`: 409 (locator invalid) `bg-warning-soft text-warning-deep` (warning 22px), others `bg-danger-soft text-danger` (file-search 22px); title `text-xl font-medium text-ink` (replaces 24px display); message `text-[13px] leading-5 text-ink-soft`; hint `text-[12px] leading-5 text-ink-muted`; for non-409/401 show "Try again" secondary `h-8` (refresh 12px). 409/403/404/401 titles and hint copy preserved.
- **④ CSV table** (`PreviewShell`: outer card `overflow-hidden rounded-xl border border-line bg-card`; header row `flex items-center justify-between border-b border-line-soft px-3.5 py-2.5` - title `text-[13px] font-semibold text-ink` + subline `font-mono text-[11px] text-ink-faint` + right-side "Highlighted column" badge `rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 font-mono text-[11px] text-blue-800` (dot `h-1 w-1 rounded-full bg-blue-600`)):

| Element | Spec |
|---|---|
| Table body container | `max-h-[46vh] overflow-auto`; table `w-full min-w-[680px] border-collapse text-left text-[13px]` (current value preserved) |
| Header row | `sticky top-0 z-10 bg-subtle`; column header `min-w-[118px] border-b border-r border-line px-2.5 py-2`, column letter `font-mono text-[11px] text-ink-faint` + header name `text-[12px] font-medium text-ink-soft` |
| Target column header | `bg-blue-100 text-blue-800` + "Field" badge `rounded bg-blue-600 px-1 py-px font-mono text-[11px] text-white` (ml-auto) |
| Row number column | `w-12 bg-page text-center font-mono text-[11px] text-ink-faint` (same spec as the # header; replaces `#faf7ef`) |
| Data row | `border-b border-line-soft hover:bg-subtle/60` (replaces `#fbf8f0`); cell `max-w-[260px] truncate border-r border-line-soft px-2.5 py-1.5 font-mono text-[12px] text-ink-soft` |
| Target cell | `bg-blue-50/80 font-medium text-ink` (data content in neutral ink + blue background, 00 §1.2 principle 3) |
| Footnote bar | `border-t border-line-soft bg-page px-3.5 py-2 text-[11px] text-ink-muted` (highlighted column note + "Max 50 rows shown" mono) |
| sr-only caption | preserved |

- **⑤ XLSX table** (layered on top of the CSV spec):

| Element | Spec |
|---|---|
| Column header row (A B C...) | `sticky top-0 z-10 bg-subtle`; target column header `bg-blue-100 text-blue-800`, others `text-ink-faint`; `font-mono text-[11px] font-medium`; corner row-number cell `sticky left-0 z-20 bg-subtle` |
| Header data row (multi-level headers) | whole-row background `bg-warning-soft` (amber separates it from the blue highlight); header row-number cell `bg-warning-soft text-warning-deep` (`sticky left-0`) |
| Data row | background `bg-card`; row-number cell `sticky left-0 bg-page text-ink-faint`; `data row start row` top border `border-t-2 border-blue-200` (row range start marker, functional not decorative) |
| Cell | same as CSV; header-row cell `text-[12px] font-medium text-ink-soft`; target column (including merged span hits) finalized `bg-blue-100 text-blue-800` (consistent with the target column header); merged cell values centered, empty merge shows `text-ink-faint` "Merged cell" |
| Merge range chips | `rounded border border-line bg-card px-1.5 py-px font-mono text-[11px] text-ink-muted` (§7.5 chip; +N overflow count `text-[11px] text-ink-faint`) |
| Footnote bar | same as CSV (row range/merge ranges/"Max 50 data rows shown") |

- **⑥ JSON panel**:
  - JSONPath bar: `flex items-center gap-2 rounded-lg border border-line bg-page px-3 py-2` (code 13px `text-ink-faint` + path `font-mono text-[13px] text-ink-soft` + "jsonpath" corner label `rounded bg-card px-1.5 py-0.5 font-mono text-[11px] text-ink-faint`).
  - Hit badge (header right): info combination `rounded-full border border-transparent bg-info-soft px-2 py-0.5 font-mono text-[11px] text-info-deep` "N hits" (**info, not ai** - hit count is unrelated to AI, see pending item #3).
  - Sample list: `mt-3 divide-y divide-line-soft rounded-xl border border-line bg-page`; row `grid grid-cols-[34px_minmax(0,1fr)] gap-2 px-3 py-2.5` - sequence number `font-mono text-[11px] text-ink-faint`; structured value `pre overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-5 text-ink-soft` (replaces pine-900, data content in neutral ink); scalar value `code break-words font-mono text-[13px] leading-5 text-ink-soft`.
  - Footnote: `mt-2.5 flex items-center justify-between text-[11px] text-ink-muted` ("Hit samples keep their original types from the source file" + display count mono).
- **Footer (h-12)**: `flex h-12 shrink-0 items-center gap-x-3 border-t border-line-soft bg-card px-4 text-[11px] text-ink-muted` - read-only note (lock 12px "Read-only · storage path not exposed externally") · type note (mono); right `ml-auto`: "Download source file (permission-controlled)" secondary sm `h-7 px-2.5 text-[12px]` (download 12px; busy "Downloading..." + disabled neutralized; title permission note preserved) + "Close" ghost sm. Download error `w-full text-danger-deep role="alert"` preserved.

### 3.6 EdgeCreateModal · Add lineage (modal md tier)

- Overlay/panel: same as §3.5 spec but `max-w-[560px]` (md tier, replaces the off-tier 520px value); **while submitting, neither overlay click nor Esc closes** (existing behavior preserved).
- **Header (h-12)**: icon block `h-8 w-8 rounded-lg border border-blue-200 bg-blue-50 text-blue-700` (link 16px); eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Manual edge creation · field-level/table-level"; title `text-[14px] font-semibold text-ink` "Add lineage"; close icon button `h-8 w-8` (disabled `opacity-50` while submitting).
- **Body** (`px-4 py-4 space-y-3.5`):
  - Draft endpoint row: `break-all font-mono text-[13px] leading-5 text-ink-soft` (fromLabel → toLabel, arrow `text-ink-faint`).
  - Form: label §7.2 (12px); transformation note input `.field-input h-9 text-[13px]`; confidence `.field-input h-9 font-mono` (number 0-1 step 0.05) and remark `.field-input h-9` in two columns `grid sm:grid-cols-[1fr_1.4fr] gap-3` (current ratio preserved).
  - Hint bar (info combination): `flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[12px] leading-4 text-blue-800` (info icon 12px; existing copy "Manual edges are recorded with source manual...409" preserved).
  - Error bar: danger combination `text-[12px] leading-4`, `role="alert"`.
- **Footer (h-12)**: `flex h-12 items-center justify-end gap-2 border-t border-line-soft bg-card px-4` - Cancel secondary `h-8 px-3 text-[13px]` (disabled while submitting) + Create lineage edge primary `h-8 px-3.5 text-[13px]` (plus 12px; busy "Creating..." + small white spinner).

## 4. Component state spec (summary of interactive elements on this page)

| Component | default | hover | active/focus | disabled/loading | selected |
|---|---|---|---|---|---|
| Panel header icon button | ghost (`text-ink-faint`) | `border-line bg-card text-ink-soft` (edit button `text-blue-700`) | unified ring (00 §7.1) | - | - |
| Copy locator (inside envelope card) | `text-blue-700` | `bg-blue-100/70` | unified ring | - | success "Copied" / failure `text-danger-deep` (timed restore) |
| Source preview | primary `h-9 flex-1` | `bg-blue-700` | `active:bg-blue-800` + ring | - | - |
| Edit (field/edge entry) | secondary `h-9` | `border-blue-400 text-blue-700` | ring | - | - |
| AI suggest trigger | `border-ai/25 bg-card text-ai-deep` | `border-ai/40 bg-ai-soft` | ring | spinner + "Analyzing..." `disabled:opacity-60` | - |
| Candidate confirm | primary sm `h-7` | `bg-blue-700` | ring | any busy disables the whole group | - |
| Candidate reject | secondary sm `h-7` | `border-danger/30 text-danger-deep` | ring | same as above | - |
| Confirm as manual edge (edge details) | primary `h-8 w-full` | `bg-blue-700` | ring | spinner + "Confirming..." | - |
| Delete edge | danger ghost `h-9` | `border-danger/45` | ring | - | - |
| Save (form) | primary `h-8 flex-1` | `bg-blue-700` | ring | spinner "Save and verify..." neutralized disabled | - |
| Cancel (form) | secondary `h-8` | `border-blue-400 text-blue-700` | ring | disabled `opacity-50` | - |
| Annotation submit | primary sm `h-7` | `bg-blue-700` | ring | empty text/submitting disabled neutralized | - |
| Form input (in panel) | `.field-input h-8` | `border-line-strong` | blue focus (built in) | `opacity-50 cursor-not-allowed` | - |
| Change history entry row | `border-line bg-card text-ink-muted` | `border-blue-400 text-blue-700` | ring | - | - |
| `<details>` summary | `text-ink-muted` | `text-ink` | ring | - | chevron rotated in open state |
| Modal close button | ghost `h-8 w-8` | `border-line bg-page text-ink-soft` | ring; initial focus when opened | submitting (EdgeCreate) disabled | - |
| Download source file | secondary sm | secondary hover | ring | spinner "Downloading..." | - |

## 5. Data states

| Area | Empty state | Loading state | Error state |
|---|---|---|---|
| DetailPanel | §3.2 empty-state guidance (no field selected) | - (field data syncs with the subgraph; no independent loading) | - |
| Annotation area | dashed "No annotations" | `animate-soft-pulse bg-subtle` "Reading annotations..." | danger bar (loadError) + submit error `role="alert"` |
| AI suggestion area | suggestNote dashed note (no candidates/processed) | trigger spinner "Analyzing..."; candidate card busy "Confirming.../Rejecting..." | danger bar (suggestError / confirmation failure) |
| EdgeDetailPanel | - (edge prop always present) | confirm button spinner | confirmation error danger bar |
| PreviewModal | unsupported type: dashed "Unsupported preview data type" `text-[13px] text-ink-muted` | two skeleton blocks `animate-soft-pulse bg-subtle` | §3.5③: 409 warning / others danger; 409 and 401 have no retry button |
| EdgeCreateModal | - | submit button "Creating..." + spinner; during this, Esc/overlay/cancel/close all locked (existing behavior) | danger error bar (includes backend 409 duplicate-edge copy) |

## 6. Interaction and motion (00 §5)

| Interaction | Motion |
|---|---|
| Panel content switch (field↔edge, entering edit state) | `animate-fade-in` 200ms (existing preserved) |
| Modal enter | `animate-modal-in` 250ms `out-quint` (00 §5.2) |
| Overlay fade-in | `animate-fade-in` 200ms |
| Skeleton screen / annotation loading row | `animate-soft-pulse` 1.8s (two of the only continuous animations, static under reduced-motion) |
| Button/row/input hover | `transition-colors duration-150` |
| summary chevron | `transition-transform duration-150` |
| Copy success/failure copy | instant replacement + timed restore (1600/1800ms, current values; no color transition animation) |
| Esc / Tab trap / focus restore | behavior logic preserved (PreviewModal focus trap, EdgeCreateModal Esc lock), no new motion |
| List item enter | no enter animation for AnnotationSection items (appears immediately on append, avoiding flicker in verification scenarios) |

## 7. Change list for existing components

Same-name value swaps are handled by the 00 §9 global replacement (pine/ochre/rosewood→blue/warning/danger, etc.); the table below lists only page-level changes beyond that mapping. `HistoryDrawer` / `ConfirmDialog` are owned by the 06 doc; this page only keeps their entry points and mounting.

| # | Component - Current - Target - tokens/classes involved |
|---|---|
| 1 | `DetailPanel.tsx` / `EdgeDetailPanel.tsx` - container `xl:w-[340px] bg-[#f8f5ed]/70~80 relative z-10`, header `py-3.5` free height - change to `xl:w-[320px] bg-card` (00 §4.5, [CONFLICT] see intro), header to h-12 fixed structure (§3.1), remove `z-10` - `w-[320px]`, `bg-card`, `h-12` |
| 2 | Both panels - eyebrow/breadcrumb/direction chip font sizes mixed 7.5-10px - eyebrow `text-[11px]`, breadcrumb `text-[12px]`, direction chip `text-[11px]`, header block background `bg-page` - size tiering (00 §3.2) |
| 3 | `DetailPanel.tsx` - empty-state title `font-display text-[25px]`, icon block pine, hint card `bg-surface/55` - title `text-xl font-medium font-sans`, icon block `border-line bg-page text-blue-600`, hint card `bg-card` + size tiering - `text-xl`, blue icon block |
| 4 | `DetailPanel.tsx` - entity title `font-mono text-[22px] tracking-[-0.035em]` - change to `font-mono text-lg font-semibold text-ink` (18px tier) - `text-lg` |
| 5 | `DetailPanel.tsx` - locator envelope card `border-pine-100 bg-pine-50/55 text-pine-900`, footnote `text-pine-700/70`, copy button hover `bg-pine-100/70` - change to `border-blue-100 bg-blue-50`, body `text-blue-800`, footnote `text-blue-700`, copy button hover `bg-blue-100/70` (§3.2④) - `blue-50/100/700/800` |
| 6 | `DetailPanel.tsx` - "Managed file" badge `border-pine-200 bg-pine-50 text-pine-700` - neutral info badge `border-line bg-subtle text-ink-muted` - `bg-subtle`, `text-ink-muted` |
| 7 | `DetailPanel.tsx` - source preview `h-10 rounded-xl bg-pine-800` + shadow, edit button `h-10` pine hover - primary/secondary `h-9 rounded-lg` (§3.2⑤), remove shadow - `bg-blue-600`, `h-9`, `rounded-lg` |
| 8 | `DetailPanel.tsx` - AI area `border-ai/20 bg-ai-soft/40`, trigger button/candidate card pine-family confirm button, reject button hover rosewood - outer card `border-ai/25`; confirm primary sm, reject secondary sm + danger hover (§3.2⑥); font sizes 9-10.5px → 11/12/13 tiers - `h-7`, `text-[12px]/[13px]`, danger hover |
| 9 | `DetailPanel.tsx` - IncomingEdgeCard field name `text-pine-800`, card `bg-surface/75` - field name `text-ink`, card `bg-card`; size tiering (§3.2⑦) - `bg-card`, `text-[12px]/[11px]` |
| 10 | `DetailPanel.tsx` - FieldEditor hint card pine, label `text-[10.5px]`, inputs h-8/h-9 mixed `text-[10.5px]`, save button `bg-pine-800 disabled:opacity-65` - hint card info combination (blue-50/blue-700/blue-800), label §7.2 12px, inputs unified `.field-input h-8 text-[13px]`, save primary `h-8` + disabled neutralization - info group, `text-[12px]/[13px]`, `h-8` |
| 11 | `DetailPanel.tsx` - change history entry `bg-surface/70 hover:border-pine-300 text-[9.5px]`, details pre 9px - entry `bg-card hover:border-blue-400 text-[13px]`, pre `text-[11px] bg-subtle/50` (§3.2⑨⑩) - `text-[13px]/[11px]`, `bg-subtle/50` |
| 12 | `EdgeDetailPanel.tsx` - title `font-display text-[22px]`, endpoint card `bg-surface/75`, downstream `text-pine-800`, AI area confirm button `bg-pine-800`, delete button rosewood + hardcoded `hover:bg-[#f4dfe1]` - title `text-lg font-semibold`; endpoint card `bg-card`, downstream `text-blue-800`; confirm primary `h-8`; delete danger ghost (§3.4); size tiering - `text-lg`, `text-blue-800`, danger ghost |
| 13 | `EdgeDetailPanel.tsx` - EdgeEditor same pine family as FieldEditor - same as #10 spec (§3.4) - same as #10 |
| 14 | `AnnotationSection.tsx` - title 8.5px, chip `bg-canvas/55` 8px, entry `bg-surface/75` 10px, meta 8px, loading row `bg-surface/60`, empty state `text-ink-faint`, error rosewood, submit button `bg-pine-800` 9.5px, counter row 8px - §3.2⑧ full set: title/chip/meta/counter `text-[11px]`, entry body `text-[13px]`, loading `bg-subtle`, empty state `text-ink-muted`, error danger, submit primary sm `h-7 text-[12px]` - `text-[11px]/[12px]/[13px]`, `bg-subtle`, danger group |
| 15 | `PreviewModal.tsx` - overlay `z-[80] bg-ink/45 backdrop-blur-[3px]`, panel `max-w-[980px] rounded-2xl shadow-float`, header py-3.5 two-row large title (22px display) - §3.5: overlay `z-50 bg-slate-900/40`, panel `max-w-[880px] rounded-xl shadow-modal`, header h-12 title `text-[14px]` - 00 §7.6 xl tier, `shadow-modal`, `h-12` |
| 16 | `PreviewModal.tsx` - body `bg-[#fbf9f3]`, CSV header `bg-[#f3f0e7]`, row number `bg-[#faf7ef]`, row hover `hover:bg-[#fbf8f0]`, footnote `bg-[#faf7ef]`, font sizes 7-10.5px - body `bg-page`, header `bg-subtle`, row number `bg-page`, row hover `hover:bg-subtle/60`, footnote `bg-page`; font size 11/12/13 tiers (§3.5④) - `bg-page`, `bg-subtle`, size tiering |
| 17 | `PreviewModal.tsx` - target column pine family (`bg-pine-100/90 text-pine-900`, badge `bg-pine-600`) - column header `bg-blue-100 text-blue-800`, data cell `bg-blue-50/80 text-ink`, badge `bg-blue-600 text-white text-[11px]`, "Highlighted column" badge blue family (§3.5④) - `blue-50/100/600` |
| 18 | `PreviewModal.tsx` - XLSX column header `bg-[#eae5d9]`, header row `bg-[#f5f1e7]`/row number `bg-[#f1ecdf] text-ochre-deep`, data row start `border-t-2 border-pine-200`, merge chip hardcoded - column header `bg-subtle`, header row `bg-warning-soft` + row number `text-warning-deep`, start line `border-t-2 border-blue-200`, merge chip §7.5 (§3.5⑤) - `bg-subtle`, warning group, `border-blue-200` |
| 19 | `PreviewModal.tsx` - JSON hit badge `border-ai/20 bg-ai-soft text-ai-deep`, sample background `bg-[#faf8f1]`, pre `text-pine-900`, corner label 8px - hit badge info group (`bg-info-soft text-info-deep`, decoupled from AI semantics), sample background `bg-page`, pre/code `text-ink-soft`, corner label `text-[11px]` - info group, `bg-page`, `text-ink-soft` |
| 20 | `PreviewModal.tsx` - verification "Passed" badge pine family, sha256/subline 8.5px - passed badge success group (`bg-success-soft text-success-deep` + check); subline `text-[11px]` (§3.5①) - success group, `text-[11px]` |
| 21 | `PreviewModal.tsx` - ErrorPreview icon `bg-ochre-soft text-ochre-deep / bg-rosewood-soft text-rosewood`, title `font-display text-[24px]`, retry button pine hover - 409 uses warning group, others danger group; title `text-xl font-medium`; retry secondary `h-8` (§3.5③) - warning/danger group, `text-xl` |
| 22 | `PreviewModal.tsx` - footer self-laid-out py-2.5 9px, download button pine hover - footer h-12 structure (§7.6), text `text-[11px] text-ink-muted`, download secondary sm - `h-12`, `text-[11px]` |
| 23 | `EdgeCreateModal.tsx` - overlay `z-[80] bg-ink/45 blur`, panel `max-w-[520px] rounded-2xl shadow-float`, header/footer self-laid-out, hint bar `bg-canvas/45 text-ink-faint 9px`, label 10.5px, create button `bg-pine-800` - §3.6: overlay z-50, `max-w-[560px] rounded-xl shadow-modal`, header/footer h-12, hint bar info group 12px, label §7.2, create primary `h-8` - 00 §7.6 md tier, info group, `h-12` |

## 8. Accessibility highlights (specific to this page)

1. **Modal focus trap**: PreviewModal's Tab trap + Esc + focus restore after close, EdgeCreateModal's Esc (locked while submitting) and initial focus - existing behavior preserved item by item; the visual redesign must not break them (00 §10.5).
2. **Copy feedback is not color-only**: "Copied / Copy failed" have text changes (distinguishable for color vision deficiency); copy success is also self-described by the button copy, no aria-live needed (transient state, 1.6s visual is sufficient).
3. **Table dual encoding**: highlighted column = background + "Field" text badge + `sr-only caption`; XLSX header row = warning background + row-number text note (title "Header row" preserved); merged cells have the text "Merged cell".
4. **Form labels**: all associated via `htmlFor` (existing preserved); label readability improves after unifying 8.5-10.5px to 12px; annotation input sr-only label preserved.
5. **Error bar semantics**: `role="alert"` (form validation / AI failure / annotation submit / download failure) and `role="status"` distinction preserved.
6. **Preview loading**: `aria-live="polite"` container wraps the preview body (existing preserved), skeleton `aria-hidden`.
7. **Disabled-state copy**: busy buttons have both spinner + text ("Confirming..."), not relying on opacity alone.
8. **Key spacing**: panel scroll body `pb-7` bottom padding prevents the last item from being flush against the edge and having its focus obscured by the sticky header.

## Pending tokens (suggest writing back to 00)

| # | Gap | Suggested value | Note |
|---|---|---|---|
| 1 | **[CONFLICT] detail right column width tier** | Keep 320px per 00 §4.5; or unify to the drawer 360px tier | 00 §4.5 (320) conflicts with the task "align with drawer width tiers 360/480"; this page follows 00; suggest the 00 maintainers clarify whether "detail right column" and "drawer" should merge width tiers; no value change before the decision |
| 2 | Data table header-row semantic color (XLSX multi-level headers) | `bg-warning-soft` row background + `text-warning-deep` row number | 00 §2.3 warning is used for "low confidence/expired/manual edge"; borrowing it in data preview to mark "structural rows" is a new scenario; suggest adding a row to the §2.3 scenario list |
| 3 | JSON hit count badge | info combination (`bg-info-soft text-info-deep`) | "Hit count" is not AI semantics; the current implementation misuses the ai color group; suggest adding a "count/hit" scenario row to the 00 §7.4 status badge table |
| 4 | ai border opacity sub-tiers | Current state mixes `ai/20`, `ai/25`, `ai/40` | 00 §8.1 opacity extension tiers have no 20/40; suggest unifying AI area borders to `/25` (hover `/40` needs to be tiered) or listing all tiers |
| 5 | Modal inner table min-width / scroll height | CSV `min-w-[680px]`, XLSX `min-w-[720px]`, preview body `max-h-[46vh]` (current values retained) | One-off layout values; suggest adding a "data table in modal" row to 00 §4.5 to prevent 04/05 docs from inventing their own |
