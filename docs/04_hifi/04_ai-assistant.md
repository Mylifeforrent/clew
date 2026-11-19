# 04 · AI Assistant

> Role: the workspace's "natural-language lineage query" layer. The 480px drawer `AiAssistantDrawer` on the right hosts LLM status checks, multi-turn conversation, read-only tool-call trace display, and graph-linked canvas updates (`onGraph` → `Workspace.applyGraph`, 02 §1). This page is the site's second main battlefield for the `ai` color group (indigo, 00 §2.4) (the first is the AI suggested edge): AI identity, model badge, and tool-trace emphasis always use `ai / ai-soft / ai-deep`, never mixed with the primary blue.
>
> Basis and sources:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (single source for tokens, referenced as "00 §x.x"; drawer §7.7, button §7.1, input §7.2, badge §7.4, chip §7.5, empty state §7.9, loading §7.10, layering §6)
> - `docs/02_prototype/clew-lofi-prototype.html` AI conversation screen (information-architecture baseline: header status + message stream + tool trace + suggest card + bottom input)
> - `docs/03_dev/02_frontend-development.md` §6 (AiAssistantDrawer responsibilities), §7.6 (graph update linkage), §9.3-3 (suggest is not in the conversation tool set)
> - `docs/03_dev/05_api-reference.md` §13 (/ai/status, /ai/chat: `answer` / `tool_trace` / optional `graph`; 503/502 error semantics)
> - Component source: `prototype/frontend/src/components/AiAssistantDrawer.tsx` (includes the `TOOL_LABELS` four-tool label mapping and 64-character truncation in `compactArgs`)
>
> Scope constraint: visual and layout changes only; conversation logic is unchanged (status check, history truncation to 50 entries × 8000 characters, AbortController, 503 fallback to the unconfigured state, Esc/overlay close are all preserved); no new dependencies, no new components. The low-fidelity "in-conversation suggest candidate card" has no data source in the current implementation (§3.6 marks [TBD-FE]); this page only defines its visual baseline.

---

## 1. Page role and entry points

