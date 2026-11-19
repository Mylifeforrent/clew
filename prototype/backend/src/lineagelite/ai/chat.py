"""AI chat orchestration: OpenAI-compatible function calling loop (at most 5 tool rounds).

Flow:
1. A fixed system prompt (with optional focus context) + the conversation history sent by the frontend;
2. Call ``llm.complete(messages, tools)``; when the model returns tool_calls, execute each tool,
   append the results as role=tool messages, and continue to the next round;
3. When the model requests no more tools, take that message's content as the final answer;
4. If 5 consecutive rounds all call tools, send one more request without tools to force closure
   (guaranteeing a bounded loop).

``tool_trace`` records ``{tool, args, ok}`` for every tool call; ``graph`` takes the GraphPayload
returned by the last graph-query tool (trace_lineage) for the frontend canvas to render;
``highlights`` aggregates fields declared by mark_highlight (the canvas red trace-chain signal);
``suggestions``/``drafts`` are new in M5 (suggest_lineage candidates, description drafts).

Streaming: ``stream_run_chat`` reuses the same orchestration, only replacing the model call with
``llm.stream_complete`` (per-token callback) and emitting tool-round events to the SSE route in
real time via ``on_event``.
"""

from __future__ import annotations

import json
from typing import Callable

from ..config import get_settings
from ..db import get_db
from . import llm
from .tools import MAX_HIGHLIGHT_FIELDS, TOOL_SCHEMAS, run_tool

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """You are the assistant of LineageLite, a lightweight AI data lineage tool.

You can call tools to query dataset fields, source-file locators, upstream/downstream lineage and change history:
- search_fields: locate fields by keyword;
- get_field_details: field details, source-file locator and source preview;
- trace_lineage: trace the upstream/downstream N-hop subgraph by dataset/field;
- get_field_history: change history of a field;
- mark_highlight: declare fields to highlight as a red trace chain on the canvas (a canvas signal; returns no data);
- suggest_lineage: run lineage suggestions for a dataset/field; candidate edges are persisted and shown on the canvas (effective only after the user confirms manually);
- analyze_impact: analyze the downstream impact surface of a field (downstream fields, source files, recent changes);
- draft_descriptions: generate description drafts for fields missing descriptions (they become annotations only after the user accepts).

Answering rules:
1. Base every answer on data returned by the tools; never invent datasets, fields, edges or file locations;
   when nothing is found, say "not found" explicitly and suggest a next step.
2. If the user asks in Chinese, answer in Chinese; when lineage is involved, state the direction, hops and confidence;
   when source traceability is involved, give the file name and locator (sheet/column/JSONPath).
3. You have no permission to modify business data directly: lineage candidates must be confirmed by the user and
   description drafts must be accepted by the user; do not claim to have modified any official data.
4. When the user asks to "highlight/mark/point out" results, or the answer revolves around the upstream/downstream
   of some fields, call mark_highlight before giving the final answer, passing the fields this answer focuses on
   (at most 8); those fields are highlighted as a red trace chain on the canvas.
5. Write fields in answers as `dataset.field` where possible (e.g. d0.amount); the frontend renders them as
   clickable evidence anchors."""


def _system_prompt(focus: dict | None) -> str:
    lines = [SYSTEM_PROMPT]
    if focus:
        dataset = str(focus.get("dataset") or "").strip()
        field = str(focus.get("field") or "").strip()
        if dataset:
            scope = f'Dataset "{dataset}"'
            if field:
                scope += f' field "{field}"'
            lines.append(f"The current user is focused on {scope}; prefer answering within that scope.")
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


def _drive(messages: list[dict], focus: dict | None, actor: str,
           complete_fn: Callable, on_event: Callable[[dict], None] | None) -> dict:
    """Function calling main loop; ``complete_fn`` can be replaced by a streaming implementation."""
    conversation: list[dict] = [
        {"role": "system", "content": _system_prompt(focus)},
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

    while True:
        # The 6th request (rounds == 5) no longer provides tools, forcing the model to give the final answer
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
                        result = run_tool(conn, name, args, actor=actor)
                    ok = True
                except Exception as exc:  # Tool errors are returned to the model without aborting the whole conversation
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
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

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
             actor: str = "system") -> dict:
    """Run one AI chat turn (non-streaming) and return the orchestration payload.

    ``messages`` has already been validated by the route layer as ``[{role, content}]``
    (role is user/assistant only). Missing LLM configuration raises
    :class:`llm.LLMNotConfigured`; upstream HTTP/structure errors raise
    :class:`llm.LLMError`.
    """
    if not llm.is_configured(get_settings()):
        raise llm.LLMNotConfigured(llm.NOT_CONFIGURED_MESSAGE)
    return _drive(messages, focus, actor, llm.complete, None)


def stream_run_chat(messages: list[dict], focus: dict | None, actor: str,
                    on_event: Callable[[dict], None]) -> dict:
    """Streaming orchestration: the final answer calls back token by token via ``llm.stream_complete``; the rest is identical.

    Returns the complete payload (including answer/graph/highlights/suggestions/drafts).
    """
    if not llm.is_configured(get_settings()):
        raise llm.LLMNotConfigured(llm.NOT_CONFIGURED_MESSAGE)

    def complete_fn(conversation: list[dict], tools) -> dict:
        return llm.stream_complete(
            conversation, tools,
            on_delta=lambda delta: on_event({"type": "token", "delta": delta}))

    return _drive(messages, focus, actor, complete_fn, on_event)
