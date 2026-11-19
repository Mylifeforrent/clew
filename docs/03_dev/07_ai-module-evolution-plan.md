# 07 · AI Module Evolution Plan (finalized 2026-10-24)

> Purpose: the evolution blueprint and confirmed decision record for the AI module, from a "conversational query tool" to a "governance copilot".
> Conclusion first: **choose LangChain, do not introduce LangGraph**; automatic description completion follows "draft → human confirmation → annotation"; expose an MCP server.
> Related: [06_ai-canvas-highlight-fix](./06_ai-canvas-highlight-fix.md) (previous fix round), [03_backend-development](./03_backend-development.md) §8, [02_frontend-development](./02_frontend-development.md) §7.

## 1. Background and Gap Assessment

The previous assessment (2026-10-24) confirmed three layers of gaps; this plan addresses each item:

1. **Experience layer**: `llm.py` is a synchronous blocking urllib client (60s timeout), so users wait blankly for 20–40s after asking — the first principle of industry agent chat is streaming feedback (LangChain "UX for Agents" and the stream interface of the OpenMetadata AI SDK both follow this);
2. **Capability layer**: it can only "query", not "change" — the in-conversation `suggest_lineage` planned in design plan §6.2 is not wired in; lineage suggestions have only two rules, same-name/containment (the "semantic similarity + LLM judgment" planned in design plan §6.4 is not done); description gaps have no AI-assisted completion; impact-analysis Q&A is missing;
3. **Engineering layer**: the hand-written urllib LLM client cannot switch providers, has no evaluation set, and exposes no tools externally.

External references: OpenMetadata 1.8 packages metadata/lineage as an **MCP server** for any agent to consume; Atlan's AI-generated descriptions have an adoption rate of about 70%, and Atlan treats column-level impact analysis as a core agent scenario; the Atlan AI Labs benchmark shows that catalog context can improve text-to-SQL accuracy by 38% relative (governance context is valuable, but text-to-SQL is beyond this product's boundary and is **explicitly out of scope**, see §5).

## 2. Confirmed Decisions (2026-10-24, approved by the user)

| # | Decision | Conclusion | Rationale |
|---|---|---|---|
| D1 | LLM access layer | **Upgrade to LangChain** (`ChatOpenAI` + `OpenAIEmbeddings` from `langchain-openai`), replacing the hand-written urllib client | Unified wrapper for two providers ("OpenAI / Alibaba Cloud DashScope compatible mode"; both use the OpenAI-compatible protocol and can be switched via `base_url`); future model/provider changes do not touch business code |
| D2 | Whether to introduce LangGraph | **No** | Current orchestration is a fixed 5-round function calling loop plus human confirmation through REST/canvas; there are no complex agent flows requiring a state machine, persistent checkpoints, or dynamic branching; LangGraph would add concepts and dependencies without corresponding benefit. Re-evaluate if "multi-step autonomous agents" (e.g. automatic inspection generating governance tasks) appear in the future |
| D3 | Persistence path for auto-completed descriptions | **Draft slot → human confirmation → annotation** | Add a `description_draft` table to hold AI drafts (leaving the original imported value in `field.description` untouched, consistent with the "separate original imports from human insight" invariant); the `annotation` (append-only) is written only after the user confirms adoption in the UI; rejected drafts are marked and not regenerated |
| D4 | MCP exposure | **Yes**, stdio transport | Expose query-type tools as an MCP server so external AIs such as Claude Desktop / Cursor can query lineage directly; the REST drawer route is unchanged and the two coexist |
| D5 | embedding provider | **Both OpenAI and Alibaba Cloud DashScope supported** (switched via the `OpenAIEmbeddings` base_url from D1) | When embeddings are not configured, the semantic layer **degrades gracefully** to pure heuristics without blocking other features [TBD-INFRA: the user must provide an embedding key; DeepSeek does not offer an embedding API] |

## 3. Evolution Items and Status

