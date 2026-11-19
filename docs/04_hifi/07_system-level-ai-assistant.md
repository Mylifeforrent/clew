# 07 · AI assistant for the system-level lineage prototype (interaction design)

> Positioning: Completes the AI large-model integration layer for [clew-system-lineage-prototype.html](../02_prototype/clew-system-lineage-prototype.html) (system/dataset/field three-level view prototype). The form follows the drawer baseline of [04_AI assistant.md](./04_ai-assistant.md) (status check → focus bar → message stream → tool trace → input area); the toolset extends the system-level tools already finalized in design proposal §6.2; graph update linkage follows design proposal §5.3#7 "AI graph updates and manual browsing share `applyGraph`".
>
> Basis and sources:
> - `docs/01_design/clew-design-proposal.md` §6.2 (toolset: `search_systems` / `trace_system_lineage` / `get_system_details` read-only + `suggest_system_lineage` write-class), §5.3#7 (`SystemGraphPayload` is isomorphic to `GraphPayload`, sharing the rendering protocol)
> - `docs/04_hifi/04_ai-assistant.md` (drawer five-section skeleton, three LLM states, tool trace collapsible card, inline candidate card, canvas-updated bar, send/stop toggle)
> - `docs/03_dev/05_api-reference.md` §13 (/ai/status, /ai/chat: `answer` / `tool_trace` / optional `graph` / `highlights`; 503/502 semantics), §15.1 (`/ai/suggest/systems*` three endpoints, editor+)
> - `docs/03_dev/08_review-fix-batch-2026-10-26.md` R8-R11, R17 (tool-layer role guardrails, 429, stop/clear/inline confirmation card)
>
> Scope constraint: this page is the **interaction design of the prototype**, validating information architecture and flow; mock tool results are scripted data and do not mean the backend has implemented system-level AI endpoints (all of §15.1 is marked `[TBD-BE]`). Real streaming (SSE), typewriter effect, and 429 rate-limit demonstration are out of scope for this round (see §9 pending decisions).

---

## 1. Entry points and drawer skeleton

### 1.1 Entry points (TopBar)

| Entry | Form | Behavior |
|---|---|---|
| "AI assistant" button | Top bar right side, before the role switcher; ai-color badge style (✦ icon + text) | Opens the drawer |
| Pending-suggestion badge | Shown when system edges with `source='ai'` exist (including candidates added at runtime): "✦ N system-level suggestions pending confirmation", badge-ai | Opens the drawer (the suggestion card is visible in the conversation stream) |

Both entries share the same drawer; the badge count updates in real time as suggestions are confirmed/rejected (§7).

### 1.2 Drawer five sections (480px fixed right-side layer, overlay z-index below the panel)

