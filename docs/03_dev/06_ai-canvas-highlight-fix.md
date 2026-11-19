# 06 · Canvas-Linked Highlighting for AI Answers (Fix Document)

> Status: implemented and verified (validated in the prototype first → synced to the official `backend/` and `frontend/`). Date: 2026-10-24.
> Related: [02_Frontend Development Document](./02_frontend-development.md) §7.3 "Field tracking chain" and §7.6 "AI graph linkage"; [05_API Interface Document](./05_api-reference.md) §13.2; [03_Backend Development Document](./03_backend-development.md) §8.2/§8.4.

## I. Problem

The user asked a question in the AI assistant drawer:

> "For the amount field in orders, which tables correspond upstream and downstream? Highlight the corresponding results for me."

The AI correctly called tools and returned a subgraph (the canvas switched to the corresponding scope), and wrote "highlighted results" in the answer body — but **nothing was highlighted on the canvas**.

Meanwhile, the AI assistant drawer's empty-state copy had long promised that "the canvas will automatically switch and highlight when a subgraph is returned", but the "highlight" part had never been implemented.

## II. Root Cause

1. **The backend contract had no highlight channel**: `POST /ai/chat` returned only `{answer, tool_trace, graph?}` (`run_chat` in `ai/chat.py`). Although the `trace_lineage` tool knew which fields were queried, that information was discarded when assembling the response, so the frontend had no way to know "which fields this answer focuses on".
2. **The tool set had no means to declare highlights**: the model could only call 4 query-type tools and could not convey "which fields to mark" to the frontend; it could only write it into the markdown body (the frontend does not parse the body).
3. **The frontend had no consumption point**: `Workspace.handleAiGraph` only did `setAiGraph + applyGraph` (canvas subgraph switching); `LineageCanvas`'s field tracking highlight (`focusFields`) could only be triggered by clicking a field row, and the AI path was not wired in at all.

## III. Fix Approach

### 3.1 Backend: New `mark_highlight` Tool + `highlights` Response Field

**New tool `mark_highlight`** (`ai/tools.py`, read-only, returns no business data):

- Parameters: `{ fields: [{dataset, field}, ...] }`, at most `MAX_HIGHLIGHT_FIELDS = 8`;
- Behavior: validate field existence item by item (SELECT) and deduplicate; nonexistent items are recorded in `ignored` and returned to the model; when **all items are nonexistent**, throw `ToolError` so the model can self-correct (the conversation is not interrupted);
- Purpose: a canvas linkage signal — the model uses it to "declare" the fields this answer focuses on that should be highlighted on the frontend canvas with a red tracking chain.

**system prompt** (`ai/chat.py`) additions: `mark_highlight` is added to the tool list, and rule 4 is added to the answer rules — when the user asks to "highlight/mark/call out" results, or when the answer revolves around the upstream/downstream of certain fields, **call `mark_highlight` before giving the final answer**.

**Response contract**: `run_chat` aggregates all `mark_highlight` calls in the current round (deduplicated across calls, capped at 8) and returns the following when non-empty:

```json
{
  "answer": "...",
  "tool_trace": [ { "tool": "mark_highlight", "args": {...}, "ok": true }, ... ],
  "graph": { ... },
  "highlights": [ { "dataset": "d0", "field": "amount" }, ... ]
}
```

`highlights` is an **optional key** — it is not sent when the model does not call the tool, and older frontends can simply ignore it, preserving backward compatibility.

### 3.2 Frontend: AI Declaration → Canvas Tracking Chain

Reusing the existing field tracking highlight implementation ([02_Frontend Development Document](./02_frontend-development.md) §7.3), the trigger source is extended from "clicking a field row" to "AI declaration":

| Step | Change |
|---|---|
| `lib/fieldChain.ts` | The focus parameter of `computeFieldChain` changes from a single field to a **field array** (undirected BFS with multiple starting points), with starting points role='focus' and traversed nodes role='linked' |
| `types.ts` | Add `AiHighlightItem {dataset, field}`; add optional `highlights` to `AiChatResponse` |
| `AiAssistantDrawer` | The `onGraph` signature is extended to `(graph: LineageGraph \| null, highlights?: AiHighlightItem[])`; invoke the callback when the response carries `graph` or `highlights`; add `mark_highlight: 'Mark highlight'` to the tool-trace label table |
| `Workspace` | Add `aiFieldFocus` state `{seq, fields}[]` (seq distinguishes each answer round); `handleAiGraph` updates it on every answer round — applies it when `highlights` is present and explicitly clears it when absent; clears it when the dataset/hop count is switched or on refresh; passes it through to the canvas |
| `LineageCanvas` | Focus state `focusedField (single)` → `focusFields (array)`; add an `aiFocusFields` prop; an effect validates field existence by seq → reuses `revealChainFields` to automatically expand collapsed tables/field lists involved in the chain → applies them as tracking focus; `DatasetNode` data changes to `focusedFieldNames[]` |