| # | Evolution item | Priority | Status | Notes |
|---|---|---|---|---|
| 1 | LangChain access layer (chat + embeddings) | P0 | ✅ this round | `ai/llm.py` rewritten: `complete()` keeps its original signature (compatible with existing callers/tests) and internally uses `ChatOpenAI.invoke`; adds `stream_chat()` (SSE aggregation) and `get_embeddings()` |
| 2 | Streaming chat `POST /ai/chat/stream` | P0 | ✅ this round | SSE events: `token` (incremental text) / `tool` (tool call trace) / `suggest` (candidate persistence count) / `drafts` (description drafts) / `done` / `error`; the frontend fetch reader renders incrementally |
| 3 | In-conversation `suggest_lineage` tool | P0 | ✅ this round | The model can proactively propose lineage: internally runs the existing heuristics (+ semantic layer, D5) and persists candidates with `source='ai'`, returning the candidate list; the frontend refreshes the canvas on the `suggest` event (blue dashed candidate edges), and confirm/reject still use the existing REST loop |
| 4 | Evidence anchors in answers | P0 | ✅ this round | `dataset.field` references in the answer text are rendered as clickable chips; clicking → canvas focus + field trace-chain highlight (reusing the `aiFieldFocus`/`computeFieldChain` channel) |
| 5 | Impact analysis tool `analyze_impact` | P1 | ✅ this round | Input field → recursive downstream + each downstream source file's verification status + recent change aggregation; the model uses this to produce an "impact report" |
| 6 | Auto description completion (D3 draft flow) | P1 | ✅ this round | Tool `draft_descriptions(dataset, fields?)`: the chat model generates at most 10 drafts into `description_draft` based on field name/type/upstream-downstream/same-name fields; REST: `GET /ai/description-drafts`, `POST …/{id}/accept` (writes an annotation + sets accepted), `POST …/{id}/reject`; the drawer renders confirmation cards |
| 7 | MCP server (D4) | P1 | ✅ this round | `ai/mcp_server.py` (stdio): `search_fields` / `get_field_details` / `trace_lineage` / `get_field_history` / `get_overview`; run with `uv run python -m clew.ai.mcp_server`; Claude Desktop / Cursor configuration is in §6 |
| 8 | Evaluation set (golden QA regression script) | P1 | ⬜ to do | 10–20 typical Q&A pairs + assertion points, run as a scripted benchmark; used for tuning before semantic suggestions |
| 9 | suggest semantic-layer tuning (once embeddings are available) | P1 | ⬜ to do | Threshold tuning (initial cos ≥ 0.75) + upstream/downstream proximity constraints + excluding existing edges (reusing the existing rules in suggest.py) |
| 10 | Context engineering (overview injection / history summarization) | P1 | ⬜ to do | Inject a dataset catalog summary into the system prompt; conversation summaries replacing 50 raw messages in long chats |
| 11 | FTS5 Chinese search | P2 | ⬜ | Evaluate once the field count reaches the thousands |
| 12 | Multi-model fallback (local ollama fallback) | P2 | ⬜ [TBD-INFRA] | With LangChain, only the env needs to change |

## 4. Technical Design

### 4.1 Provider Matrix (D1/D5)

| Provider | chat base_url | embedding base_url | Example model |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com` | — (no embedding API) | `deepseek-chat` |
| Alibaba Cloud DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | same as left | `qwen-plus`; embedding: `text-embedding-v3` |
| OpenAI | `https://api.openai.com/v1` | same as left | `gpt-4o-mini`; embedding: `text-embedding-3-small` |

New `.env` entries (all optional; empty = feature degraded):

```
EMBEDDING_BASE_URL=          # if empty, semantic suggestions degrade to pure heuristics
EMBEDDING_API_KEY=
EMBEDDING_MODEL=             # e.g. text-embedding-v3 / text-embedding-3-small
```

The chat side keeps using the existing `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`.

### 4.2 `ai/llm.py` Rewrite (D1)

- `get_chat_model()`: builds `ChatOpenAI(model, api_key, base_url, temperature=0, timeout=60)` from settings (singleton cached);
- `complete(messages, tools)`: **keeps its original signature** — internally converts OpenAI-format messages/tools into LangChain messages and `bind_tools`, then converts the `invoke` result back to a dict (the `{choices:[{message:{content, tool_calls}}]}` shape), so the existing `chat.py` orchestration and tests need zero changes;
- `stream_chat(messages, tools)`: `ChatOpenAI.stream` yields `AIMessageChunk` — when a chunk contains `tool_call_chunks`, no text is emitted (this round is a tool round) and the chunks are aggregated into a complete `AIMessage` to return; otherwise tokens are emitted one by one;
- `get_embeddings()`: returns `OpenAIEmbeddings` when `EMBEDDING_*` is configured in settings, otherwise `None` (callers degrade);
- `LLMNotConfigured / LLMError / endpoint_url` keep their semantics (`endpoint_url` is kept for compatibility; LangChain consumes base_url directly).

### 4.3 SSE Streaming Orchestration (evolution item 2)