```
┌──────────────────────────────────────────────────────────────────────┐ Overlay rgba(15,23,42,.25)
│ ┌──────────────────────────────────────────────────────────────────┐ │ Panel w=480px bg-card
│ │ ① Header ✦ AI assistant · LLM status badge │ Refresh Clear ✕     │ │ h-12 border-b
│ │ ② Focus bar · Current focus {3-level} │ 🔒 read-only tools        │ │ h-9 bg-page border-b
│ │ ③ Status banner (conditionally rendered)                         │ │ Not configured (warning)
│ │ ④ Message scroll body                                            │ │ role="log" aria-live="polite"
│ │    · Empty state: sample questions ×4 (system-level topics)      │ │
│ │    · User bubble (right) / AI bubble (left)                      │ │
│ │    · Tool trace card (collapsed/expanded)                        │ │
│ │    · Inline candidate card (suggest_system_lineage)              │ │
│ │    · Canvas-updated bar (graph linkage)                          │ │
│ │    · sending waiting bubble                                      │ │
│ │ ⑤ Input area  textarea + send/stop + counter                     │ │ border-t
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

- The drawer coexists with the canvas: opening it does not cover the top bar; overlay click / `Esc` / ✕ closes it; after closing, the canvas keeps the linkage results (subgraph/selected edge do not revert).
- While the drawer is open, any selection/level change on the canvas refreshes the ② focus bar (three-level view focus pass-through, see §3).

## 2. LLM status (header badge + banner)

| State | Header badge | ③ Banner | Input area |
|---|---|---|---|
| Configured | `Configured · <model>` (ai-soft background, ai-deep text, mono) | None | Can send |
| Not configured | "Not configured" (neutral line/subtle background) | warning: "AI assistant temporarily unavailable" + explanation (`LLM_BASE_URL` / `LLM_MODEL` not configured; configure them, then click Refresh to re-check) | disabled, placeholder "AI not configured: configure LLM_BASE_URL / LLM_MODEL in .env to enable" |
| Loading | spinner | None | disabled |

Prototype demo toggle: the "Refresh" button simulates re-detection after a `.env` change, toggling between configured/not-configured and showing a toast. If sending returns 503 (not configured) semantics, append a danger error bubble (reusing the banner copy).

## 3. Focus bar (three-level view focus pass-through)

The focus value changes in real time with the canvas level and selection; the right-side chip "🔒 Read-only tools" has a title completing the review-batch copy: "Queries are available in real time; write operations such as suggestions / drafts require editor".

| Canvas level | Focus bar display | Focus source |
|---|---|---|
| System | `System · dw_platform data warehouse` | `S.selectedSystem` (fallback `S.seed`) |
| Dataset | `Dataset · dws_order_daily daily order summary` | `S.selectedDataset` |
| Field | `Field · dws_order_daily.gmv` | `S.selectedField` (ds + f) |

The focus value is passed through with the request as conversation context (the focus convention of `/ai/chat`, 04 §1); the fourth sample question demonstrates field-level focused Q&A.

## 4. Toolset and permissions (aligned with design proposal §6.2 + batch 08 R8)

| Tool | Corresponding API (§15.1) | Category | Demonstrated on this page |
|---|---|---|---|
| `search_systems` | `GET /systems?q=` | Read-only | Flow A step 1 |
| `trace_system_lineage` | `GET /lineage/systems` | Read-only | Flow A step 2 (returns system subgraph → graph update linkage) |
| `get_system_details` | `GET /systems/{id}` | Read-only | Flow B |
| `search_fields` / `trace_lineage` / `analyze_impact` / `get_field_history` | §13.6 Appendix A8 | Read-only | Flow D (field-level) |
| `suggest_system_lineage` | `POST /ai/suggest/systems` | **Write-class** | Flow C; the tool layer validates by caller role; a viewer trigger returns a tool error and does not persist |
| `suggest_lineage` / `draft_descriptions` | §13 | Write-class | Not demonstrated on this page (finalized in 04) |

Permission behavior:

- **Read-only Q&A**: available to viewer/editor/admin;
- **Suggestion confirmation**: candidate card "Confirm / Reject" buttons are grayed out for viewer + inline hint "Requires editor role" (same convention as 04 §3.6 and 08 R17); editor/admin can operate;
- Confirm/reject both write to `change_log` (`entity_kind='system_edge'`), and after the main DB commit set `graph_state.state='dirty'`; the next read request rebuilds Kùzu automatically (§4.7 versioning convention).

## 5. Tool trace card and message stream

Visuals follow 04 §3.4-3.8 (user blue background right-aligned, AI card background left-aligned, error danger bubble, sending dashed bubble); the prototype implements them with its own CSS variables:

- **Tool trace card**: one card per tool call (aligned with the tool-card form of [clew-hifi-prototype](../02_prototype/clew-hifi-prototype.html)), collapsed by default to a single line `tool ✓ name(args)`; clicking expands parameter and result details; trace success/failure uses ✓/✗ color + character dual encoding.
- **mini result row**: inside the expanded tool card, render tool returns as a three-part row of "badge + mono identifier + note" (hop badge / exact badge / confidence), same family as 04's trace details.
- **sending**: spinner + "Calling tools and composing an answer..."; the send button switches to "Stop" (danger); clicking interrupts the remaining steps of this round and appends a de-emphasized note "This round's answer has been stopped" (the mock equivalent of 08 R17's stop semantics).
- **Clear conversation**: header "Clear" button → ConfirmDialog second confirmation → restores the welcome message (08 R17).

## 6. Graph update linkage (`SystemGraphPayload` → `applyGraph`)

When the AI answer carries `graph`, the frontend feeds the system subgraph from the tool result into the **same** rendering entry as manual browsing; this page implements it by applying `S.level/seed/direction/hops/selectedEdge`:

| Linkage type | Applied action | Canvas behavior |
|---|---|---|
| System subgraph (Flow A) | `level=system, seed=dw_platform, direction=up, hops=3` | System view recomputes the closure; the upstream chain enters the graph |
| System edge selected (Flow B) | `level=system, selectedEdge='finance->dw_platform'` | Edge highlighted + edge drawer row activated + detail panel shows evidence drill-down |
| Field chain (Flow D) | `level=field, focus=dws_order_daily.gmv, selectedEdge=ds:15` | Field view lights up the 3-hop chain |

The message tail appends a "Canvas updated" success bar (dataset/system count + connection count + "Close and view" button, which closes the drawer to look back at the canvas, 04 §3.7). Linkage does not revert: after closing the drawer, the canvas keeps the view given by the AI, and the user can continue manual browsing.

## 7. System-level suggested edge lifecycle (`suggest_system_lineage`)

```
AI generates candidate (source='ai', confidence<1) → inserts system_edge (editor-triggered)
  → Canvas: indigo dashed line + "AI" label + relationship instance row "AI candidate" badge + top bar pending badge +1
  → Manual confirmation (editor+): source ai→manual, dashed line becomes solid, label becomes "explicit/×N",
    writes change_log, marks graph dirty (auto-rebuild on next read request)
  → Reject (editor+): delete the candidate row, write change_log(deleted), mark graph dirty
  → viewer: buttons grayed out, hint "Requires editor role"; tool layer rejects writes as a backstop (R8)
