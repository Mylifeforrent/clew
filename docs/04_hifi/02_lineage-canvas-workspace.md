# 02 · Lineage Canvas Workspace

> Positioning: Clew's main workbench. Entered immediately after login; it carries the core loop of "select dataset → view lineage graph → verify fields and edges": top bar global search and hop count, left dataset sidebar, central React Flow canvas (nodes/edges/groups/overlays), right detail panel (content spec in doc 03). This page is the main battleground for the Data-Dense Dashboard character (00 §1.1): white cards + fine-border layering + restrained brand orange, high information density with low noise. (2026-10 Clew brand revision: blue→brand, trace red→orange, manual amber→teal, see the note at the top of doc 00.)
>
> Basis and sources:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (single source of tokens, cited as "00 §x.x"; canvas-specific specs in 00 §2.5, §2.4)
> - `docs/02_prototype/clew-lofi-prototype.html` lineage canvas screen (information architecture baseline: top bar/sidebar/canvas/detail panel four regions, legend, AI suggested edges)
> - `docs/03_dev/02_frontend-development.md` §6 component list, §7 canvas implementation (getEdgeVisual four forms, handle system, collapse/grouping, hop-count contract)
> - Component source: `Workspace.tsx`, `TopBar.tsx`, `DatasetSidebar.tsx`, `LineageCanvas.tsx`, `DatasetNode.tsx`, `GroupNode.tsx`, `LineageEdge.tsx`, `Brand.tsx`, `SourceBadge.tsx`, `lib/layout.ts`, `src/index.css`
>
> Scope constraints: visual and layout changes only, no functional logic changes (layout algorithms, handle conventions, edge construction rules, and shortcuts are all retained); no new dependencies. The **content** of the right panel `DetailPanel` / `EdgeDetailPanel` and the two modals belongs to doc 03; this page covers the Workspace three-column skeleton and the right panel container position. The `SourceBadge` spec is finalized on this page (referenced by 03).

---

## 1. Page Positioning and Entry

| Item | Description |
|---|---|
| Entry timing | Rendered by `App` after successful login (`key={token}`); this page is the product's only main view, with no routing |
| Corresponding components | `Workspace.tsx` (container) assembles: `TopBar`, `DatasetSidebar`, `LineageCanvas` (containing `DatasetNode` / `GroupNode` / `LineageEdge`), `DetailPanel` / `EdgeDetailPanel` (doc 03) |
| Page state | Held by `Workspace`: seed dataset, hop count (1–5, default 3), AI overlay subgraph, canvas filters (confidence / hide AI edges / confirmed only), collapse and grouping, field/edge selection, each drawer and modal toggle |
| Data flow | `getSubgraph` (seed + hops + direction:'both') → unified entry `applyGraph`; AI graph output is overridden via `onGraph` (dev doc §7.6) |

## 2. Layout Structure

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ ① TopBar   h-14(56px)  sticky z-30  bg-card  border-b border-line              │
│[Brand 28px]│[Title]  [Search max-w-340 h-8]  ←ml-auto→ [AI][Version][Hops│User]│
├──────────────┬───────────────────────────────────────────────┬─────────────────┤
│ ② Dataset-   │ ③ LineageCanvas  flex-1  min-h-[560px]        │ ④ Detail panel  │
│ Sidebar      │   bg-page + bg-dot-grid bg-grid-24            │   w-[320px]     │
│ w-[240px]    │                                               │   bg-card       │
│ bg-card      │  ┌─Top-left toolbar (Panel)─┐  z-20 overlays: │   border-l      │
│ border-r     │  │ Seed·stats·bulk collapse │  Controls (BL)  │   border-line   │
│              │  │ [Collapse selected (N)]  │  MiniMap (BR)   │                 │
│ ·Header (n)  │  └──────────────────────────┘  bottom hint (C)│  DetailPanel    │
│ ·Filters     │                                               │  or             │
│ ·List(scroll)│    Nodes w-[288px] × dagre LR layout          │  EdgeDetailPanel│
│ ·Legend (btm)│    Edges: smoothstep + arrow + tooltip        │  (content in 03)│
├──────────────┴───────────────────────────────────────────────┴─────────────────┤
│ ⑤ Overlays (this page positions layers only; content in docs 03/05/06)         │
│    Canvas overlays z-20 < top bar z-30 < drawer mask z-40/panel z-[41] < modal │
│    mask z-50/panel z-[51] < Toast z-[60] (00 §6 layer table)                   │
└────────────────────────────────────────────────────────────────────────────────┘
```

Dimensions and grid (00 §4.5 control heights and key dimensions):

| Item | Value |
|---|---|
| Workspace root | `flex min-h-dvh flex-col bg-page xl:h-dvh xl:overflow-hidden` (replaces `bg-canvas`) |
| Three-column body | Existing flex implementation **retained** (`flex min-h-0 flex-1 flex-col xl:flex-row`), visually equivalent to `grid-cols-[240px_minmax(0,1fr)_320px]`; grid syntax not forced |
| TopBar | `h-14` (56px, tightened from 68px, 00 §4.5), `sticky top-0 z-30` |
| DatasetSidebar | `xl:w-[240px]` (converged from 264, 00 §4.5); below xl it is a top block (`w-full max-h-[46vh]`, existing behavior retained) |
| Canvas | `flex-1 min-h-[560px]` (status quo retained); `min-h-0` ensures internal scrolling |
| Detail right panel | `xl:w-[320px]` (converged from 340, 00 §4.5); below xl it is a bottom block (existing behavior retained, content in 03) |
| Node card | width 288px / header 56px / field row 34px / collapsed body 48px (`lib/layout.ts` constants, explicitly unchanged in 00 §4.5) |
| Group node | width 248px (status quo retained) |

z-index relationships (00 §6 layer table, item by item):

| Layer | z | Landing point on this page |
|---|---|---|
| Canvas content | 0 (inside React Flow) | nodes/edges/handles; seed node raised via React Flow `zIndex: 4` (current value retained, no global tier) |
| Canvas overlays | `z-20` | Controls, MiniMap, `EdgeLabelRenderer` tooltip (`.react-flow__panel` keeps current z-20); loading/error overlay keeps current `z-20` |
| Top bar | `z-30` | TopBar sticky |
| Drawer / modal / Toast | `z-40/41`, `z-50/51`, `z-[60]` | docs 03/05/06; not used on this page |
| Sidebar / right panel | no z | current `relative z-20` / `relative z-10` **removed** (parallel panels need no stacking; z-20 would conflict semantically with canvas overlays) |

## 3. Region-by-Region Visual Spec

### 3.1 Top Bar TopBar (h-14, bg-card)

Container: `sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card px-4 xl:px-6`. Delete the existing `bg-surface/95 backdrop-blur-sm` translucency (restraint principle: the top bar is never translucent); delete `flex-wrap / min-h-[68px] / py-3` (height fixed at 56px; narrow-screen wrapping is handled by responsive hiding of inner controls; current `flex-wrap` behavior narrows to a single row, `gap-y-3` removed).

**Control order (left→right)**:

1. **Brand**: `Brand` (BrandMark 34px current value + name `text-base`; `Brand` / `BrandMark` changes in doc 01 §7#20–21, TopBar invokes it with `text-brand-800` as the mark background).
2. **Vertical divider**: `hidden h-8 w-px bg-line xl:block` (current value retained).
3. **Title block**: `hidden xl:block`; eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Workspace / Lineage Canvas"; `h1` `text-[13px] font-semibold text-ink-soft`.
4. **Global search** (`md:ml-2 md:max-w-[340px] md:flex-1 min-w-[180px]`, 00 §7.2 left-icon spec, compact `h-8`):

```html
<div class="group relative">
  <label htmlFor="dataset-search" class="sr-only">Search datasets or fields</label>
  <span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint transition-colors duration-150 group-focus-within:text-brand-600">
    <Icon name="search" size={14} />
  </span>
  <input class="field-input h-8 rounded-lg pl-9 pr-[92px] text-[13px]" ... />
  <!-- Right-side accessories: clear button h-6 w-6 (hit area ≥24) / kbd "/" / count visible/total -->
  <kbd class="rounded border border-line bg-card px-1.5 font-mono text-[11px] leading-4 text-ink-faint">/</kbd>
  <span class="font-mono text-[11px] tabular-nums text-ink-faint">{visibleCount}/{datasetCount}</span>