**Effect**: identical to clicking a field — edges on the matching chain turn red (`#DC2626`), thicken, and animate; other connections are dimmed to opacity 0.15; the focused field row is strong red, chain field rows are light red, and handles are red.

**Clear/override timing** (consistent with click tracking, plus two AI-specific rules):

- Clicking blank canvas (`onPaneClick`), clicking a connection, box-selecting nodes, switching the seed/hop count, or focus field invalidation after subgraph refresh — same as the click path;
- **A new AI answer that declares no `highlights`** → explicitly clear the previous round's tracking state (the incrementing seq ensures every answer round is registered by the canvas, so old highlights do not linger);
- AI-declared fields not in the current subgraph (e.g., the model marked fields outside the subgraph) → skipped after per-item validation; if all are invalid, nothing is highlighted and nothing is dimmed.

## IV. Change List

| Side | File | Change |
|---|---|---|
| Backend | `src/clew/ai/tools.py` | `MAX_HIGHLIGHT_FIELDS=8`; `mark_highlight` schema + implementation + registration |
| Backend | `src/clew/ai/chat.py` | system prompt adds the tool and rule 4; `run_chat` aggregates `highlights` |
| Backend | `tests/test_m4_api.py` | Tool set assertion 4→5; 2 new regression tests (partially invalid fields deduplicated and ignored / all invalid returns a tool error) |
| Frontend | `src/types.ts` | `AiHighlightItem`; `AiChatResponse.highlights?` |
| Frontend | `src/lib/fieldChain.ts` | `computeFieldChain` supports multiple starting points |
| Frontend | `src/components/AiAssistantDrawer.tsx` | `onGraph` extension, `TOOL_LABELS` addition, response callback conditions |
| Frontend | `src/components/Workspace.tsx` | `aiFieldFocus` state and lifecycle, pass-through |
| Frontend | `src/components/LineageCanvas.tsx` | Focus converted to an array, `aiFocusFields` wired in, `revealChainFields` extracted and reused |
| Frontend | `src/components/DatasetNode.tsx` | `focusedFieldNames: string[]` |

The prototype and the official `backend/`/`frontend/` are synced from the same source (the official `Workspace.tsx`/`types.ts` contain pre-existing import-wizard code and were merged manually; everything else was copied wholesale).

## V. Verification Record

| Item | Result |
|---|---|
| `pytest` (prototype/backend) | 56 passed (including 2 new mark_highlight regression tests) |
| `pytest` (backend) | 57 passed |
| `npm run build` (both frontends) | tsc + vite passed |
| API: asking "amount upstream/downstream... highlight" | `highlights` returns 5 `{dataset, field}` items; `tool_trace` includes `mark_highlight ok=true` |
| prototype UI (5175 + prototype backend) | The canvas switches to a 5-dataset subgraph; the amount rows of d0–d4 are all tracked in red, the chain (same-name field matching inferred lines) flows in red, and other connections are dimmed |
| Official UI (5176 + backend) | Same as above; a "Mark highlight ✓" chip appears on the tool-trace card |
| Clicking blank space clears; a new question without declared highlights clears | Passed |

> Note: during development, a one-off dirty state of "canvas has nodes but no edges" was observed on an old page after a Vite HMR hot update; it did not reproduce after a full page refresh and is unrelated to product code.

## VI. Known Limitations

- `highlights` depends on the model following the system prompt to call `mark_highlight` before answering; if the model does not call it, that round falls back to "switch the graph only, no highlighting" (same behavior as before the fix) without raising an error.
- Highlighting propagates along "field-level edges within the database + same-name field matching inferred lines" (§7.3 definition); if both ends of a link have only table-level edges and no same-name fields, that segment will not appear in the red chain.
