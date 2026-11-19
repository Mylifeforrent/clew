"""AI chat orchestration: OpenAI-compatible function calling loop (at most 5 tool rounds).

Flow:
1. A fixed system prompt (with optional focus context and write-tool role notes)
   + the conversation history sent by the frontend;
2. Call ``llm.complete(messages, tools)``; when the model returns tool_calls,
   execute each tool, append the results as role=tool messages, and continue to
   the next round;
3. When the model no longer requests tools, take that message's content as the
   final answer;
4. If 5 consecutive rounds all call tools, send one more request without tools
   to force a conclusion (guaranteeing the loop is bounded).

``tool_trace`` records ``{tool, args, ok}`` for every tool call; ``graph`` takes
the GraphPayload returned by the last graph-query tool (trace_lineage), for the
frontend canvas to render; ``highlights`` aggregates the fields declared by
mark_highlight (canvas red tracing-chain signal); ``suggestions``/``drafts``
are new in M5 (suggest_lineage candidates, description drafts).

Streaming: ``stream_run_chat`` reuses the same orchestration, only swapping the
model call for ``llm.stream_complete`` (per-token callback) and emitting tool
round events to the SSE route in real time via ``on_event``.

Doc 08 fixes (2026-10-26):

- R8 write-tool role guard: the caller's ``role`` is mandatory; when a viewer
  triggers suggest_lineage / draft_descriptions, ``run_tool`` raises ToolError
  (no DB write);
- R9 disconnect-stops: ``should_interrupt`` is checked at the start of every
  round and before every tool call; once set, :class:`ChatInterrupted` is raised
  and unexecuted rounds and write operations no longer proceed;
- R10 context budget: tool results are truncated before being appended
  (``MAX_TOOL_RESULT_CHARS``); after each round is appended, the oldest rounds
  are trimmed as a whole block according to the token budget
  (``CONTEXT_TOKEN_BUDGET``, overridable via ``LLM_CONTEXT_TOKEN_BUDGET`` in
  ``.env``).
"""

from __future__ import annotations

import json
from typing import Callable

from ..config import get_settings
from ..db import get_db
from ..security import ROLE_ORDER
from . import llm
from .tools import MAX_HIGHLIGHT_FIELDS, TOOL_SCHEMAS, run_tool

MAX_TOOL_ROUNDS = 5
# R10: character cap of the tool result text visible to the model (graph/highlights extraction happens before truncation)
MAX_TOOL_RESULT_CHARS = 4000
DEFAULT_CONTEXT_TOKEN_BUDGET = 96_000


class ChatInterrupted(Exception):
    """The client has disconnected: orchestrate an orderly convergence (R9); unstarted rounds and write operations no longer execute."""


SYSTEM_PROMPT = """You are the assistant for Clew (a field-level AI data lineage tool).

You can call tools to query dataset fields, source-file locators, upstream/downstream lineage and change history:
- search_fields: locate fields by keyword;
- get_field_details: field details, source-file locator and source preview;
- trace_lineage: trace the N-hop upstream/downstream subgraph by dataset/field;
- get_field_history: the field's change history;
- mark_highlight: declare fields to highlight with orange tracing on the canvas (a canvas-linking signal; returns no data);
- suggest_lineage: run lineage suggestions for a dataset/field; candidate edges are persisted and appear on the canvas (effective only after the user confirms them manually);
- analyze_impact: analyze a field's downstream impact surface (downstream fields, source files, recent changes);
- draft_descriptions: generate description drafts for fields missing descriptions (become annotations only after user acceptance).

Answering rules:
1. You must answer based on data returned by tools; never fabricate datasets, fields, edges or file locations;
   when nothing is found, clearly say "not found" and give the next-step suggestion.
2. Answer in Chinese when the user asks in Chinese, and in English when the user asks in English; when lineage is involved, state the direction, hop count and confidence;
   when source tracing is involved, give the file name and locator (sheet/column/JSONPath).
3. You have no permission to directly modify business data: lineage candidates must be confirmed by the user and description drafts must be
   accepted by the user; do not claim you have modified any formal data.
4. When the user asks to "highlight/mark/point out" results, or the answer revolves around the upstream/downstream of certain fields,
   call mark_highlight before giving the final answer, passing the fields this answer focuses on
   (at most 8); these fields will be highlighted with an orange tracing chain on the canvas.
5. Write fields in answers as `dataset.field` where possible (e.g. d0.amount); the frontend renders them as
   clickable evidence anchors.
6. The answer language must match the language of the user's latest question: answer English questions in English and
   Chinese questions in Chinese; never default to Chinese just because this system prompt is in English."""

VIEWER_TOOL_PROMPT = (
    "7. The current chat user has the viewer role: the write-type tools suggest_lineage / draft_descriptions"
    " are unavailable to you (rejected by the role guard). When the user asks to \"add lineage/generate"
    " description suggestions\", explain that this operation requires an editor account in the canvas"
    " detail panel, and do not retry these two tools repeatedly.")