</div>
```

5. **AI assistant button** (secondary skeleton + AI color accent, `aria-expanded` / `aria-haspopup` retained):

```html
class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[13px] font-medium transition-colors duration-150 focus-visible:... "
<!-- default: border-line bg-card text-ink-muted  hover:border-ai/25 hover:text-ai-deep
     active (aiOpen): border-ai/25 bg-ai-soft text-ai-deep, sparkles icon text-ai -->
```

6. **Version button**: secondary variant (00 §7.1): `border border-line-strong bg-card text-ink-soft`, hover `border-brand-400 text-brand-700`.
7. **Hop count group** (container `flex items-center gap-2 rounded-lg border border-line bg-card p-1 pl-2.5`; "Hops" eyebrow `font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint`):

| Tier | Classes |
|---|---|
| unselected default | `flex h-6 min-w-[25px] items-center justify-center rounded-md px-1.5 font-mono text-[11px] font-medium text-ink-muted transition-colors duration-150 hover:bg-subtle hover:text-ink` |
| selected | Same as above, replaced with `bg-brand-600 text-white` |
| Subgraph loading spinner | `h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-brand-300 border-t-brand-700` (00 §7.10 top bar small spinner) |

(`role="group"`, `aria-pressed`, `aria-label="N hops"` current behavior retained; hit area 25×24 ≥ 00 §10.7.)

8. **Language toggle** (`LanguageToggle`, 00 §7.12): between the hop group and the user area; two-segment `ZH | EN`, h-7 container + h-6 segment buttons, selected `bg-subtle text-ink`.
9. **User area** (`flex items-center gap-2 border-l border-line pl-3`):
   - Trigger button: `flex items-center gap-2 rounded-lg px-1 py-1 hover:bg-subtle` + unified focus ring; avatar `flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 font-mono text-[11px] font-medium text-white` (replaces pine-800).
   - Username `max-w-[110px] truncate text-[13px] font-medium text-ink`.
   - **Role badge** (replaces the existing mono 8.5px plain text, spec 00 §7.4): admin `border-transparent bg-brand-800 text-white` / editor `border-brand-200 bg-brand-50 text-brand-800` / viewer `border-line bg-subtle text-ink-muted`, skeleton `inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium leading-none`.
   - chevron-down 12px `text-ink-faint`, `rotate-180` when expanded (`transition-transform duration-150` retained).

**User dropdown menu** (00 §7.3 custom menu):

```html
<div class="absolute right-0 top-full z-30 mt-2 w-[200px] overflow-hidden rounded-lg border border-line bg-card py-1 shadow-float animate-fade-in" role="menu">
  <div class="border-b border-line-soft bg-page px-3 py-2.5">
    <!-- Username text-[13px] font-medium text-ink; role row: role badge + role text text-[11px] mono text-ink-muted -->
  </div>
  <!-- Menu items (only admin sees "User Management"): flex h-8 items-center gap-2 px-3 text-[13px] text-ink-soft hover:bg-subtle focus-visible:bg-subtle -->
  <!-- "Sign out": mt-1 border-t border-line-soft, same menu item spec -->