```

- The prototype's initial mock contains one pending candidate: `crm → marketing` (conf 0.62, tag co-selection inference); demo Flow C adds `payment_gateway → finance` at runtime (conf 0.58, channel reconciliation inference).
- The "AI candidate" filter toggle (already in the toolbar) is decoupled from the suggestion lifecycle: filtering only controls visibility and does not change candidate state; once confirmed and promoted, an edge is no longer affected by the AI filter.
- Top bar pending badge = count of `system_edge WHERE source='ai'` (including when the demo cycle edges are enabled).

## 8. Mock conversation flows (sample questions)

Four sample questions in the empty state, covering four categories: "system chain Q&A / edge evidence explanation / suggestion generation / field-level focus"; clicking backfills and **sends immediately** (aligned with clew-hifi-prototype's qchip behavior); grayed out when the LLM is not configured:

| # | Sample question | Tool trace | Canvas linkage |
|---|---|---|---|
| A | What are the upstream systems of the data warehouse? How does the data flow in? | `search_systems("dw_platform")` → `trace_system_lineage(dw_platform, up, 3)` | System view · upstream 3-hop subgraph |
| B | How did the edge from the finance system to the data warehouse come about? Is the evidence sufficient? | `get_system_details("finance")` | System view · selects the `finance→dw_platform` edge and drills down into evidence |
| C | Help me find system-level lineage that may be missing | `suggest_system_lineage(scope=system)` | Candidate dashed edges appear on the canvas + inline candidate card (role-difference demonstration) |
| D | How is the gmv metric calculated? | `trace_lineage("dws_order_daily.gmv", up, 3)` | Field view · lights up the gmv upstream chain |

Answer content must match the prototype mock data (hop count, evidence count, confidence) and explicitly reference the storage tiers (Kùzu variable-length paths / SQLite evidence tables), maintaining the narrative that "the AI is the orchestrator of this system's query tools".

## 9. Accessibility and pending decisions

Accessibility follows 04 §8: `role="log" aria-live="polite"` message area, icon buttons `aria-label`, trace collapse `aria-expanded`, success/failure = color + ✓/✗ character, AI identity = ai color + ✦ + text, disabled = grayed out + copy; `prefers-reduced-motion` disables motion globally.

| # | Pending item | Type | Note |
|---|---|---|---|
| 1 | Real contract of `/ai/chat` for system-level tools | `[TBD-BE]` | Tool names and `tool_trace` structure follow §13.2; the `level=system` shape of the `graph` returned for system-level graph updates needs to be finalized when the backend lands (§15.1 not implemented) |
| 2 | Confirm/reject interaction endpoints for the system-level suggestion card | `[TBD-BE]` | The `/ai/suggest/systems/confirm|reject` contract is finalized; the frontend drawer inline card and the detail panel candidate card share one component |
| 3 | 429 rate limiting, SSE heartbeat, typewriter | `[TBD-FE]` | Follows the existing specs of 04 and batch 08; not demonstrated in this prototype round |
| 4 | Jump details from the suggestion badge to the drawer | `[TBD-UX]` | Currently "opening the drawer shows the candidate card in the conversation stream"; whether to scroll to the card needs review confirmation |
