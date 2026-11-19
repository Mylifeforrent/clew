# 08 · Full-Site Review-Fix Batch (finalized 2026-10-26)

> Purpose: the review-fix batch document for the 2026-10-26 full-site review (layout / interaction accessibility / AI module) — the **single source of truth** for fix-item design, contract changes, and verification records; it follows the "problem / approach / contract / verification" structure of [06_AI Canvas-Linked Highlight Fixes](./06_ai-canvas-highlight-fix.md) and the R numbering in `test_review_fixes.py` (R8–R18 this round).
> Conclusion first: fix 3 P0s (write-type tools in AI chat bypassing the editor threshold, TopBar overflow at narrow-and-medium widths, lineage edge operations not keyboard accessible) + 8 P1s; of the P2 polish items, only 4 are cleaned up in passing, and the rest are **explicitly deferred** (§VI).
> Code baseline: all changes in this round land in the official project directories `backend/src/clew/` and `frontend/src/` (the `prototype/` path in the README's "document-to-code mapping" is the same-source porting baseline and is not repeated here).
> Related: [07_AI Module Evolution Plan](./07_ai-module-evolution-plan.md) (R10 is the first step of its evolution item 10, "context engineering"), [05_API Interface Document](./05_api-reference.md) §13 (this round completes the M5 endpoints), [01_Architecture Design](./01_architecture.md) §3.4.

## I. Review Conclusion Summary

Three main threads (evidence line numbers use the 2026-10-25 code as a snapshot; after the fixes, this round's code is authoritative):

1. **AI module**: The functional loop is complete (SSE streaming, 8 tools, dual-confirmation flow, full change_log trail), but the write-type tools on the chat path (`suggest_lineage` / `draft_descriptions`) have **no role check** — a viewer can trigger writes to the edge table / `description_draft` table via `/ai/chat`, while the direct endpoints require editor, so the permission model is systematically bypassed; in addition, the context has no token budget, there is no stop button, SSE has no heartbeat, disconnects do not propagate, and there is no rate limiting, so long-running scenarios are unmanageable.
2. **Layout and canvas**: The xl breakpoint skeleton is clear, the three states are well covered, and animations are restrained; however, the TopBar inevitably overflows horizontally at 768–1279px, all lineage edge operations depend on the hover toolbar (`edgesFocusable=false`), and keyboard users cannot reach them; the canvas's giant effect reruns dagre in full on every field click, causing perceptible lag on large subgraphs; the first-screen empty state flashes, clearing filters has no explanation, and the mobile hint bar disappears entirely.
3. **Overlays and global concerns**: The 8 overlays each hand-roll overlay / Esc / focus management — Esc closes all overlays at once, Tab traps are missing in 6/8, and focus restoration is missing in 6/8; the root cause is the **absence of a unified foundation**, so any new dialog will keep drifting.

## II. Fix Item Overview

| # | Priority | Fix Item | Key Files | Status |
|---|---|---|---|---|
| R8 | P0 | `run_tool` role guardrails for write-type tools | `ai/tools.py`, `ai/chat.py`, `routes/ai.py` | ✅ |
| R9 | P1 | SSE heartbeat + stop on client disconnect | `routes/ai.py`, `ai/chat.py` | ✅ |
| R10 | P0 | Context budget: tool result truncation + conversation pruning | `ai/chat.py` | ✅ |
| R11 | P1 | In-memory rate limiting for AI routes (no new dependencies) | New `ai/ratelimit.py`, `routes/ai.py` | ✅ |
| R12 | P2, in passing | Description draft prompt language parameterization | `ai/descriptions.py`, `ai/tools.py` | ✅ |
| R13 | P0 | Overlay foundation: `useOverlayBehavior` + `ModalShell` unify the 8 overlays | New `lib/useOverlayBehavior.ts`, `components/ModalShell.tsx` + 8 overlay components | ✅ |
| R14 | P0 | TopBar responsive tightening (768–1279px overflow) | `components/TopBar.tsx` | ✅ |
| R15 | P1 | Canvas fixes: dagre memoization, empty-state flash, filtered-empty hint, mobile hint, Controls aria localization, hops radiogroup | `components/LineageCanvas.tsx` | ✅ |
| R16 | P0 | Keyboard-accessible edge operations: floating "edge list" secondary entry point on the canvas | `components/LineageCanvas.tsx`, `components/Workspace.tsx` | ✅ |
| R17 | P1 | AI drawer: stop button, soft interrupt on close, clear conversation, inline candidate confirmation card, badge copy | `components/AiAssistantDrawer.tsx`, `lib/api.ts` | ✅ |
| R18 | P1 | Toast upgrade, stable `onClose`, misc bundle (role badge / SSE dead code / login per-field validation / wizard format-switch confirmation / mobile copy locator / HistoryDrawer truncation hint / VersionDrawer abort) | See §V | ✅ |

Verification commands (full suite, see §VII):

```
cd backend  && uv run pytest            # Includes new R8–R12 regression cases, fully offline
cd frontend && npm run typecheck && npm run build
```

## III. Backend Design (R8–R12)

### R8 `run_tool` Role Guardrails for Write-Type Tools (P0)

Problem: `/ai/chat*` in `routes/ai.py` only requires viewer (`require_role("viewer")`); `_drive` calls `run_tool(conn, name, args, actor=actor)` without passing a role; `suggest_lineage` / `draft_descriptions` pass viewers through directly — while the equivalent direct endpoints `POST /ai/suggest` and `POST /ai/description-drafts/{id}/accept` require editor, so the `require_role` threshold is bypassed wholesale by the chat path; the drawer header also displays a "read-only tools" badge.

Approach (three layers of defense, primarily the routing layer):

1. Routing layer: `ai_chat` / `ai_chat_stream` keep their minimum threshold unchanged (viewers can ask questions);
2. **Enforcement at the tool layer**: `run_tool` gains a required named parameter `role`; `suggest_lineage` / `draft_descriptions` fall into the `WRITE_TOOLS` set, and when `ROLE_ORDER[role] < ROLE_ORDER["editor"]` it throws `ToolError("This tool requires the editor role; an editor must run lineage suggestions / description drafts from the canvas detail panel")`, which is returned to the model as a tool error (without interrupting the whole round), and `tool_trace` records `ok=false` — database writes must never happen;
3. A sentence is added to the `system prompt`: when a viewer is chatting, write-type tools will be rejected; prompt the user to switch to an editor account or have an editor perform the action on the canvas.

- `role` comes from the `user["role"]` returned by `require_role` (`security.py`); `run_tool`'s `role` is **required**, preventing future callers from omitting it and causing accidental pass-through;
- The MCP server exposes only 5 read-only tools and is unaffected (the decision in 07 §4.6 is unchanged);
- The frontend "read-only tools" badge copy becomes "Queries are immediately available; write proposals require editor confirmation" (delivered together with R17).

### R9 SSE Heartbeat + Stop on Client Disconnect (P1)

Problem: `event_stream` is completely silent between events, so reverse proxies may cut the connection; the worker is a daemon thread, and after the client disconnects it still runs all LLM calls and write tools (including persisting suggestions) — the user is gone, but writes still occur.

Approach (`routes/ai.py`):

1. **Heartbeat**: when the event queue idles for more than 15s, yield the comment frame `: ping\n\n` (an SSE comment frame; the frontend `api.ts` parser looks for `data: ` lines frame by frame, safely skips empty frames, and requires no frontend change);
2. **Stop on disconnect**: add `cancelled = threading.Event()`; set it in the coroutine's `finally` (including `GeneratorExit`) and pass it into orchestration; `stream_run_chat` / `_drive` check at the start of each tool-loop round, and when set throw `ChatInterrupted` (a new exception class in `ai/chat.py`); the worker catches it and exits silently (no error event is appended — the client is already gone);
3. The interrupt check is **before write-tool execution**, ensuring no further database writes occur after cancellation;
4. Non-streaming `/ai/chat` is unchanged; leftover `finally: pass` is cleaned up in passing.

### R10 Context Budget: Tool Result Truncation + Conversation Pruning (P0)

Problem: Tool result JSON is appended to the conversation verbatim (`get_field_details` includes a 50-line source preview, and `trace_lineage` can carry the entire subgraph), the frontend sends back 50 history entries × 8000 characters, and there is no budget control whatsoever — with a real provider, a few rounds blow out the context window.

Approach (`ai/chat.py`, effective for **all** chat entry points):

1. **Tool result truncation**: **after** extracting `graph` / `highlights` / `suggestions` / `drafts` (canvas linkage is unaffected by truncation) and **before** appending the result back to the conversation as `role=tool`, if the JSON serialization exceeds `MAX_TOOL_RESULT_CHARS = 4000` characters, truncate it and append a truncation marker (`…[truncated; full data is N characters]`); truncation affects only the text visible to the model;
2. **Conversation pruning**: add `_estimate_tokens(text)` (ASCII ≈ 4 characters/token, CJK ≈ 1 character/token) and the constant `CONTEXT_TOKEN_BUDGET = 96_000` (optionally overridden in `.env` via `LLM_CONTEXT_TOKEN_BUDGET`, added to config.py); after appending tool results back each round, if the cumulative total exceeds the budget, delete whole blocks starting **from the oldest complete round block** (assistant + all its tool messages, the earliest unit that can be removed as a whole) until below budget; the system message and the current round are never deleted;
3. Explicit boundary: this item implements only the first step, "truncation + pruning"; catalog-summary injection and history summarization belong to later rounds of evolution item 10 in 07 and are out of scope this round.

### R11 AI Route Rate Limiting (P1, No New Dependencies)

Problem: `/ai/chat*` and `/ai/suggest` have no per-user rate limiting; viewers/editors can make unlimited concurrent LLM calls (uncontrolled cost) and heuristic scans.

Approach (new `src/clew/ai/ratelimit.py`):

- `ai_limiter(window_seconds, max_requests)`: a FastAPI dependency factory with an in-memory sliding window (`time.monotonic` + one deque per username + `threading.Lock`); exceeding the limit throws `HTTPException(429, detail=…)` with a `Retry-After` header;
- Mounting: `/ai/chat` and `/ai/chat/stream` → 10 requests per user per 60s; `/ai/suggest*` → 6 per 60s; draft accept/reject are cheap writes and are not rate-limited [TBD-OPS: thresholds are currently guesses and may be tuned after observing usage];
- Windows are counted in process memory, which is sufficient for single-machine deployment; multi-process deployment would require external storage, which this product does not do in its single-machine form (recorded in §V).

### R12 Description Draft Prompt Language Parameterization (P2, in passing)

Problem: `_DRAFT_PROMPT` hard-codes "write a one-sentence Chinese description", so drafts produced in English conversations are also in Chinese.

Approach: `descriptions.draft_descriptions(..., lang: str = "zh")` gains a language parameter with dual prompt templates (zh/en); the `draft_descriptions` tool schema gains a `lang` enum `["zh","en"]` (default zh), filled in by the model according to the conversation language; the direct REST endpoint is unchanged.

### New Tests (Merged into `tests/test_review_fixes.py`, Retaining R Numbers)

- R8: a viewer sends a message that triggers `suggest_lineage` → assert that no candidate is persisted (no `source='ai'` rows in the edge table) + that the corresponding `tool_trace` entry has `ok=false`; the same input with an editor account → persisted normally;
- R9: the SSE test consumes the event stream and asserts that a `ping` comment frame is visible during a long silent round; after the client closes early, assert that no further database writes occur (monkeypatch a slow LLM + query the table before joining the thread) — if parallel cost is too high, degrade to a unit test of `_drive`'s `should_interrupt` (throwing `ChatInterrupted` between rounds);
- R10: fabricate an oversized tool result → assert that the appended message is ≤ the limit and carries the truncation marker; fabricate over-budget history → assert that the oldest round is deleted as a whole and the system message is retained;
- R11: the same user sends `/ai/chat` 11 times in a row (LLM unconfigured; the request is intercepted by the rate-limit dependency before the 503 — note the ordering: the rate-limit dependency is registered after `require_role`; assert 429);
- R12: `lang="en"` → the prompt template is the English version (assert on the arguments passed to `llm.complete`).

## IV. Frontend Design (R13–R18)

### R13 Overlay Foundation: `useOverlayBehavior` + `ModalShell` (P0, Root-Cause Closure)

Current state: the 8 overlays (ConfirmDialog / EdgeCreateModal / ImportWizardModal / PreviewModal / UserManagementModal / VersionDrawer / HistoryDrawer / AiAssistantDrawer) each implement their own behavior: each binds Esc to document without knowing the level (one Esc closes all), Tab traps exist in only 2/8, focus restoration is missing in 6/8, and body scroll locking exists in 7/8 (ImportWizard does not lock). The conclusion is mutual exclusion by convention, not by mechanism.

Approach:

1. New hook `lib/useOverlayBehavior.ts`: when opened, save `document.activeElement`, attach Esc (**only one overlay responds to Esc** — see item 2), trap Tab cycling, restore focus on unmount/close, and lock `body.style.overflow`; the `onRequestClose` callback uniformly goes through `requestClose` (close can be refused while busy);
2. **Esc stack**: a module-level `overlayStack` (push/pop in useEffect); only the top of the stack responds to Esc — when two drawers are open, only the most recent layer closes;
3. New component `components/ModalShell.tsx`: overlay coverage (`fixed inset-0`) + card container (centered dialog / right-side drawer variants) + unified header (icon badge + title + close button) + footer slot; the 8 overlays migrate in, reusing their existing Tailwind classes and replacing only structure (with zero visual change as the goal);
4. All inline `onClose` functions on the Workspace side become `useCallback` (a stability prerequisite beyond R18, delivered together with R13 — drawer effects must not remount and steal focus on parent renders);
5. On delivery, list the migration checklist overlay by overlay (file ⇒ Shell variant) for verification.

### R14 TopBar Responsive Tightening (P0)

Current state: the header uses a fixed-height `h-14 flex` and renders all actions unconditionally; at 768–1279px the total width exceeds the screen and the tail is clipped (only the brand copy and username have responsive hiding).

Approach: below `lg` (1024px), "Import / AI assistant / Version" become icon-only (retaining `aria-label` + `title`); below `md` (768px), the hops group collapses from 5 buttons into 1 dropdown (`select`), and the language switch moves into the user menu; add `min-w-0` to the header for safe overflow degradation. Focus styles remain consistent with the existing ones (`focus-visible:ring`).

### R15 Canvas Fixes (P1)

1. **dagre layout memoization**: split `LineageCanvas`'s giant effect (lines 450–898) into two layers — rerun `layoutDatasets` only when `graph + collapsedGroupIds + expandedDatasetIds` change (`useMemo`); "tracking-state coloring" depends only on `chain` and performs a shallow update (skip rebuilding fields whose node data reference is unchanged);
2. **Empty-state flash**: pass `datasetsLoading` into the canvas so the first screen shows a loading card instead of "Please select a dataset";
3. **Filtered-empty hint**: when the filtered edge count is 0 and the original graph has > 0 edges, show the i18n hint "No visible connections under the current filter" in a Panel at the top of the canvas;
4. **Mobile hint**: change the bottom hint bar into a dismissible overlay shown on first entry below `md` (remembered in `localStorage`; the copy includes "Box-select ≥2 nodes to collapse them into a group");
5. **Controls' built-in English aria-labels** pass through localized text; the hops button group becomes `role="radiogroup"` + `aria-checked`.

### R16 Keyboard-Accessible Edge Operations (P0, Secondary Entry Point Approach)

Problem: `edgesFocusable=false` + a hover-driven toolbar mean keyboard users cannot view/edit/delete edges (the only entry point to `EdgeDetailPanel` is the hover toolbar).

Approach: add a floating "edge list" Panel at the bottom of the canvas (on the same side as the legend, collapsible): by default it shows the first 20 edges of the current filtered graph (read from `filteredGraph.edges`, including direction and source badges); each row is a focusable button, and Enter selects it → goes through the existing `onEdgeSelect` path to open `EdgeDetailPanel`; the search box supports filtering. When a field is selected, the list prioritizes that field's upstream and downstream edges and highlights them. This approach does not rely on React Flow edge focusing (avoiding reworked edge interactions), and the hover toolbar remains unchanged.

### R17 AI Drawer UX (P1)

1. **Stop button**: in the `sending` state the send button becomes "Stop"; clicking it calls `abortRef.current.abort()`; the existing abort logic is retained;
2. **Soft interrupt on close**: the drawer's `onClose` first aborts the in-flight stream and then collapses (when a stream was in progress, explicitly tell the user "Stopped", not silently);
3. **Clear conversation**: add a "Clear conversation" button to the header (`ConfirmDialog` confirmation; clears `entries` and subsequent context); conversation history remains in memory (persistence deferred, §VI);
4. **Inline candidate confirmation card**: when the `suggest` event arrives, render a candidate list card below this round's answer bubble (reusing the `/ai/suggest/confirm|reject` endpoints and DetailPanel's existing candidate-card state/copy); the card has a "View on canvas" button (jumps to the seed field) — cards received by viewers are grayed out with a hint that editor is required (aligned with R8);
5. **Badge copy**: "Read-only tools" → "Queries are available in real time; write operations such as suggestions/drafts require editor" (update the ai dict for zh/en separately).

### R18 Toast Upgrade and Misc Bundle (P1)

1. **Toast**: remove `pointer-events-none` from the container; error-level toasts (`variant=error`) persist for ≥8s and have a close button and an action-button slot (retry); also keep a `role=alert` copy in the owning drawer for "toast-only errors" (rollback failures, etc.) (VersionDrawer already has a rollbackNotice area that can be reused);
2. **Stable onClose**: change all overlay toggles in `Workspace` to `useCallback` (as a fallback after R13's synchronization is complete);
3. Miscellaneous:
   - `UserManagementModal`: the user list's role badge now uses `roleLabel(user.role, t)` (readily available in `lib/roles.ts`);
   - `lib/api.ts`: delete the dead code `sendAiChat` (no callers); the Chinese semicolon used to join error details is changed to a locale-dependent separator;
   - `LoginPage`: per-field empty-value validation ("Please enter your username" / "Please enter your password", quoted separately);
   - `ImportWizardModal`: in step 2, if switching the format would discard selected files, show a `ConfirmDialog` for secondary confirmation;
   - `PreviewModal`: on small screens, move the "Copy locator" button into the footer (remove `hidden sm:flex`);
   - `HistoryDrawer`: when entries reach the 50-item cap, show the hint "Only the most recent 50 entries are shown";
   - `VersionDrawer`: wire the three write operations (create tag / diff / rollback) to `AbortController` so they abort on unmount.

## V. Explicitly Not Done / Deferred (This Round)

- **All P2 technical debt**: extracting z-index values into constants, a `focus-ring` component class, extracting group-collapse offsets / canvas-opacity magic numbers into constants, sidebar legend collapse on short screens, React Flow edge tooltip focus state — recorded in the backlog and paid down incrementally;
- **AI conversation persistence** (sessionStorage / server-side): deferred; the real-world cost of losing it on refresh is low;
- **LLM error-text whitelist noise reduction**, a navigation entry after draft accept, automatic version diff refresh, and [7.2 #7] cleanup of the legacy `GET /lineage/snapshot` endpoint;
- **Already tracked in 07**, not repeated: evaluation set, suggest semantic tuning, catalog-summary injection / history summarization, FTS5, multi-model fallback;
- **Multi-process distribution of SSE disconnects / external rate-limit storage**: explicitly not done in the single-machine form.

## VI. Document Synchronization Checklist (Required Within This Round's Scope)

| Document | Updates |
|---|---|
| This document (08) | §II status column, §VII verification record write-back |
| [05_API Interface Document](./05_api-reference.md) | §13: updated permission descriptions (role guardrails for write-type tools); 13.2 adds the current tool set and truncation notes; adds 13.6 `POST /ai/chat/stream` (including the `ping` heartbeat comment frame, cancellation semantics, 429) and 13.7–13.9 description draft endpoints; the endpoint summary table adds 33–36; Appendix A8's tool list adds the 4 M5 tools and role constraints |
| [03_Backend Development Document](./03_backend-development.md) | §8: run_tool role guardrails, truncation/pruning, heartbeat and stop-on-disconnect, the `ai/ratelimit.py` module, draft lang parameter; test commands unchanged (new R8–R12 scenario notes) |
| [02_Frontend Development Document](./02_frontend-development.md) | §6 component list: add `ModalShell` / `lib/useOverlayBehavior.ts`; §4 authentication and global state / overlay description section: Esc top-of-stack protocol, focus trap/restore, and body lock unified as foundation behavior |
| [01_Architecture Design](./01_architecture.md) | §3.4 AI chat sequence diagram and copy updates (role guardrails, truncation, heartbeat/disconnect, rate limiting); §2.2 module table AI row current-state correction (LangChain client / 8 tools / new `ai/ratelimit.py`) plus a "2026-10-26 current-state record" note; §2.3 frontend top-level organization adds a row for the overlay foundation |
| [04_hifi/02_Lineage Canvas Workspace](../04_hifi/02_lineage-canvas-workspace.md) | Add "2026-10-26 review increment" at the end: TopBar responsive degradation rules, canvas empty-state/filter hint/mobile hint, edge list secondary entry point, hops radiogroup |
| [04_hifi/04_AI Assistant](../04_hifi/04_ai-assistant.md) | Add "2026-10-26 review increment" at the end: send/stop toggle key, clear conversation, inline candidate card, badge copy, SSE `ping` frames transparent to the frontend |

## VII. Verification Record (Written Back 2026-10-26)

**Command-level verification (all passed):**

- Backend: `cd backend && uv run pytest` → **68 passed**. R8–R12 add 9 regressions: viewer rejection for `suggest_lineage` / `draft_descriptions` ×2 (asserting zero writes), `_drive` stop-on-disconnect (no further LLM calls after interruption), SSE `: ping` heartbeat comment frame, tool result truncation, context-budget whole-block pruning, chat rate limiting 429 + `Retry-After`, suggestion rate limiting 429, and draft prompt following `lang=en`;
- Frontend: `npm run typecheck && npm run build` → passed. The three change batches (R13, R14–R16, R17–R18) each passed twice, and the merged review passed after all were complete; 4 new files were added (`ModalShell.tsx`, `useOverlayBehavior.ts`, `ratelimit.py`, this document), not committed through the AGENTS.md process (uncommitted, pending user confirmation);
- MCP smoke test: the MCP tool-name cases in `test_m5_api.py` pass with the regression — the 5 read-only query tools are unaffected by R8 (MCP does not expose write-type tools).

**Runtime smoke testing (partially complete; the rest left to manual testing):**

- Started the backend + seed_demo + Vite dev with a temporary `DATA_DIR` and environment-variable overrides of `.env` (LLM left empty to ensure determinism); tested in an embedded browser at 900×800: login page rendering, the language toggle button, and `role=alert` error feedback on login failure all work correctly;
- **Workspace interactions could not be completed in this session**: the embedded browser sandbox does not honor synthetic pointer/keyboard events or page script injection (typed characters reach the page, but Tab/Enter/click/evaluate cannot reach the React app), which is not an application defect. Manual checklist items 1–8 in §VII are left for human execution (estimated 15 minutes).

**Implementation deviation record (increments relative to the §III/§IV contracts, all verified):**

1. R13: `useOverlayBehavior` adds an optional `initialFocusRef` (faithfully subsuming each overlay's initial focus target); `ModalShell` adds a required `titleId` prop (`aria-labelledby` keeps pointing at a real element); ConfirmDialog takes over entirely through the `header` slot (the alertdialog layout is incompatible with the standard header); three unified ≤2px tweaks including the close button style; in the AI drawer's unconfigured state, initial focus now lands on the container's first focusable element.
2. R15: after a hops switch, the old graph keeps its current position and the new subgraph is rearranged once when it arrives (the original "snap back first, then swap graphs" sequence is replaced by memoization semantics); `DatasetNode` gains `memo`; `LineageEdge` gains an optional `derivedLinkKey` field (table lookup for aggregate-line tracking hits).
3. R16: the edge list is collapsed by default (the bottom Controls remain at the lower left; the expanded body covers about 340px; the collapsed state is a permanently visible pill), and the hover toolbar behavior is unchanged.
4. R17: the drawer gains an `onRefresh` prop (reusing the silent `refreshGraph` refresh channel; confirm/reject scenarios do not reuse `onSuggested`, which shows a toast); fixed the existing conditional defect where `sending` did not reset after abort (`abortRef.current === controller`); `Icon` gains a `stop` icon.
5. R18: toast height `h-10` → `min-h-10 py-2` (to accommodate the close button and multi-line copy); `i18n/index.tsx` exports `getStaticLocale()` for api.ts to choose the error separator.
6. R11: the dependency function returned by the rate-limit dependency factory carries an attached `reset()` (a function-object attachment) for isolated test counters; thresholds are 10/6 requests per 60s [TBD-OPS: adjust based on usage].