| Item | Description |
|---|---|
| Entry | TopBar "AI Assistant" button (02 §3.1#5, open state `border-ai/25 bg-ai-soft text-ai-deep`) → conditional render in `Workspace` |
| Component | `AiAssistantDrawer.tsx` (the only component, containing the internal `ToolChips`) |
| Exit | Esc / overlay click / close button (existing behavior); on open, lock `body` scroll and move initial focus into the input |
| Page state | `status` (LLM configuration), `entries` (conversation stream), `sending`; `focus` is passed through from the selected field/dataset on the canvas |
| Graph linkage | When the response carries `graph`, `onGraph` overwrites the canvas subgraph (`aiGraph` takes precedence), and a "Canvas updated" bar is shown inside the message |

## 2. Layout structure

Drawer width tier: **480px** (00 §4.5, explicit "AI conversation" entry). Layering: overlay `z-40` + panel `z-[41]` (00 §6/§7.7; the current `z-[72]` is an out-of-tier value, see §7#1). The DOM structure keeps the "overlay container + nested panel" form, visually equivalent to `fixed right-0 top-0` in 00 §7.7.

```
┌──────────────────────────────────────────────────────────┐ Overlay z-40 bg-slate-900/25 (blur removed)
│ ┌──────────────────────────────────────────────────────┐ │ Panel z-[41]  w-[480px]  bg-card
│ │ ① Header h-12  px-4  border-b border-line-soft       │ │ [✦ icon block] AI Assistant + LLM status badge │ [↻][✕]
│ ├──────────────────────────────────────────────────────┤ │
│ │ ② Focus bar h-9  px-4  bg-page  border-b             │ │ Current focus · dwd_order.order_no │ 🔒 Read-only tools
│ ├──────────────────────────────────────────────────────┤ │
│ │ ③ Status banner (conditional, see §5)                │ │ Not configured (warning) / status read failed (danger)
│ ├──────────────────────────────────────────────────────┤ │
│ │ ④ Message scroll body  flex-1  bg-page  px-4 py-4    │ │ role="log" aria-live="polite"
│ │    · Empty state: icon block + 3 example prompts     │ │
│ │    · User bubble (right-aligned, blue-50)            │ │
│ │    · AI bubble (left-aligned, bg-card)               │ │
│ │       ├ Tool trace card (collapsed/expanded)         │ │
│ │       ├ Body + canvas updated bar (success state)    │ │
│ │       └ suggest candidate card ([TBD-FE] baseline)   │ │
│ │    · sending dashed bubble                           │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ ⑤ Input area  border-t border-line-soft  p-3         │ │ Multiline textarea + send + line counter
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

Region sizes (all referencing 00 tokens):

| Region | Size / spacing |
|---|---|
| Panel | `w-full sm:w-[480px]` (00 §4.5 drawer 480 tier), `border-l border-line`, `shadow-float` (00 §4.4) |
| Header | `h-12` (00 §7.7 drawer skeleton), `px-4` |
| Focus bar | `h-9 px-4` (drawer header secondary info bar, see Pending additions #2 at the end) |
| Message body | `flex-1 min-h-0 overflow-y-auto px-4 py-4 pb-6`; item spacing `space-y-3` (12px) |
| Input area | `p-3` (00 §7.7 explicitly "AI conversation bottom input area border-t border-line-soft p-3") |
| Controls | Send button `h-9` (lg tier); textarea `min-h-[56px]` (about 3 lines; currently converges to 54px) |

## 3. Per-region visual specs

### 3.1 Header (h-12)

```html
<header class="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4">
  <div class="flex min-w-0 items-center gap-2.5">
    <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ai/25 bg-ai-soft text-ai">
      <Icon name="sparkles" size={16} />
    </span>
    <h2 id="ai-drawer-title" class="text-[14px] font-semibold text-ink">AI Assistant</h2>
    <!-- LLM status badge (three states, see table below), ml-1 -->
  </div>
  <div class="flex shrink-0 items-center gap-1">…refresh / close icon buttons…</div>
</header>
```

**LLM status badge** (attached to the right of the title, follows the three `getAiStatus` states):

| State | Class combination |
|---|---|
| Configured (has model) | `max-w-[180px] truncate rounded-full border border-ai/25 bg-ai-soft px-2 py-px font-mono text-[11px] text-ai-deep` (`title` keeps the full name; 00 §2.6 ai-deep on ai-soft 8.88:1) |
| Loading | spinner `h-3 w-3 animate-spin rounded-full border-[1.5px] border-ai/25 border-t-ai` + `aria-label="Reading AI status"` |
| Not configured / status unknown | `rounded-full border border-line bg-subtle px-2 py-px font-mono text-[11px] text-ink-muted`, text "Not configured" / "Status unknown" (semantics are carried by banner ③; the badge stays neutral) |

Right-side icon buttons (refresh / close): ghost spec (00 §7.1) `flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft` + shared focus ring; existing `aria-label` / `title` preserved; close icon 16px, refresh 14px.

### 3.2 Focus bar (h-9)

```html
<div class="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-line-soft bg-page px-4">
  <span class="shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">Current focus</span>
  <span class="min-w-0 truncate font-mono text-[12px] font-medium text-blue-700" title={focusLabel(focus)}>{focusLabel(focus)}</span>
  <span class="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-card px-1.5 py-px font-mono text-[11px] text-ink-muted">
    <Icon name="lock" size={10} />Read-only tools
  </span>
</div>
```

(When the focus value is empty, show "No dataset focused", lower the color to `text-ink-faint`, and drop `font-medium`; the original header explanation "tool calls are read-only; the canvas switches automatically when graph updates are involved" is compressed into the right-side chip + input placeholder, avoiding three lines of text piling up in the header.)

### 3.3 Status banner (conditional render, directly below the focus bar)

Container: `shrink-0 border-b border-line-soft px-4 py-2.5`, with two semantic variants of the inline notice (soft background always with deep body text, 00 §2.3):

| Branch | Class combination | Content |
|---|---|---|
| `statusError` (status API failed) | `flex items-start gap-2.5 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[12px] leading-5 text-danger-deep`, `role="status"`, warning icon 12px `text-danger` | Title "Unable to read AI status" `font-medium` + error copy + retry button (see below) |
| Not configured (`!statusLoading && !status.configured`, including the 503 fallback) | Same skeleton, with `border-warning/25 bg-warning-soft text-warning-deep`, warning icon 12px `text-warning` | Title "AI assistant temporarily unavailable" + `NOT_CONFIGURED_TEXT` (existing copy) + trailing note "After configuring, click refresh at the top right to re-check" |

Retry button (statusError branch only): danger ghost sm variant `inline-flex h-7 items-center gap-1 rounded-md border border-danger/25 bg-card px-2 font-mono text-[11px] text-danger-deep transition-colors duration-150 hover:border-danger/45` + shared ring (refresh 11px, "Retry").

### 3.4 Message scroll body

Container: `min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4 pb-6`, `role="log" aria-live="polite" aria-label="AI conversation messages"` (existing, preserved). Item stream `space-y-3`, **no entrance animation added** (conversation uses "immediate appearance" as feedback; adding motion would interfere with reading; 00 §1.2 principle 5).

**User message** (right-aligned):

```html
<div class="flex flex-col items-end">
  <div class="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint">You</div>
  <div class="max-w-[88%] whitespace-pre-wrap break-words rounded-xl rounded-tr-md border border-blue-100 bg-blue-50 px-3 py-2 text-[13px] leading-5 text-ink">
    {entry.content}
  </div>
</div>
```

(blue-50 background + blue-100 border express the identity semantics of "one's own message" (00 §2.1 blue-100 scenario); body text uses neutral `ink` to keep long questions readable. `max-w-[88%]` is a one-off layout value for this page.)

**AI message** (left-aligned):

- Name row: `mb-1 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint`, sparkles 10px `text-ai` + "AI Assistant".
- Bubble: `rounded-xl rounded-tl-md border px-3 py-2.5` — normal `border-line bg-card`; error `border-danger/25 bg-danger-soft/70`.
- Body: `whitespace-pre-wrap break-words text-[13px] leading-6 text-ink-soft`; error entries `text-danger-deep`; when the model returns no text, fall back to `text-[12px] italic text-ink-faint` "The model returned no text answer." (existing copy).

### 3.5 Tool-call trace card (collapsed / expanded)

Replaces the existing flat `ToolChips` chips (8.5px + `title` tooltip) and upgrades them to a collapsible card. Labels align with `TOOL_LABELS` (search_fields=Search fields / get_field_details=Field details / trace_lineage=Trace lineage / get_field_history=Change history; unknown tools fall back to "Tool call", existing logic preserved).

**Collapsed (default)** — one-line summary:

```html
<div class="mb-2 overflow-hidden rounded-lg border border-line bg-page">
  <button type="button" aria-expanded={open} class="flex w-full items-center gap-2 px-2.5 py-2 text-left transition-colors duration-150 hover:bg-subtle/60 + shared ring">
    <Icon name="code" size={12} className="shrink-0 text-ink-faint" />
    <span class="shrink-0 text-[11px] font-medium text-ink-muted">Tool calls · {trace.length}</span>
    <span class="flex min-w-0 flex-1 flex-wrap gap-1">
      <!-- Each chip: TOOL_LABELS label + success/failure marker -->
      <span class="inline-flex max-w-full items-center gap-1 rounded border border-line bg-card px-1.5 py-px font-mono text-[11px] text-ink-muted">
        <span className="shrink-0">{TOOL_LABELS[item.tool] ?? 'Tool call'}</span>
        <span className={item.ok ? 'font-semibold text-success' : 'font-semibold text-danger'} aria-label={item.ok ? 'Call succeeded' : 'Call failed'}>{item.ok ? '✓' : '✗'}</span>
      </span>
    </span>
    <Icon name="chevron-down" size={12} className={`shrink-0 text-ink-faint transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
  </button>
</div>
```

**Expanded** — a detail list under the header (`border-t border-line-soft px-2.5 py-1.5 space-y-1.5`), each row:

- Row container: `flex items-start gap-2 rounded-md px-1 py-1.5`; **failed rows** get a full-row `bg-danger-soft` background and `text-danger-deep` labels (soft background + deep body text, 00 §2.3 rule).
- Status icon: check 12px `mt-0.5 shrink-0 text-success` / close 12px `text-danger` (replaces the existing ✓/✗ characters, distinguishable for color-vision deficiency).
- Label row: label text `text-[12px] font-medium text-ink-soft` + English name chip `rounded bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-muted`.
- Full arguments: `mt-1 whitespace-pre-wrap break-all rounded-md bg-subtle px-2 py-1.5 font-mono text-[11px] leading-4 text-ink-muted` (full `JSON.stringify(item.args)`; replaces the 64-character truncation of the collapsed state; subtle background uses ink-muted body text, 00 §2.2 hard rule).

Collapse/expand is pure UI state (`aria-expanded`) and does not affect message data; collapsed by default, messages containing failed calls expanded by default.

### 3.6 AI suggested candidate card (suggest, [TBD-FE] design baseline)

> Data source note: the read-only tool set of `/ai/chat` **does not include** suggest_lineage; lineage suggestions currently use REST `POST /ai/suggest`, triggered from the field details in `DetailPanel` (03 §3.2⑥, the candidate card spec is finalized). This section is the visual baseline for the in-conversation candidate card (the form shown on the low-fidelity AI screen); implementation requires either the backend returning candidates in the conversation response `[TBD-BE]` or frontend extension of the linkage `[TBD-FE]`; this round of high-fidelity work does not implement it.

```html
<!-- As a variant of an AI message: dashed bubble (dashed = unconfirmed, same origin as the dashed line semantics of the AI suggested edge) -->
<div class="rounded-xl rounded-tl-md border border-dashed border-ai/25 bg-ai-soft/40 p-3">
  <div class="mb-1.5 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ai-deep">
    <Icon name="sparkles" size={10} className="text-ai" />AI Assistant · suggest_lineage
  </div>
  <p class="font-mono text-[12px] leading-5 text-ink-soft">
    <span class="text-ink-faint">ods_raw.order_time</span>
    <Icon name="arrow-right" size={12} className="mx-1 text-ink-faint" />
    <span class="text-blue-700">dwd_order.order_date</span>
  </p>
  <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
    <span class="rounded-full border border-ai/25 bg-ai-soft px-1.5 py-px font-mono text-[11px] tabular-nums text-ai-deep">Confidence 0.6</span>
    <span class="text-[12px] leading-4 text-ink-muted">{reason}</span>
  </div>
  <div class="mt-2 flex items-center justify-between border-t border-line-soft pt-2">
    <span class="text-[11px] leading-4 text-ink-muted">On confirm, the edge source is rewritten to manual · requires editor role or above · written to change_log throughout</span>
    <span class="flex shrink-0 items-center gap-1.5">
      <!-- Confirm: primary sm h-7 px-2 text-[12px] (check 12px, busy "Confirming…" + spinner) -->
      <!-- Reject: secondary sm h-7 px-2 text-[12px] + hover:border-danger/30 hover:text-danger-deep (trash 12px) -->
    </span>
  </div>
</div>
```

The two-state mutually exclusive disabling (busy) of the button group is exactly the same as the candidate card in 03 §3.2⑥; no separate visual family is introduced.

### 3.7 Graph-update bar (entry.graph)

```html
<div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-success/25 bg-success-soft px-2.5 py-2 text-[12px] text-success-deep">
  <Icon name="network" size={12} className="shrink-0" />
  <span className="font-medium">Canvas updated</span>
  <span className="font-mono text-[11px] tabular-nums">{datasets.length} datasets · {edges.length} edges</span>
  <button type="button" onClick={onClose}
    class="ml-auto rounded px-1.5 py-0.5 font-medium text-success-deep transition-colors duration-150 hover:bg-card + shared ring">
    Close and view
  </button>
</div>
```

(success semantics = one successful canvas linkage; "Close and view" reuses the existing `onClose` and adds no logic — it satisfies the flow of "reviewing the canvas after graph update".)

### 3.8 sending streaming wait bubble

```html
<div class="inline-flex items-center gap-2 rounded-xl rounded-tl-md border border-dashed border-line bg-card/70 px-3 py-2.5">
  <span class="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-ai/25 border-t-ai" aria-hidden="true" />
  <span class="text-[12px] text-ink-muted">Calling tools and organizing the answer…</span>
</div>
```

(Not token streaming output: the backend returns `answer` in one shot, and the wait state is expressed with a spinner + copy; introducing a "typewriter" effect is a functional change, out of scope for this page, see Pending additions #3 at the end.)

### 3.9 Empty state (no messages and not sending)

- Icon block: `flex h-14 w-14 items-center justify-center rounded-2xl border border-ai/25 bg-ai-soft text-ai`, sparkles 24px.
- Primary copy: `text-xl font-medium text-ink` "Query lineage in natural language" (00 §3.2 empty state primary copy 20px tier, replacing the 21px display).
- Description: `mt-2 max-w-[300px] text-[13px] leading-6 text-ink-muted` (existing copy preserved).
- Example prompt buttons (`EXAMPLE_PROMPTS`): `w-full max-w-[300px] rounded-lg border border-line bg-card px-3 py-2 text-left text-[12px] text-ink-muted transition-colors duration-150 hover:border-blue-300 hover:bg-blue-50/60 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50` + shared ring (click fills the input and focuses it, existing behavior).

### 3.10 Bottom input area

```html
<form class="shrink-0 border-t border-line-soft bg-card p-3">
  <div class="flex items-end gap-2">
    <label htmlFor="ai-chat-input" class="sr-only">Ask the AI assistant</label>
    <textarea id="ai-chat-input" rows={2} maxLength={8000}
      class="field-input min-h-[56px] flex-1 resize-none py-2 text-[13px] leading-5 disabled:cursor-not-allowed" … />
    <button type="submit" class="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:… disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400">
      {sending ? <><span class="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-white/40 border-t-white" />Sending</> : <><Icon name="send" size={14} />Send</>}
    </button>
  </div>
  <div class="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-mono text-[11px] text-ink-faint">
    <span>Enter to send · Shift + Enter for newline · only the latest 50 entries are sent</span>
    <span class="tabular-nums">{input.length}/8000</span>
  </div>
</form>
```

- The four placeholder copy branches are preserved (checking / status failed / configured / not configured); `Enter` submits, `Shift+Enter` inserts a newline, `maxLength 8000` — existing logic unchanged.
- Character count: at the 8000 limit it turns `text-danger-deep`; "only the latest 50 entries are sent" is an explicit hint for the existing `slice(-50)` truncation behavior (copy only, no logic added).

## 4. Component state specs

| Component | default | hover | active/focus | disabled/loading | selected |
|---|---|---|---|---|---|
| Header refresh/close | ghost `text-ink-faint` | `bg-subtle text-ink-soft` | shared ring (00 §7.1) | — | — |
| Tool trace collapse button | `bg-page text-ink-muted` | `bg-subtle/60` | shared ring; `aria-expanded` | — | expanded chevron `rotate-180` |
| Trace chip / status icon | `border-line bg-card text-ink-muted` | — | — | — | success `text-success` / failure `text-danger` |
| Example prompt button | `border-line bg-card text-ink-muted` | `border-blue-300 bg-blue-50/60 text-blue-700` | shared ring | `opacity-50 cursor-not-allowed` (inputDisabled) | — |
| suggest confirm | primary sm `h-7` | `bg-blue-700` | ring | any busy → entire group disabled/neutralized | — |
| suggest reject | secondary sm `h-7` | `border-danger/30 text-danger-deep` | ring | same as above | — |
| Close and view (in linkage bar) | `text-success-deep` | `bg-card` | shared ring | — | — |
| Retry (status banner) | `border-danger/25 bg-card text-danger-deep` | `border-danger/45` | ring | — | — |
| Input textarea | `.field-input` (border-line bg-card/60) | `border-line-strong` | `border-blue-600 bg-card + ring-2 ring-blue-600/15` | `opacity-50 cursor-not-allowed` (inputDisabled) | — |
| Send button | `bg-blue-600 text-white` | `bg-blue-700` | `active:bg-blue-800` + ring | `bg-slate-200 text-slate-400` + spinner "Sending"; empty text disabled | — |

## 5. Data states

| State | Design |
|---|---|
| Initial open | Header spinner (status checking) + empty state (example prompt buttons disabled, existing logic `inputDisabled = !configured \|\| sending \|\| statusLoading`) |
| Empty state | §3.9 (no messages) |
| Sending | sending dashed bubble (§3.8) + send button busy + textarea disabled; message body auto-scrolls to bottom (existing `scrollTop` logic) |
| LLM not configured (detected on open or 503 fallback after send) | Header badge "Not configured" + ③ warning banner (on 503, a danger error bubble follows the user message showing the backend 503 detail, existing behavior) |
| Status API failure | Header badge "Status unknown" + ③ danger banner + retry button |
| Single-turn failure (502 upstream / network / 422) | AI error bubble (`border-danger/25 bg-danger-soft/70 text-danger-deep`, §3.4); no message-level retry button — the input area stays available and resending retries (existing behavior, zero logic changes) |
| Empty model answer | "The model returned no text answer." italic fallback (existing) |
| Graph linkage | success linkage bar appended at the end of the message (§3.7) |
| Input over limit | Counter `n/8000` turns `text-danger-deep` at the limit; `maxLength` physically truncates (existing) |

## 6. Interaction and motion (00 §5)

| Interaction | Motion |
|---|---|
| Drawer slide-in | 200ms `out-quint` translateX slide-in (00 §7.7; `drawer-in` keyframe pending write-back to 00, see Pending additions #1; replaces the existing `animate-fade-in`) |
| Overlay fade-in | `animate-fade-in` 200ms (existing, preserved) |
| Header buttons / chip / example buttons hover | `transition-colors duration-150` |
| Trace collapse chevron | `transition-transform duration-150`, expanded `rotate-180` |
| Banner / empty state / sending bubble appearance | `animate-fade-in` 200ms (state-feedback entrances) |
| spinner (status badge / sending / sending button) | `animate-spin` (standard loading element, precedent in doc 01) |
| Message append | no entrance animation (immediate appearance, see §3.4 note) |
| All | globally disabled under `prefers-reduced-motion` (current rule in index.css) |

## 7. Change list for the existing component

Same-name value swaps (pine→blue, rosewood→danger, ochre→warning, ai same-name swaps, ink/line same-name swaps) are handled by the global replacement in 00 §9; the table below lists only changes beyond that mapping.

| # | Component - current - target - tokens/classes involved |
|---|---|
| 1 | `AiAssistantDrawer.tsx` - overlay `z-[72] bg-ink/40 backdrop-blur-[2px]` - change to `z-40 bg-slate-900/25`, remove blur (00 §7.7) - `bg-slate-900/25` |
| 2 | Same - panel `max-w-[460px] bg-surface animate-fade-in` - change to `sm:w-[480px] bg-card border-l border-line shadow-float` + 200ms `out-quint` slide-in - `w-[480px]`, `bg-card`, `drawer-in` |
| 3 | Same - header `py-3.5` free three-tier stack (eyebrow 8.5px + 22px display title + 9.5px description) - change to h-12 single row (icon block + `text-[14px] font-semibold` title + LLM badge 11px + refresh/close), description removed (compressed into the focus-bar chip and placeholder) - `h-12`, `text-[14px]`, `text-[11px]` |
| 4 | Same - model badge / unconfigured badge `text-[8.5px] border-ai/20`, status spinner `h-3 w-3` - §3.1 three-state table: `text-[11px]`, `border-ai/25 bg-ai-soft text-ai-deep` / neutral badge `border-line bg-subtle text-ink-muted` - `text-[11px]`, ai badge group |
| 5 | Same - focus bar `bg-canvas/45`, eyebrow 8.5px, value `text-[9.5px] text-pine-700`, nothing on the right - change to `bg-page`, eyebrow 11px, value `font-mono text-[12px] text-blue-700`, add "Read-only tools" chip (lock 10px) - `bg-page`, `text-[12px]`, `blue-700` |
| 6 | Same - status banner `border-rosewood/25 bg-rosewood-soft` / `border-ochre/25`, body `text-[9.5px]`, retry button `bg-surface/70 ring-pine-500/30` - §3.3: danger / warning combinations, `text-[12px] leading-5` deep body text, retry danger ghost sm + shared ring - danger/warning group, `text-[12px]` |
| 7 | Same - message area `bg-[#fbf9f3]` - change to `bg-page` - `bg-page` |
| 8 | Same - user bubble `rounded-2xl border-pine-200 bg-pine-50/80 text-pine-900 text-[11px]`, name row 8.5px - change to `rounded-xl rounded-tr-md border-blue-100 bg-blue-50 text-ink text-[13px]`, name row `text-[11px]` - `blue-50/100`, `text-[13px]` |
| 9 | Same - AI bubble `bg-surface`, error `rosewood` family, body `text-[11px]` - change to `bg-card border-line`, error danger combination, body `text-[13px] leading-6` - `bg-card`, danger group |
| 10 | `ToolChips` (internal) - flat chips `text-[8.5px] border-line bg-canvas/70`, ✓ `text-pine-600` ✗ `text-rosewood`, 64-character argument truncation + title - change to collapsible/expandable trace card (§3.5): chips `text-[11px]` using TOOL_LABELS labels, ✓ `text-success` ✗ `text-danger`, expanded full-argument mono block; collapse is pure UI state (`aria-expanded`) - `text-[11px]/[12px]`, success/danger |
| 11 | Same - "Canvas updated" bar `border-pine-200 bg-pine-50/80 text-pine-700 text-[9px]` - change to success combination bar (§3.7) + add "Close and view" ghost (only calls existing `onClose`) - success group |
| 12 | Same - empty-state title `font-display text-[21px]`, description `text-[10px]`, example buttons `bg-surface/75 hover:border-pine-300 text-[9.5px] disabled:opacity-55` - title `text-xl font-medium font-sans`, description `text-[13px]`, buttons `bg-card hover:border-blue-300 hover:bg-blue-50/60 text-[12px] disabled:opacity-50` + shared ring - `text-xl`, `text-[13px]/[12px]` |
| 13 | Same - sending bubble `text-[9.5px]` - change to `text-[12px]`, spinner spec preserved (`border-ai/25 border-t-ai`) - `text-[12px]` |
| 14 | Same - send button `h-[42px] rounded-xl bg-pine-800 disabled:opacity-55 font-semibold` - change to primary `h-9 rounded-lg bg-blue-600` four states + disabled neutralized (00 §7.1) - `h-9`, `rounded-lg`, `bg-blue-600` |
| 15 | Same - textarea `text-[11px] min-h-[54px]`, counter row `text-[8px]` two static hints - textarea `text-[13px] min-h-[56px]`; counter row `text-[11px]` + right-side `n/8000` counter (at limit `text-danger-deep`) + "only the latest 50 entries are sent" hint - `text-[13px]/[11px]` |
| 16 | Same - header button focus `ring-pine-500/35` - shared focus ring (00 §7.1) - `ring-blue-600/60` |
| 17 | (no corresponding implementation) - in-conversation suggest candidate card - §3.6 visual baseline, **not implemented this round** ([TBD-FE]/[TBD-BE], data source see §3.6 note) - ai group + dashed border |

## 8. Accessibility notes (specific to this page)

1. **Conversation semantics**: message area `role="log" aria-live="polite"` (existing, preserved); new messages/errors/sending state are perceivable by screen readers; banner `role="status"`.
2. **Focus management**: opening focuses the input (existing); Esc closes (existing); Tab order: header buttons → message area (trace collapse button) → input area, no focus trap; restoring focus after close is left to the TopBar trigger button (existing DOM unmount behavior, no extra handling).
3. **Icon buttons**: refresh / close `aria-label` + `title` (existing, preserved); trace ✓/✗ use `aria-label` "call succeeded/failed" (existing, preserved).
4. **Trace collapse**: `aria-expanded` expresses the expanded state; expansion is not the only information channel (the collapsed summary already contains all tools and success/failure).
5. **Color is not the only encoding**: tool success/failure = color + ✓/✗ characters; AI identity = indigo color + sparkles icon + "AI Assistant" text; suggest card unconfirmed = dashed border + text description.
6. **Contrast spot checks**: `ai-deep` on `ai-soft` (8.88), `success-deep` on `success-soft` (6.81), `ink` on `blue-50` (≈16:1), `ink-soft` on `card` (10.36) — all within the 00 §2.6 table.
7. **Disabled is not color-only**: sending busy = spinner + "Sending" text; not configured = placeholder copy change + banner text.
8. **reduced-motion**: no continuous animation other than slide-in / spinner; all disabled by the global rule.

## Pending tokens (suggested write-back to 00)

| # | Gap | Suggested value | Note |
|---|---|---|---|
| 1 | Drawer slide-in keyframe | `drawer-in`: `translateX(16px)→0` + fade, 200ms `out-quint` | 00 §7.7 states "slide in 200ms out-quint" but §8.1 keyframes has no matching frames; docs 05/06 depend on the same thing; suggest adding it centrally and then replacing the existing `animate-fade-in` in all three places |
| 2 | Drawer header secondary info bar | `h-9 px-4 bg-page border-b border-line-soft` (eyebrow 11px + value mono 12px) | 00 §7.7 defines only the h-12 header; the AI focus bar and 05's version info bar both need this spec; suggest merging into §7.7 |
| 3 | Conversation bubble corner combination | `rounded-xl` + single corner `rounded-tl-md` / `rounded-tr-md` | 00 §4.2 does not list the "bubble" scenario; suggest adding a row so future conversation UIs do not each invent one |
| 4 | ai border opacity sub-tiers | collapsed suggest card `border-dashed border-ai/25`, outer card `bg-ai-soft/40` | Same origin as Pending additions #4 in doc 03 (mixed use of ai/20/25/40); suggest archiving together |
| 5 | Character counter / truncation hint spec | `font-mono text-[11px] tabular-nums text-ink-faint`, at limit `text-danger-deep` | Same pattern in 03 (marked 4000 characters) and 04 (conversation 8000 characters); suggest adding a "counter row" entry in 00 §7.2 |

## 2026-10-26 review increment (see [08 Review fix batch](../03_dev/08_review-fix-batch-2026-10-26.md) R17 + backend R8–R11)

This round adds the following specs to the AI assistant drawer per review conclusions; all are **additions** to the existing specs above:

1. **Send / stop toggle** (R17): during streaming, the send button switches to "Stop" (danger tone); clicking interrupts the current stream; closing the drawer has the same effect (soft interrupt, the input is restored accordingly). The interrupted turn does not continue within the stream (backend R9 cooperates).
2. **Clear conversation** (R17): the drawer header gains a "Clear conversation" icon button; after a `ConfirmDialog` second confirmation, the conversation history (including tool trace) is cleared; unavailable while a stream is in progress.
3. **Inline candidate confirmation card** (R17): when a `suggest` event (the model generates candidate edges during conversation) arrives, besides the toast and canvas refresh, an **inline candidate card** should also be rendered below this turn's answer bubble — reusing the candidate card's information and actions from the detail panel (confirm / reject / view canvas); for viewer, the card actions are greyed out with the hint "requires editor role". This replaces the earlier broken experience of "only a toast, the user has to find the field themselves".
4. **Badge copy update** (aligned with backend R8): the header "read-only tools" badge changes to "Queries available in real time; write operations such as suggestions/drafts require editor" (zh/en §i18n ai dictionary entries kept in sync).
5. **SSE contract addition (transparent to frontend)**: the backend adds a 15s heartbeat comment frame `: ping` (R9) — the frontend parser looks for `data:` lines per frame; comment frames are safely ignored, no new spec needed on this page; recorded for future reference only.
6. **Rate-limit interaction (429)**: when conversation / suggestions trigger rate limiting, reuse the existing failure alert bar style to show "Too many requests, please try again later" (add i18n key).