</div>
```

(The menu uses `z-30`, the same layer as the top bar—see pending item #3 at the end. `aria-haspopup="menu"` / `aria-expanded` / Esc and outside-click close behavior retained.)

### 3.2 Left Dataset Sidebar DatasetSidebar (w-240, bg-card)

Container: `flex w-full shrink-0 flex-col border-b border-line bg-card xl:h-full xl:w-[240px] xl:border-b-0 xl:border-r` (replaces `bg-[#f7f4ec]/80` and `xl:w-[264px]`; removes `z-20`).

**① Header** (`border-b border-line-soft px-4 py-3`):
- Eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Data assets".
- Title row: `text-[13px] font-semibold text-ink` "Datasets" + count badge `rounded-full border border-line bg-card px-1.5 font-mono text-[11px] tabular-nums text-ink-muted`; right icon block `flex h-7 w-7 items-center justify-center rounded-lg border border-line bg-card text-ink-faint` (database 14px).
- Search-hit hint (conditionally rendered): `text-[12px] text-ink-muted`, numbers `font-mono tabular-nums text-ink`.
- Seed note: `mt-2 text-[12px] leading-4 text-ink-faint` "Select a dataset as the seed to load a ±N-hop subgraph".

**② Filter area** (`border-b border-line-soft px-4 py-3`):
- Eyebrow "Filters", same spec as above.
- Confidence select (00 §7.3 native select): `.field-input h-8 rounded-md pr-8 text-[12px]` + 14px chevron on the right.
- Two checkboxes: `label mt-1.5 flex cursor-pointer items-center gap-1.5 text-[12px] text-ink-muted`, input `h-3 w-3 accent-brand-600` (replaces the `text-pine-700` accent).
- Description text: `mt-1.5 text-[11px] leading-4 text-ink-muted` (the rule forbidding ink-faint on subtle backgrounds applies here to a white background, but per the 00 §2.2 hard rule, promoting small text to muted is safer).

**③ Dataset list** (`min-h-0 flex-1 overflow-y-auto px-2.5 py-2.5`):

List item button (`aria-current` retained):

| State | Class combination |
|---|---|
| default | `group relative w-full overflow-hidden rounded-lg border border-transparent px-3 py-2 text-left transition-colors duration-150 hover:border-line hover:bg-subtle` |
| hover extra | Left indicator bar `absolute inset-y-2 left-0 w-[2.5px] rounded-r-full bg-brand-400 opacity-0 group-hover:opacity-45` (formerly pine-400) |
| selected (seed) | `border-brand-100 bg-brand-50`; left indicator bar `bg-brand-600 opacity-100`; name `text-brand-800`; id `text-brand-700`; "Seed" badge `rounded bg-brand-100 px-1.5 py-px font-mono text-[11px] uppercase text-brand-800` |

Inline typography: name `truncate text-[13px] font-medium text-ink` (selected `text-brand-800`) + field count `shrink-0 font-mono text-[11px] tabular-nums text-ink-faint`; second-row id `truncate font-mono text-[11px] text-ink-faint` (selected `text-brand-700`) + right arrow (chevron-right 12px, always visible `text-brand-600` when selected, appears on hover when not selected—current interaction retained). List item entrance `animate-fade-up` + `animationDelay: index*24ms, max 240ms` (current value retained).

**④ Bottom legend area** (`shrink-0 border-t border-line-soft px-4 py-3.5`):
- "Current subgraph" stat card: `rounded-lg border border-line bg-subtle/60 px-2.5 py-2`; eyebrow `font-mono text-[11px] uppercase text-ink-faint` + status dot `h-1.5 w-1.5 rounded-full bg-brand-600`; count row `font-mono text-[12px] tabular-nums text-ink-soft`, numbers `font-medium text-ink`.
- Edge legend (line-sample SVGs share the same source as getEdgeVisual, 00 §2.4):

| Legend | SVG spec (exactly the same parameters as getEdgeVisual, to avoid legend vs actual-line mismatch) |
|---|---|
| Field-level lineage | `stroke="#475569"` (lineage-imported) 1.55px solid |
| Table-level lineage | `stroke="#64748B"` (lineage-imported-weak) 1.4px dashed `4 5` |
| Same-name field match (inferred) | `stroke="#94A3B8"` (lineage-derived) 1.3px dotted `2 4` |
| Trace chain on field click | `stroke="#EA580C"` (lineage-focus) 2.6px solid, text `text-danger-deep` |
| AI suggested · pending confirmation | `stroke="#4F46E5"` (lineage-ai) 1.8px dashed `6 5`, text `text-ai-deep` |

Legend text `text-[12px] text-ink-muted`; source badge row (three `SourceBadge`s + unknown fallback) spec in §3.6; footnote `text-[11px] leading-4 text-ink-muted`.

### 3.3 Canvas Area LineageCanvas

**Container and background**: `relative h-full min-h-[560px] bg-page bg-dot-grid bg-grid-24` (00 §2.5: page background + dot grid). **Delete** the `<Background variant="Dots">` component—the dot grid is now provided by the container CSS class (explicit in 00 §8.2(5)); `.lineage-flow` background `#F8FAFC` already landed in index.css with 00 (just verify during development).

**Zoom controls Controls** (bottom-left, `position="bottom-left"`): white background, `border-line`, `rounded-lg`, `shadow-float`; buttons 27×27 (index.css `.lineage-controls` already has the new values: button hover `bg-page text-brand-700`, dividers `border-line-soft`, verify). `showInteractive={false}` retained.

**MiniMap** (bottom-right, `position="bottom-right"`, `pannable zoomable` retained):
- Container: white background, `border-line`, `rounded-lg`, `shadow-float`, 152×98 (current value retained, hidden below md retained).
- Node colors: seed `#EA580C (brand-600)` (brand-600), normal `#CBD5E1` (line-strong); `nodeStrokeColor="#FFFFFF"` (card); mask `rgba(248,250,252,0.65)` (page base). `ariaLabel="Lineage canvas thumbnail"` retained.

**Top-left toolbar** (`Panel position="top-left"`):

```html
<div class="flex flex-col gap-1.5">
  <!-- Main bar -->
  <div class="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-card p-1.5 pr-2 shadow-float">
    <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white"><Icon name="network" size={14} /></span>
    <div class="px-0.5">
      <div class="max-w-[140px] truncate text-[13px] font-medium text-ink">{seedName}</div>
      <div class="mt-0.5 font-mono text-[11px] tabular-nums text-ink-faint">N datasets · M edges</div>
    </div>
    <span class="mx-1 h-5 w-px bg-line" aria-hidden="true" />
    <button class="... h-7 secondary sm ...">{Collapse all / Expand all}</button>
  </div>
  <!-- Group actions bar (appears when ≥2 selected or groups exist, animate-fade-in) -->
  <div class="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-card p-1.5 pr-2 shadow-float">
    <span class="flex h-7 w-7 items-center justify-center rounded-lg border border-line-soft bg-subtle text-ink-muted"><Icon name="group" size={14} /></span>
    <!-- "Collapse selected (N)": border-brand-200 bg-brand-50 text-brand-800 hover:border-brand-300 (h-7) -->
    <!-- "Expand all groups (N)": secondary h-7 -->
  </div>
</div>
```

(Replaces the current `bg-surface/92 backdrop-blur-md shadow-sm`; buttons uniformly `text-[12px]`, icons 12px.)

**Bottom hint bar** (`Panel position="bottom-center"`, `hidden md:block` retained):

```html
<div class="flex items-center gap-2.5 rounded-full border border-line bg-card/90 px-3 py-1.5 font-mono text-[11px] text-ink-muted shadow-float">
  <span>Drag to pan</span><span class="h-2 w-px bg-line" />…<!-- existing copy and separator structure retained -->
</div>
```

### 3.4 DatasetNode Node Card (w-288 full spec)

Card anatomy:

```
┌────────────────────────────────────┐  ← top 2px accent bar (seed bg-brand-600/80; non-seed bg-line-strong/70)
│ ◉━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◉ │  ← table-level handle (left/right, top:28, 9px square r2)
│ ▾ │ dwd_order          [Seed] │▦│  │  ← header h-14: collapse button h-6 w-6 + name 13px + id/count 11px + table icon
├────────────────────────────────────┤     seed header bg-brand-50 border-b-brand-200; non-seed bg-subtle border-b-line-soft
│ ·order_no          STRING   ✦      │  ← field row h-[34px]: field name 11px mono + type chip + AI candidate badge (✦)
│ ·order_date        DATE            │  ← field-level handles on both sides of the row (7px dot)
│ …                                  │
│   ▸ N more fields collapsed  h-26  │  ← expand/collapse toggle row
└────────────────────────────────────┘
Collapsed state: header h-14 + "Expand N fields" dashed button h-8 (total height 56+48, layout constant)
```

**Card container states** (00 §2.5):

| State | Class combination |
|---|---|
| default | `dataset-card group/dataset relative w-[288px] rounded-xl border border-line-strong bg-card shadow-node transition-shadow duration-150` |
| hover | Border unchanged, shadow tightens to `hover:shadow-card` (explicit in 00 §2.5) |
| selected (single/multi-select) | `shadow-node-active` (1.5px brand-600 outer ring + deep blue shadow; landed by index.css `.react-flow__node-dataset.selected .dataset-card`, 00 §8.2(5)) |
| keyboard focus | `.react-flow__node-dataset:focus-visible .dataset-card`: `outline: 2px solid rgba(37,99,235,0.65)` + `outline-offset: 3px` (00 §2.5) |
| seed (persistent) | `shadow-node-active` + top 2px bar `bg-brand-600/80` (non-seed bar `bg-line-strong/70`); React Flow `zIndex: 4` raise retained |
| entrance | `dataset-card-in` 250ms `out-quint` (00 §8.2(5)) |

**Header (h-14)**:
- Seed: `bg-brand-50 border-b border-brand-200`; non-seed: `bg-subtle border-b border-line-soft` (replaces `bg-[#f8f5ed]`).
- Collapse button: `flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-ink-faint transition-colors duration-150 hover:bg-card hover:text-brand-700` (header background is subtle/brand-50, so hover uses white) + unified focus ring; existing `aria-label` retained.
- Name: `truncate text-[13px] font-medium text-ink` (00 §3.3 node title 500; replaces 12px semibold).
- Seed badge: `shrink-0 rounded-full border border-brand-200 bg-card px-1.5 py-px font-mono text-[11px] uppercase text-brand-800` (00 §2.5 "seed badge text-brand-800").
- id and count row: `font-mono text-[11px] text-ink-faint` (00 §3.2 11px tier "node id"; separator dot `h-[2px] w-[2px] rounded-full bg-line-strong` retained).
- Table icon block: `flex h-6 w-6 items-center justify-center rounded-md border`; non-seed `border-line-soft bg-card/60 text-ink-faint`, seed `border-brand-200 bg-card text-brand-700`.

**Field row (h-[34px])**:
- Row container: `group/field relative flex h-[34px] items-center rounded-md px-2 transition-colors duration-150 hover:bg-subtle/70` (Clew revision: normal hover uses neutral gray; `brand-50` is reserved for traced rows only, to avoid non-hit rows being misread as part of the chain; 00 §2.5).
- Field name: `min-w-0 truncate font-mono text-[11px] font-medium text-ink-soft transition-colors duration-150 group-hover/field:text-brand-800` (00 §3.2 explicit 11px mono; hover orange 00 §2.5).
- Type chip: `shrink-0 rounded border border-line-soft bg-page/60 px-1 py-px font-mono text-[11px] uppercase text-ink-faint` (replaces `bg-canvas/55` and the 8px font size).
- **AI candidate edge badge (new visual element)**: when this field is an endpoint of any `source='ai'` edge, render sparkles 12px `text-ai` to the right of the type chip, `title="Pending AI candidate lineage exists"` + `aria-hidden` (textual semantics are carried by the edge and detail panel). Data source: passthrough note in §7#14.
- **Field trace state (new)**: after clicking a field, field rows hit by the trace chain switch to the brand orange family (the neutral hover rule yields)—Clew's "light up the clue" brand moment:

| State | Class combination |
|---|---|
| focused row (clicked) | `bg-brand-50 ring-1 ring-inset ring-brand-300/80 hover:bg-brand-100/70`; field name `text-brand-700`; `h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500` dot to the left of the name (aria-hidden) |
| chain-related row | `bg-brand-50/70 hover:bg-brand-100/50`; field name `text-brand-700/90` |
| hit field-level handle | `.field-handle-traced`: `opacity: 1; border-color: #EA580C; background: #FFF7ED` + outer ring `0 0 0 2px rgba(234, 88, 12, 0.16)` (landed in index.css) |

Data passthrough and clear timing in dev doc §7.3 "Field Trace Chain".

**Handle system** (landed in index.css, 00 §2.5 + §8.2(5), spec reference here):

| handle | Spec |
|---|---|
| table-level (`table:in/out`, top:28) | 9px square r2: white background + `border-line-strong`(#CBD5E1) + outer ring `0 0 0 2px rgba(248,250,252,.9)`; hover `border-brand-700 bg-brand-100` + `box-shadow: 0 0 0 3px rgba(37,99,235,.15)` |
| field-level (`field:in/out:<name>`, vertically centered in row) | 7px dot: white/page background + `border-line-strong`, opacity 0.55; node hover or self hover → `border-brand-600 bg-brand-50`, opacity 1 + blue ring |
| transition | `transition ... 150ms ease` (index.css current value is 150ms, consistent with 00 §5.1, verify) |
| viewer | `isConnectable={false}` current behavior retained (no line dragging, not grayed out) |

**Collapsed state and toggle**:
- Whole-card collapse: the body contains a `p-2` inner dashed button `flex h-8 w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-line text-[12px] text-ink-muted transition-colors duration-150 hover:border-brand-300 hover:bg-brand-50/60 hover:text-brand-700`.
- Empty fields: `flex h-[42px] items-center justify-center gap-1.5 rounded-md border border-dashed border-line-soft text-[12px] text-ink-faint` (ink-faint on white is allowed, placeholder semantics).
- "N more fields collapsed / collapse to first 5": `flex h-[26px] w-full items-center gap-1.5 rounded-md px-2 text-[11px] text-ink-faint transition-colors duration-150 hover:bg-brand-50/60 hover:text-brand-700` (`aria-expanded` retained).

### 3.5 GroupNode Collapsed Group and LineageEdge Edges

**GroupNode (w-248, view-layer temporary object, visually weaker than data nodes)**:

| Element | Class combination |
|---|---|
| container | `group relative w-[248px] rounded-xl border border-dashed border-brand-600/65 bg-brand-50/85 p-3 shadow-node transition-shadow duration-150 hover:shadow-card` (`selectable={false}`, table-level handle `isConnectable={false}` status quo retained) |
| icon block | `flex h-7 w-7 items-center justify-center rounded-lg border border-brand-200 bg-card text-brand-700` |
| count badge | `rounded-full border border-brand-200 bg-card px-1.5 py-px font-mono text-[11px] text-brand-800` "N datasets" |
| group name | `mt-2 truncate text-[13px] font-medium text-ink` (replaces pine-900) |
| "Click to expand" | `mt-1 flex items-center gap-1.5 font-mono text-[11px] text-brand-700` |

**LineageEdge four line types** (`getEdgeVisual` constants replaced; shape/dash pattern/width all unchanged, only color values go through the 00 §2.4 lineage group):

| Form | stroke token | Dash pattern | Width | Extra |
|---|---|---|---|---|
| `source='ai'` (AI suggested) | `lineage-ai` `#4F46E5` | dashed `6 5` | 1.8 | `animated` (flowing; React Flow 1s current value retained; still under `prefers-reduced-motion`) |
| `source='manual'` field-level | `lineage-manual` `#0D9488` | solid | 1.7 | — |
| `source='manual'` table-level | `lineage-manual` `#0D9488` | dashed `4 5` | 1.7 | — |
| imported field-level | `lineage-imported` `#475569` | solid | 1.55 | — |
| imported table-level | `lineage-imported-weak` `#64748B` | dashed `4 5` | 1.4 | — |
| cross-group aggregate edge | same-source `lineage-*` color | dashed `5 4` | 1.5 | opacity 0.85 (current value carried over); not selectable |
| same-name field match (inferred, `derived`) | `lineage-derived` `#94A3B8` | dotted `2 4` | 1.3 | view-derived line, `selectable: false`; tooltip read-only (header "Same-name field match · inferred" + `derived` badge + description, no action buttons), opacity 0.9 |
| trace chain hit (`focusState='chain'`) | `lineage-focus` `#EA580C` | original form's dash pattern | 2.6 | `animated` flow, `zIndex: 2`, marker in the same orange |

**Field trace focus state (`focusState`, after clicking a field)**: edges hit by the chain switch entirely to `lineage-focus` brand orange, width 2.6, and `animated`; non-hit edges (including table-level edges and cross-group aggregate edges) get `focusState='dim'`—opacity → 0.15, arrow marker `withAlpha(original color, 0.3)`. On hover/selection, opacity recovers to ≥0.9 (`LineageEdgeView` inline override: `active ? max(style.opacity, 0.9)`), line width takes `max(current width, 2.4 / AI 2.8)`, and a traced 2.6 line does not fall back on hover. For the derivation algorithm and clear timing see dev doc §7.3; clicking a field with no related fields neither highlights nor dims.

Path: `getSmoothStepPath` (borderRadius 18 / offset 30) + `MarkerType.ArrowClosed` (15×15 same color); 18px transparent hit path retained (accessibility guarantee that thin lines can be hovered).

**hover / selected**:
- hover: width → 2.4 (AI edges 2.8) + `filter: drop-shadow(0 1px 1px rgba(15, 23, 42, 0.18))` (ink-based rgba, same source as the 00 §4.4 shadow family; replaces the old dark-green base); hit path `cursor: pointer` (replaces `default`—edges are clickable to open details, so the cursor must signal it).
- selected: width → 2.8 + same drop-shadow.
- transition: `transition: stroke-width 150ms ease, opacity 150ms ease` (current 150ms retained).

**Edge tooltip card** (shown on hover/selection, `EdgeLabelRenderer`, `nodrag nopan`, 130ms hide delay retained):

```html
<div class="edge-tooltip nodrag nopan pointer-events-auto absolute z-20 w-[268px]" role="tooltip">
  <div class="animate-fade-in rounded-lg border border-line bg-card p-3 text-left shadow-float">
    <!-- Header row: category label font-mono text-[11px] uppercase text-ink-faint + SourceBadge -->
    <!-- Endpoint row: fromLabel → toLabel, font-mono text-[12px] text-ink (arrow-right 12px text-ink-faint) -->
    <!-- Detail grid: label text-[11px] text-ink-faint; value text-[13px] mono text-ink-soft (transform/confidence tabular-nums/source) -->
    <!-- note (optional): border-t border-line-soft pt-2 text-[12px] text-ink-muted -->
    <!-- Button row: View details / Edit (secondary sm h-7), Delete (danger ghost: border-danger/25 bg-danger-soft text-danger-deep hover:border-danger/45) -->
  </div>
</div>
```

(Width 268px, `border-t border-line-soft` separators, aggregate-edge read-only branch retained; delete the existing `bg-surface/98 backdrop-blur-sm` and `rounded-xl`—overlays uniformly use `rounded-lg` + opaque white.)

### 3.6 SourceBadge (Finalized on This Page, Referenced by 03)

00 §7.4 source badge full table implemented (skeleton `inline-flex items-center gap-1 rounded-full border px-2 h-5 text-[11px] leading-none` + dot `h-1.5 w-1.5 rounded-full`):

| source | Class combination | Dot |
|---|---|---|
| imported | `border-brand-200 bg-brand-50 text-brand-800` | `bg-brand-600` |
| manual | `border-warning/25 bg-warning-soft text-warning-deep` | `bg-warning` |
| ai | `border-ai/25 bg-ai-soft text-ai-deep` | `bg-ai` |
| unknown fallback | `border-line bg-card/70 text-ink-muted` | `bg-ink-faint` |

Replace `SOURCE_META` and `UNKNOWN_META` in `SourceBadge.tsx` per the table above (pine→blue, ochre→warning, ai same-name value swap); `withDescription`, `title`, `sourceMeta` export behavior unchanged.

### 3.7 Workspace Container Misc

- Root: `bg-canvas` → `bg-page`.
- **Delete** the 1px gradient decorative line at the top of `<main>` (`bg-gradient-to-r from-transparent via-line-strong/60 to-transparent`)—pure decoration, violates 00 §1.2 principle 1, and the sidebar/canvas already have border layering.
- Mounting and layering of ConfirmDialog / drawers / Toast in 00 §6; content belongs to 03/05/06.

## 4. Component State Spec (Summary of This Page's Interactive Elements)

| Component | default | hover | active/selected/focus | disabled |
|---|---|---|---|---|
| Top bar search | `.field-input h-8` (border-line bg-card/60) | `border-line-strong` | focus `border-brand-600 + ring-brand-600/15`; `/` shortcut focuses | — |
| Clear button (in search) | `text-ink-faint` (h-6 w-6) | `bg-subtle text-ink-soft` | unified ring | — |
| AI assistant button | secondary + `text-ink-muted` | `border-ai/25 text-ai-deep` | open state `border-ai/25 bg-ai-soft text-ai-deep` | — |
| Version button | secondary | `border-brand-400 text-brand-700` | unified ring | — |
| Hop count button | `text-ink-muted` | `bg-subtle text-ink` | selected `bg-brand-600 text-white`; unified ring | — |
| User menu trigger | transparent | `bg-subtle` | menu open `aria-expanded` (no persistent selected color on the button) | — |
| Menu item | `text-ink-soft` | `bg-subtle` | `focus-visible:bg-subtle` | — |
| Sidebar list item | `border-transparent` | `border-line bg-subtle` | seed `border-brand-100 bg-brand-50` + indicator `bg-brand-600` | — |
| Confidence select / checkbox | §7.3 / `accent-brand-600` | select hover `border-line-strong` | select focus blue | — |
| Canvas node | `border-line-strong bg-card shadow-node` | `shadow-card` | selected/seed `shadow-node-active`; keyboard focus outline 2px brand-600/65 | viewer handle not connectable (rendering unchanged) |
| Table-level handle | white `border-line-strong` | `border-brand-700 bg-brand-100`+ring | same as hover while dragging | `isConnectable=false` (viewer) |
| Field-level handle | opacity 0.55 `border-line-strong` | node hover/self hover: `border-brand-600 bg-brand-50` opacity 1 | same as hover | same as above |
| Field-level handle (traced state) | — | — | chain hit: `border #EA580C` + `bg #FFF7ED`, opacity 1, orange outer ring (`.field-handle-traced`, §3.4) | same as above |
| Field row (trace chain) | same as default | orange hover (`bg-brand-100/*`, neutral hover yields) | focused row orange ring + orange dot, chain rows light orange background (§3.4) | — |
| Edge | see §3.5 line-type table (including derived lines/traced state) | 2.4/2.8 thicker + drop-shadow + `cursor:pointer`; traced hit edges start at 2.6 | selected 2.8 + tooltip pinned; with `focusState='dim'` opacity 0.15, hover recovers ≥0.9 | aggregate edges/derived lines not selectable (no hover action buttons) |
| Toolbar buttons | secondary h-7 | secondary hover | unified ring | — |
| Collapse selected button | `border-brand-200 bg-brand-50 text-brand-800` | `border-brand-300` | unified ring | — |

## 5. Data States

| Area | Empty state | Loading state | Error state |
|---|---|---|---|
| Dataset list | No search: §7.9 empty state (database icon 16px + "No datasets yet"); search with no results: "No matching datasets" + "Clear search" link button `text-brand-700 underline decoration-brand-300 underline-offset-2` | Skeleton: `animate-soft-pulse rounded-lg border border-line-soft bg-subtle`, 4 block rows (00 §7.10, replaces `bg-white/55` rows) | danger card: `rounded-lg border border-danger/25 bg-danger-soft`, title `text-[13px] font-medium text-danger-deep`, body `text-[12px] text-danger-deep`, retry button secondary sm (replaces the entire rosewood set) |
| Canvas (no graph) | Centered dashed card: container `border-dashed border-line-strong bg-card/75 rounded-2xl px-8 py-9` (remove backdrop-blur and fine-grid background); icon block `h-12 w-12 rounded-xl border border-brand-200 bg-brand-50 text-brand-600` (network 22px); main copy `text-xl font-medium text-ink` "Select a dataset" (00 §3.2 empty-state main copy tier); description `text-[13px] leading-5 text-ink-muted` | Overlay: `absolute inset-0 z-20 bg-page/60 flex items-center justify-center` (no blur); card `rounded-lg border border-line bg-card px-4 py-3 shadow-float` + spinner `h-4 w-4 border-2 border-brand-200 border-t-brand-600` (§7.10) + title `text-[13px] font-medium text-ink` / subline `text-[11px] mono text-ink-faint`; `role="status" aria-live="polite"` retained | Overlay same as above; error card `rounded-xl border border-line bg-card p-5 shadow-float`, icon block `bg-danger-soft text-danger`, title `text-[13px] font-semibold text-ink`, body `text-[12px] text-ink-muted`, retry button primary sm (replaces pine-800); `role="alert"` retained |
| Sidebar "Current subgraph" | Whole card hidden when `graph` is null (current behavior) | Follows canvas loading; the card itself unchanged (data is expressed by the canvas overlay) | Same as left |
| Top bar | count `0/0` shown as usual | small spinner inside the hop group (§3.1#7) | — |
| Toast | — | — | 00 §7.8 (z-[60]) |

## 6. Interaction and Motion (00 §5)

| Interaction | Motion |
|---|---|
| Node entrance | `dataset-card-in` 250ms `out-quint` (converges to 360ms, 00 §8.2(5)) |
| List item entrance | `animate-fade-up` 300ms, stagger 24ms (current value retained) |
| Dropdown / tooltip enter/exit | `animate-fade-in` 200ms `ease-out` (00 §5.2); tooltip hide delay 130ms retained (logic unchanged) |
| hover transitions (buttons/list items/field rows/header button) | `transition-colors duration-150` |
| Node shadow / handle | `transition-shadow` / handle transition 150ms (index.css current value is the target tier) |
| Edge hover/selected width | `transition: stroke-width 150ms, opacity 150ms` |
| fitView viewport animation | `duration: 380 → 300` (00 §10.8 cap 300ms; 100ms delay and padding 0.18 etc. unchanged) |
| AI suggested edge flow | React Flow `animated` (1s loop, current value retained); still under `prefers-reduced-motion` |
| Field trace chain | hit edges `animated` flow (same parameters as AI edges); dim/restore uses opacity 150ms transition; flow stops under `prefers-reduced-motion` |
| Group actions bar appearance | `animate-fade-in` 200ms (new entrance, state feedback) |
| Box selection | `.react-flow__selection`: `background: rgba(37,99,235,0.15)` (brand-600/15), `border: 1px solid rgba(37,99,235,0.55)` (brand-600/55)—opacity from 00 §8.1 extension tier; pending write-back to 00 (see pending #2) |
| All | `prefers-reduced-motion: reduce` globally disabled (current index.css rule, changes must not bypass it) |

## 7. Change List for Existing Components

Same-name value swaps (pine→blue, rosewood/ember→danger, ochre→warning, ai same-name value swap, ink/line same-name value swap) are globally replaced per 00 §9; the table below lists only changes beyond those mappings.

| # | Component - Current - Target - Tokens/classes involved |
|---|---|
| 1 | `Workspace.tsx` - root `bg-canvas` - change to `bg-page` - `bg-page` |
| 2 | `Workspace.tsx` - 1px gradient decorative line at top of `<main>` (`z-10` gradient) - delete - none (00 §1.2 principle 1) |
| 3 | `TopBar.tsx` - `min-h-[68px] flex-wrap gap-x-5 gap-y-3 px-4 py-3 bg-surface/95 backdrop-blur-sm` - change to `h-14 flex items-center gap-3 px-4 xl:px-6 bg-card` (single row, remove translucency) - `h-14`, `bg-card`, `gap-3` |
| 4 | `TopBar.tsx` - title eyebrow `text-[8.5px]`, h1 `text-[13px]` - eyebrow `text-[11px]`, h1 keeps `text-[13px]` - `text-[11px]` |
| 5 | `TopBar.tsx` - search `h-9 rounded-lg pl-9 pr-[92px] text-[12px]`, focus `pine-500`, icon 15px - change to `h-8`, `text-[13px]`, focus blue (built into .field-input), icon 14px - `h-8`, `brand-600` |
| 6 | `TopBar.tsx` - clear button `h-5 w-5` - change to `h-6 w-6` (hit area ≥24, 00 §10.7) - `h-6 w-6` |
| 7 | `TopBar.tsx` - kbd `text-[9px]`, count `text-[9px]` - both `text-[11px]` - `text-[11px]` |
| 8 | `TopBar.tsx` - AI button/version button `text-[10.5px]`, AI default `bg-canvas/55` - unify to §7.1 secondary skeleton `text-[13px]`; AI active `border-ai/25 bg-ai-soft text-ai-deep` retained, default background changed to `bg-card` - `text-[13px]`, `bg-card` |
| 9 | `TopBar.tsx` - hop button selected `bg-pine-800`, font size `text-[10.5px]` - selected `bg-brand-600 text-white`, font size `text-[11px]` - `bg-brand-600`, `text-[11px]` |
| 10 | `TopBar.tsx` - subgraph spinner `border-pine-300 border-t-pine-700` - change to `border-brand-300 border-t-brand-700` (§7.10) - `brand-300/700` |
| 11 | `TopBar.tsx` - avatar `bg-pine-800`, role row mono 8.5px text - avatar `bg-brand-800`; role text replaced with the 00 §7.4 role badge (h-5 rounded-full text-[11px], three sets for admin/editor/viewer) - `bg-brand-800`, three role badge sets |
| 12 | `TopBar.tsx` - user menu `z-50 w-[192px] rounded-xl`, items `py-2 text-[10.5px] hover:bg-canvas/70` - change to §7.3: `z-30 w-[200px] rounded-lg`, items `h-8 px-3 text-[13px] hover:bg-subtle`, header block `bg-page` - `z-30`, `rounded-lg`, `text-[13px]`, `bg-subtle` |
| 13 | `DatasetSidebar.tsx` - `xl:w-[264px] bg-[#f7f4ec]/80 relative z-20` - change to `xl:w-[240px] bg-card`, remove `z-20` - `w-[240px]`, `bg-card` |
| 14 | `DatasetSidebar.tsx` - eyebrow/title/description font sizes mixed 8–10px - eyebrow `text-[11px]`, title `text-[13px]`, list name `text-[13px]`, id/count/badge `text-[11px]`, checkbox label `text-[12px]` - font size tiering (00 §3.2) |
| 15 | `DatasetSidebar.tsx` - list item selected `border-pine-200 bg-surface`, indicator `bg-pine-600`, name `text-pine-800`, seed badge `bg-pine-100 text-pine-700 text-[8px]`, hover `bg-surface/70` - selected `border-brand-100 bg-brand-50`, indicator `bg-brand-600`, name `text-brand-800`, seed badge `bg-brand-100 text-brand-800 text-[11px]`, hover `bg-subtle` - `brand-50/100/600/800`, `bg-subtle` |
| 16 | `DatasetSidebar.tsx` - checkbox `text-pine-700` accent, select focus pine - `accent-brand-600`, select follows §7.3 (focus blue) - `brand-600` |
| 17 | `DatasetSidebar.tsx` - skeleton `bg-white/55`, error card rosewood, empty-state link pine - skeleton `bg-subtle` (§7.10), error card danger combination, link `text-brand-700 decoration-brand-300` - `bg-subtle`, danger set, blue link |
| 18 | `DatasetSidebar.tsx` - legend SVG lines `#2f64d8 / #66756e`, stat dot `bg-pine-500`, stat card `bg-surface/70` - line colors use the four lineage values (§3.2④), dot `bg-brand-600`, card `bg-subtle/60 border-line` - `lineage-*`, `brand-600` |
| 19 | `LineageCanvas.tsx` - container `bg-canvas bg-fine-grid bg-grid-28` + `<Background Dots gap=23 color="#c9c2b3">` - change to `bg-page bg-dot-grid bg-grid-24`, delete the `<Background>` component (dot grid provided by container class; `.lineage-flow` background already replaced in index.css) - `bg-dot-grid bg-grid-24` |
| 20 | `LineageCanvas.tsx` - MiniMap `nodeColor #2f8268/#b7c9c0`, stroke `#fffdf8`, mask beige - seed `#EA580C (brand-600)`, normal `#CBD5E1`, stroke `#FFFFFF`, mask `rgba(248,250,252,0.65)` - `brand-600`, `line-strong`, `card`, `page` |
| 21 | `LineageCanvas.tsx` - toolbar `bg-surface/92 backdrop-blur-md shadow-sm`, icon block `bg-pine-800 text-pine-100`, buttons `text-[9.5px]` - toolbar `rounded-lg border-line bg-card shadow-float` (no blur), icon block `bg-brand-600 text-white`, buttons `h-7 text-[12px]` (secondary / collapse-selected light-blue tier) - `shadow-float`, `bg-brand-600`, `text-[12px]` |
| 22 | `LineageCanvas.tsx` - bottom hint bar `bg-surface/80 text-[8px] backdrop-blur-sm border-line/85` - change to `rounded-full border-line bg-card/90 shadow-float text-[11px] text-ink-muted` (no blur) - `text-[11px]`, `bg-card/90` |
| 23 | `LineageCanvas.tsx` - fitView `duration: 380` - change to `300` (00 §10.8 cap) - `300ms` |
| 24 | `LineageCanvas.tsx` - loading overlay `bg-canvas/55 backdrop-blur-[1px]` + spinner pine - change to `bg-page/60` (no blur), spinner `border-brand-200 border-t-brand-600`, card `rounded-lg shadow-float` - `bg-page/60`, §7.10 spinner |
| 25 | `LineageCanvas.tsx` - error card icon `bg-rosewood-soft text-rosewood`, retry button `bg-pine-800` - icon block danger combination, retry primary sm (`bg-brand-600`) - danger group, `bg-brand-600` |
| 26 | `LineageCanvas.tsx` - empty-state card `bg-fine-grid` background + `font-display text-[24px]` title + icon block pine - remove grid background and blur; title `text-xl font-medium font-sans text-ink`; icon block `border-brand-200 bg-brand-50 text-brand-600` - `text-xl`, blue icon block |
| 27 | `LineageCanvas.tsx` (index.css) - box-selection rectangle has no custom style - add `.react-flow__selection` rule: `background: rgba(37,99,235,0.15); border: 1px solid rgba(37,99,235,0.55)` - `brand-600/15`, `brand-600/55` (pending write-back to 00) |
| 28 | `DatasetNode.tsx` - card `rounded-[14px]`, seed `border-pine-400/80`, header `bg-pine-50/85 / bg-[#f8f5ed]`, top bar `bg-pine-500/80` - `rounded-xl`; seed header `bg-brand-50 border-brand-200`, bar `bg-brand-600/80`; non-seed header `bg-subtle border-line-soft` - `rounded-xl`, blue family, `bg-subtle` |
| 29 | `DatasetNode.tsx` - header name `text-[12px] font-semibold`, id/count `text-[8.5px]`, seed badge `text-[7.5px]` - name `text-[13px] font-medium`, id/count `text-[11px]`, seed badge `text-[11px]` (§3.4) - font size tiering |
| 30 | `DatasetNode.tsx` - field name `text-[10.5px]` hover `text-pine-800`, row hover `bg-pine-50/60`, type chip `text-[8px] bg-canvas/55` - field name `text-[11px]` hover `text-brand-800`, row hover `bg-brand-50/70`, chip `text-[11px] bg-page/60` - 00 §2.5 / §3.2 |
| 31 | `DatasetNode.tsx` - collapse button/collapse row hover `text-pine-700 bg-pine-50/60` - change to `hover:text-brand-700 hover:bg-brand-50/60`, unified focus ring - `brand-700`, blue ring |
| 32 | `DatasetNode.tsx` - no AI candidate indicator - add an AI candidate badge to field rows (sparkles 12px `text-ai`, §3.4); data passthrough: `LineageCanvas` derives `aiEndpointFields: string[]` from existing `graph.edges` when building nodes (`source==='ai'` and any endpoint is a field name in this node) and puts it into `DatasetNodeData` — **display-only derived field, does not change any edge construction/selection logic** - `text-ai` |
| 33 | `GroupNode.tsx` - `border-pine-400/70 bg-pine-50/85`, badge/title pine family, `text-[8.5px]` - §3.5 spec: `border-brand-600/65 bg-brand-50/85`, badge blue family `text-[11px]`, title `text-[13px] text-ink` - blue family, `text-[13px]/[11px]` |
| 34 | `LineageEdge.tsx` - `getEdgeVisual` four hard-coded colors `#2f64d8/#a36b11/#52645c/#8b958f` - color values replaced with the four lineage token constants (dash/width/other logic unchanged) - `lineage-ai/manual/imported/imported-weak` |
| 35 | `LineageEdge.tsx` - hit path `cursor: 'default'`, active drop-shadow `rgba(27,42,37,0.14)` - `cursor: 'pointer'`, drop-shadow `rgba(15,23,42,0.18)` (ink base) - `cursor-pointer` |
| 36 | `LineageEdge.tsx` - tooltip `rounded-xl bg-surface/98 backdrop-blur-sm`, inner font sizes 8–10.5px, buttons pine/rosewood hover - `rounded-lg bg-card shadow-float` (no blur); font sizes 11/12/13 tiers; buttons secondary sm / danger ghost (§3.5); outer `z-50` changed to `z-20` (canvas overlay tier) - `rounded-lg`, `bg-card`, font size tiering, `z-20` |
| 37 | `index.css` (canvas section) - each item in 00 §8.2(5) (handle/Controls/edge transition 150ms, `.lineage-controls`/`.lineage-minimap` `rounded-lg` 8px, blue values, `.react-flow__panel` z-20) **already landed with the 00 migration** (current file is the target value) - verify item by item during development, no new changes - none |
| 38 | `Brand.tsx` / `SourceBadge.tsx` - see doc 01 §7#20–21 and §3.6 of this document - - |

`lib/layout.ts`: **zero changes** (explicit constants in 00 §2.5 unchanged).

## 8. Accessibility Notes (Specific to This Page)

1. **Canvas keyboard accessible**: `nodesFocusable` retained, node focus outline (2px `brand-600/65` + offset 3px) not clipped (00 §10.3); edges `focusable={false}` is an existing trade-off (edge actions via tooltip/detail panel), keep it registered.
2. **Color is not the sole encoding**: lineage source = color + dash pattern (solid/dashed/flowing) + badge text, triple encoding (00 §10.6); the AI badge has tooltip text as a fallback.
3. **Hit areas**: hop buttons ≥25×24, icon buttons (history/close/collapse etc.) ≥24×24, search clear 24×24, handles are a canvas exception (drag interaction, compensated by the existing 18px edge hit area).
4. **`/` shortcut** and kbd visual hint retained; shortcuts do not hijack input state (current logic).
5. **Legend dual encoding**: sidebar legend = line sample (solid/dashed) + color + text label, so color-blind users can distinguish "field-level vs table-level vs AI".
6. **`aria-current`** (sidebar selected item), `aria-pressed` (hop count), `aria-expanded` (AI button/menu/field expand), edge `ariaLabel` (four-endpoint description) all retained, not lost to the revision.
7. **MiniMap/Controls**: `ariaLabel` retained; MiniMap hidden below md (touch-screen scenarios are not the primary path).
8. **Loading/error overlays**: `role="status"` / `role="alert"` + `aria-live` retained, not broken by the visual revision.

## Pending Tokens (Suggested Write-Back to 00)

| # | Gap | Suggested value | Notes |
|---|---|---|---|
| 1 | Edge hover/selected width tiers | hover 2.4 / selected 2.8 (AI edges always 2.8) + selected `drop-shadow(0 1px 1px rgba(15,23,42,0.18))` | Current values carried over; suggests fixing them as a note in 00 §2.4 to avoid divergent tuning later |
| 2 | Box-selection rectangle style | `background: rgba(37,99,235,0.15)` + `border: 1px solid rgba(37,99,235,0.55)` (opacity from 00 §8.1 extension tier 15/55) | 00 has no React Flow selection style; suggests adding it to the §2.5 canvas-specific table |
| 3 | Dropdown menu z tier | `z-30` (same layer as the top bar, follows the trigger) | 00 §6 layer table does not cover "non-modal overlay menus"; current z-50 equals the modal mask tier and is semantically conflicting |
| 4 | MiniMap color mapping | node line-strong / seed brand-600, stroke card, mask `rgba(248,250,252,0.65)` | All are existing token combinations; no official mapping row; suggests adding to §2.5 |
| 5 | Cross-group aggregate edge spec | same-source color, width 1.5, dashed `5 4`, opacity 0.85 (current values carried over) | 00 §2.4 table only covers the four main forms |
| 6 | fitView viewport animation duration | 300ms | 00 §5.1 has no "viewport animation" entry; suggests adding a row (React Flow duration parameter) |
| 7 | Canvas toolbar/bottom hint bar surfaces | `rounded-lg border-line bg-card shadow-float` (hint bar `bg-card/90`) | Same family as Controls/MiniMap as "canvas overlay container" spec; suggests adding a unified row in §2.5 |

## 2026-10-26 Review Increment (see [08 Review Fix Batch](../03_dev/08_review-fix-batch-2026-10-26.md) R14–R16)

This round adds the following specs to the canvas workspace per the review conclusions; all are **additions** to the existing specs above and do not change the established visual baseline:

1. **TopBar responsive degradation** (R14): below `lg`, "Import / AI assistant / Version" become icon-only (retaining `aria-label` + `title`); below `md`, the hop group (1–5) collapses into a single dropdown and the language toggle merges into the user menu; add `min-w-0` to the header container. Goal: eliminate horizontal overflow at 768–1279px. Visual tokens unchanged; only layout density changes with breakpoints.
2. **Canvas empty state and filter hint** (R15): ① while the dataset list is loading on the first screen, the canvas shows a loading card (reusing the error/skeleton style) and must not flash "Please select a dataset"; ② when confidence/source filters clear all edges, a Panel at the top of the canvas shows an i18n hint "No visible edges under the current filter" (same style as the bottom hint bar).
3. **Mobile canvas onboarding** (R15): below `md`, the bottom hint bar becomes a dismissible overlay on first entry (`localStorage` remembers the read state); the four copy lines reuse existing i18n, plus a new "Box-select ≥2 nodes to collapse them into a group".
4. **"Edge list" secondary entry** (R16): add a collapsible floating Panel at the bottom-left of the canvas (same style as the overlay container spec for the legend region), listing the first 20 edges of the current filtered graph (direction + source badge); each row is keyboard focusable; pressing Enter selects it through the existing edge-selection chain to open `EdgeDetailPanel`; when a field is selected, this list prioritizes and highlights its upstream/downstream edges. **Does not** change the hover tooltip card behavior, only completes the keyboard-accessible path.
5. **Interaction semantics fix**: the hop switcher button group changes from `role="group"` + `aria-pressed` to `role="radiogroup"` + `aria-checked` (radio semantics); React Flow's built-in Controls' English aria-label is replaced with localized copy.