`POST /ai/chat/stream` (viewer+) has the same request body as `/ai/chat` and responds with `text/event-stream`:

```
event: token     data: {"delta": "…"}            # final answer, token by token
event: tool      data: {"tool":"trace_lineage","args":{…},"ok":true,"round":1}
event: suggest   data: {"count": 3, "candidates":[…]}   # after suggest_lineage persists
event: drafts    data: {"items":[{id, dataset, field, draft}]}
event: done      data: {"highlights":[…], "graph":{…}|null}
event: error     data: {"detail": "…"}
```

The orchestration loop is isomorphic to the non-streaming one (5-round cap); the only difference is that the final answer round uses `stream_chat` to emit tokens one by one; `tool/suggest/drafts` events are emitted immediately during the loop. The non-streaming `/ai/chat` stays unchanged (MCP/script consumption).

### 4.4 Conversation Toolset (5 → 8 tools)

| Tool | Type | Description |
|---|---|---|
| `search_fields` / `get_field_details` / `trace_lineage` / `get_field_history` / `mark_highlight` | existing | See [03_backend-development](./03_backend-development.md) §8.2 |
| `suggest_lineage` | writes candidates (persisted with `source='ai'`, allowed by invariant #4) | Parameters `{dataset, field}`; internally runs `suggest.suggest_edges` (heuristics + semantic layer); returns the candidate list, and the frontend refreshes the canvas on the `suggest` event |
| `analyze_impact` | read-only | Parameters `{dataset, field, hops?}`; aggregates the downstream subgraph + each downstream field's source file verification status + recent changes (change_log), returning a structured impact surface |
| `draft_descriptions` | writes drafts (`description_draft` table, not business data) | Parameters `{dataset, fields? (≤10, defaults to all fields in that dataset that lack descriptions)}`; calls the chat model per field to generate a description draft (input includes type/current description/upstream and downstream edges/same-name fields), persisted as a pending draft |

### 4.5 Description Draft Flow (D3)

```
model calls draft_descriptions → description_draft(pending) → SSE drafts event
→ drawer renders a confirmation card (accept / reject)
→ accept: write annotation(target_kind='field', body=draft, author=current user) + set accepted
→ reject: set rejected (do not regenerate for the same field unless the field content changes)
```

DDL (`db.py init_db` increment, SQLite):

```sql
CREATE TABLE IF NOT EXISTS description_draft (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES dataset(id),
  field_name TEXT NOT NULL REFERENCES field(dataset_id, name) ON DELETE CASCADE ON UPDATE CASCADE,
  draft TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
  created_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE (dataset_id, field_name, status)
);
```

REST (all editor+; viewer can only read GET): `GET /ai/description-drafts?dataset=`, `POST /ai/description-drafts/{id}/accept`, `POST /ai/description-drafts/{id}/reject`.

### 4.6 MCP Server (D4)

- Transport: stdio; process: `uv run python -m clew.ai.mcp_server` (same database and configuration as the API);
- Exposed: `search_fields` / `get_field_details` / `trace_lineage` / `get_field_history` / `get_overview` (dataset list + field/edge statistics summary);
- **Read-only**: does not expose suggest/mark_highlight/draft write operations — external agents cannot trigger database writes (not even `source='ai'`);
- Integration example (Claude Desktop / Cursor MCP configuration):

```json
{ "mcpServers": { "lineagelite": {
    "command": "uv",
    "args": ["run", "--directory", "<repo>/prototype/backend", "python", "-m", "lineagelite.ai.mcp_server"] } } }
```

## 5. Explicitly Out of Scope

- **Text-to-SQL / natural-language querying**: this product has no database connections; out of scope;
- **Vector database**: storing vectors in SQLite + brute-force in-memory retrieval is sufficient for embedding recall;
- **AI autonomously writing business data**: any write must go through human confirmation (invariant #4); MCP exposes only read-only tools;
- **Multi-tenant memory / cross-user agent memory**: unnecessary for a single-machine, single-user product.

## 6. Milestone Mapping

- This round (M5-a): evolution items 1–7 (including landing decisions D1–D5); validation = both chat loops + MCP smoke test + regression tests;
- Next round (M5-b): evolution items 8–10 (eval, semantic tuning, context engineering).

Difference notes: `suggest_lineage` from design plan §6.2 only enters the conversation toolset in this round; `get_subgraph` is not provided separately (`trace_lineage` without a field is the subgraph, an equivalent capability); the `GET /search` REST endpoint is not created (search is used only by model tools and frontend local filtering).