def _system_prompt(focus: dict | None, role: str = "editor") -> str:
    lines = [SYSTEM_PROMPT]
    if ROLE_ORDER.get(role, -1) < ROLE_ORDER["editor"]:
        lines.append(VIEWER_TOOL_PROMPT)
    if focus:
        dataset = str(focus.get("dataset") or "").strip()
        field = str(focus.get("field") or "").strip()
        if dataset:
            scope = f"dataset \"{dataset}\""
            if field:
                scope += f" field \"{field}\""
            lines.append(
                f"The current user is focused on {scope};"
                " prioritize answering within that scope.")
    return "\n\n".join(lines)


def _response_message(response: dict) -> dict:
    if not isinstance(response, dict):
        raise llm.LLMError("LLM response is not a JSON object")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise llm.LLMError("LLM response is missing choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise llm.LLMError("LLM response is missing message")
    return message


def _tool_calls(message: dict) -> list:
    calls = message.get("tool_calls")
    return calls if isinstance(calls, list) else []


def _content_text(content) -> str:
    """Tolerate provider differences where content is a string or [{type:text,text:...}]."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def _parse_arguments(raw) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Tool arguments are not valid JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return parsed
    raise ValueError("Tool arguments must be a JSON object")


def _is_graph_payload(value) -> bool:
    return (isinstance(value, dict)
            and isinstance(value.get("datasets"), list)
            and isinstance(value.get("edges"), list))


# ---------- R10: context budget ----------


def _estimate_tokens(text: str) -> float:
    """Rough token estimate: non-ASCII ≈ 1 token/char, ASCII ≈ 0.25 token/char."""
    if not text:
        return 0.0
    non_ascii = sum(1 for ch in text if ord(ch) > 0x7F)
    return non_ascii + (len(text) - non_ascii) / 4


def _conversation_tokens(conversation: list[dict]) -> float:
    """Estimated total tokens of the whole conversation (including tool_calls arguments)."""
    return sum(
        _estimate_tokens(json.dumps(message, ensure_ascii=False, default=str))
        for message in conversation)


def _context_budget() -> int:
    try:
        budget = int(get_settings().llm_context_token_budget)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TOKEN_BUDGET
    return budget if budget > 0 else DEFAULT_CONTEXT_TOKEN_BUDGET


def _trim_context(conversation: list[dict]) -> list[dict]:
    """When over budget, trim the oldest rounds as a whole block (in place).

    "A whole block" = all messages from index 1 up to (but excluding) the next
    user message — ensuring that after trimming the conversation still starts
    with a user message and that the system prompt and the current round are
    never deleted.
    """
    if len(conversation) <= 1:
        return conversation

    def user_starts() -> list[int]:
        return [i for i, message in enumerate(conversation)
                if i > 0 and message.get("role") == "user"]

    starts = user_starts()
    budget = _context_budget()
    while len(starts) > 1 and _conversation_tokens(conversation) > budget:
        del conversation[1:starts[1]]
        starts = user_starts()
    return conversation


def _truncate_tool_result(result: dict) -> str:
    """Serialize the tool result to JSON; if it exceeds ``MAX_TOOL_RESULT_CHARS``, truncate and append a marker.

    Only affects the text appended to the conversation for the model to read;
    graph/highlights/suggestions/drafts extraction happens before this function
    is called, so canvas linking is unaffected (doc 08 R10).
    """
    payload = json.dumps(result, ensure_ascii=False, default=str)
    if len(payload) <= MAX_TOOL_RESULT_CHARS:
        return payload
    return (payload[:MAX_TOOL_RESULT_CHARS]
            + f"...[tool result truncated: full data is {len(payload)}"
              " characters; only the leading part is returned here]")


def _drive(messages: list[dict], focus: dict | None, actor: str, role: str,
           complete_fn: Callable, on_event: Callable[[dict], None] | None,
           should_interrupt: Callable[[], bool] | None = None) -> dict:
    """Main function-calling loop; ``complete_fn`` may be replaced with a streaming implementation.

    ``role`` is the caller's role (passed with ``run_tool`` to write-type tools,
    doc 08 R8); when ``should_interrupt`` is set, :class:`ChatInterrupted` is
    raised (doc 08 R9).
    """
    conversation: list[dict] = [
        {"role": "system", "content": _system_prompt(focus, role)},
    ]
    for message in messages:
        conversation.append(
            {"role": message["role"], "content": message["content"]})

    tool_trace: list[dict] = []
    graph: dict | None = None
    highlights: list[dict] = []
    seen_highlights: set[tuple[str, str]] = set()
    suggestions: list[dict] = []
    drafts: list[dict] = []
    rounds = 0

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    def interrupted() -> bool:
        if should_interrupt is not None and should_interrupt():
            raise ChatInterrupted()
        return False

    while True:
        interrupted()
        # The 6th request (rounds == 5) no longer offers tools, forcing the model to give a final answer
        tools = TOOL_SCHEMAS if rounds < MAX_TOOL_ROUNDS else None
        response = complete_fn(conversation, tools)
        message = _response_message(response)
        calls = _tool_calls(message)

        if not calls or rounds >= MAX_TOOL_ROUNDS:
            answer = _content_text(message.get("content"))
            break

        conversation.append({
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": calls,
        })
        rounds += 1

        for call in calls:
            interrupted()
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict):
                function = {}
            name = function.get("name")
            name = name if isinstance(name, str) else ""
            call_id = call.get("id") if isinstance(call, dict) else None

            try:
                args = _parse_arguments(function.get("arguments"))
                parse_error = None
            except ValueError as exc:
                args = {}
                parse_error = str(exc)

            if parse_error is None:
                try:
                    with get_db() as conn:
                        result = run_tool(conn, name, args, actor=actor,
                                          role=role)
                    ok = True
                except Exception as exc:  # Tool errors are returned to the model; the whole conversation is not interrupted
                    result = {"error": str(exc) or exc.__class__.__name__}
                    ok = False
            else:
                result = {"error": parse_error}
                ok = False

            tool_trace.append({"tool": name, "args": args, "ok": ok})
            emit({"type": "tool", "tool": name, "args": args, "ok": ok})
            if ok and isinstance(result, dict):
                candidate = result.get("graph")
                if _is_graph_payload(candidate):
                    graph = candidate
                if name == "mark_highlight":
                    fields = result.get("fields")
                    if isinstance(fields, list):
                        for item in fields:
                            if not isinstance(item, dict):
                                continue
                            key = (str(item.get("dataset") or ""),
                                   str(item.get("field") or ""))
                            if key in seen_highlights or not all(key):
                                continue
                            seen_highlights.add(key)
                            highlights.append(
                                {"dataset": key[0], "field": key[1]})
                if name == "suggest_lineage":
                    candidates = result.get("candidates")
                    if isinstance(candidates, list) and candidates:
                        suggestions.extend(candidates)
                        emit({"type": "suggest", "count": len(candidates),
                              "candidates": candidates})
                if name == "draft_descriptions":
                    items = result.get("items")
                    if isinstance(items, list) and items:
                        drafts.extend(items)
                        emit({"type": "drafts", "items": items})
            conversation.append({
                "role": "tool",
                "tool_call_id": call_id or "",
                "content": _truncate_tool_result(result),
            })

        # After this round's tool results are appended, check the context budget;
        # over budget trims the oldest rounds as a whole block (R10)
        _trim_context(conversation)

    payload: dict = {"answer": answer, "tool_trace": tool_trace}
    if graph is not None:
        payload["graph"] = graph
    if highlights:
        payload["highlights"] = highlights[:MAX_HIGHLIGHT_FIELDS]
    if suggestions:
        payload["suggestions"] = suggestions
    if drafts:
        payload["drafts"] = drafts
    return payload


def run_chat(messages: list[dict], focus: dict | None = None,
             actor: str = "system", *, role: str) -> dict:
    """Run one AI chat round (non-streaming) and return the orchestration payload.

    ``messages`` has already been validated by the route layer as
    ``[{role, content}]`` (role is only user/assistant). ``role`` is mandatory
    (the caller's role, R8). An unconfigured LLM raises
    :class:`llm.LLMNotConfigured`; upstream HTTP/structure errors raise
    :class:`llm.LLMError`.
    """
    if not llm.is_configured(get_settings()):
        raise llm.LLMNotConfigured(llm.NOT_CONFIGURED_MESSAGE)
    return _drive(messages, focus, actor, role, llm.complete, None)


def stream_run_chat(messages: list[dict], focus: dict | None, actor: str,
                    role: str, on_event: Callable[[dict], None],
                    should_interrupt: Callable[[], bool] | None = None) -> dict:
    """Streaming orchestration: the final answer is token-callbacked via ``llm.stream_complete``; the rest is isomorphic.

    ``role`` is mandatory (the caller's role, R8); ``should_interrupt`` stops on
    disconnect (R9). Returns the full payload (including
    answer/graph/highlights/suggestions/drafts).
    """
    if not llm.is_configured(get_settings()):
        raise llm.LLMNotConfigured(llm.NOT_CONFIGURED_MESSAGE)

    def complete_fn(conversation: list[dict], tools) -> dict:
        return llm.stream_complete(
            conversation, tools,
            on_delta=lambda delta: on_event({"type": "token", "delta": delta}))

    return _drive(messages, focus, actor, role, complete_fn, on_event,
                  should_interrupt)
