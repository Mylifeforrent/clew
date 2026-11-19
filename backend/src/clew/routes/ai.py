"""M4/M5 AI API: status, chat (function calling, including SSE streaming), lineage suggestions and description drafts.

Permissions: ``/ai/status``, ``/ai/chat*`` and ``GET /ai/description-drafts``
are viewer+; ``/ai/suggest``, ``confirm``, ``reject`` and draft accept/reject
are editor+ (AI suggestions never take effect directly, and description drafts
must be accepted manually). Write-type tools re-check the caller's role in the
tool layer (doc 08 R8). Chat requests use an in-memory sliding-window rate
limit (doc 08 R11): exceeding it returns 429.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from ..ai import descriptions, llm, suggest
from ..ai.chat import ChatInterrupted, run_chat, stream_run_chat
from ..ai.ratelimit import (SUGGEST_MAX_REQUESTS, SUGGEST_WINDOW_SECONDS,
                            CHAT_MAX_REQUESTS, CHAT_WINDOW_SECONDS, ai_limiter)
from ..config import get_settings
from ..db import get_db
from ..models import AiChatIn, AiEdgeKeyIn, AiSuggestIn
from ..security import require_role

router = APIRouter(tags=["ai"])

# Rate-limit dependencies for the chat and suggest routes (module-level
# instances; tests can call reset() to clear the counters)
ai_chat_limiter = ai_limiter(CHAT_WINDOW_SECONDS, CHAT_MAX_REQUESTS,
                             role="viewer")
ai_suggest_limiter = ai_limiter(SUGGEST_WINDOW_SECONDS, SUGGEST_MAX_REQUESTS,
                                role="editor")

# SSE idle-gap heartbeat interval (doc 08 R9: prevents reverse proxies from
# cutting silent connections; tests may monkeypatch it)
PING_INTERVAL_SECONDS = 15.0


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _edge_key(body: AiEdgeKeyIn) -> tuple[str, str | None, str, str | None]:
    from_dataset = body.from_dataset.strip()
    to_dataset = body.to_dataset.strip()
    if not from_dataset or not to_dataset:
        raise HTTPException(400, "from_dataset / to_dataset are required")
    from_field = _clean_optional(body.from_field)
    to_field = _clean_optional(body.to_field)
    if bool(from_field) != bool(to_field):
        raise HTTPException(
            400, "Lineage edges must provide both upstream and downstream fields"
                 " (field-level) or neither (table-level)")
    return from_dataset, from_field, to_dataset, to_field


@router.get("/ai/status")
def ai_status(user: dict = Depends(require_role("viewer"))):
    """Return whether the LLM is configured and the current model name (never return the key)."""
    settings = get_settings()
    configured = llm.is_configured(settings)
    return {
        "configured": configured,
        "model": settings.llm_model.strip() if configured else None,
    }


@router.post("/ai/chat")
def ai_chat(body: AiChatIn, user: dict = Depends(ai_chat_limiter)):
    """Natural-language chat: the model calls tools via function calling and can
    drive graph rendering/highlighting/suggestions.

    Write-type tools (suggest_lineage / draft_descriptions) validate the caller's
    role (R8).
    """
    focus = body.focus.model_dump() if body.focus is not None else None
    try:
        return run_chat([message.model_dump() for message in body.messages],
                        focus, actor=user["username"], role=user["role"])
    except llm.LLMNotConfigured as exc:
        raise HTTPException(503, str(exc)) from None
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc)) from None


@router.post("/ai/chat/stream")
def ai_chat_stream(body: AiChatIn, user: dict = Depends(ai_chat_limiter)):
    """SSE streaming chat (evolution plan 07 §4.3; disconnect-stops and heartbeat per doc 08 R9).

    Events: ``token`` (incremental text) / ``tool`` (tool trace) / ``suggest``
    (candidates persisted) / ``drafts`` (description drafts) / ``done`` (full
    payload) / ``error``. Orchestration runs in a background thread (tools are
    synchronous calls), and events go through a queue so the generator can emit
    them in real time; when events are idle beyond ``PING_INTERVAL_SECONDS``, a
    comment frame `: ping` heartbeat is emitted; when the client disconnects
    (the generator is closed), a cancel flag is set so tool rounds that have not
    started yet (including write-type tool persistence) are not executed.
    """
    focus = body.focus.model_dump() if body.focus is not None else None
    messages = [message.model_dump() for message in body.messages]
    username = user["username"]
    role = user["role"]

    def event_stream():
        import threading
        import time

        pending: list[dict] = []
        cancelled = threading.Event()
        finished: dict = {"payload": None, "error": None}

        def on_event(event: dict) -> None:
            pending.append(event)

        def worker() -> None:
            try:
                finished["payload"] = stream_run_chat(
                    messages, focus, username, role, on_event,
                    should_interrupt=cancelled.is_set)
            except ChatInterrupted:
                pass  # Client already disconnected: converge silently, emit no further events
            except llm.LLMNotConfigured as exc:
                finished["error"] = ("503", str(exc))
            except llm.LLMError as exc:
                finished["error"] = ("502", str(exc))
            except Exception as exc:  # Orchestration fallback: never break the stream silently
                finished["error"] = ("500", str(exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        last_output = time.monotonic()
        try:
            while thread.is_alive():
                if pending:
                    while pending:
                        yield _sse(pending.pop(0))
                        last_output = time.monotonic()
                    continue
                if time.monotonic() - last_output >= PING_INTERVAL_SECONDS:
                    yield ": ping\n\n"
                    last_output = time.monotonic()
                time.sleep(0.02)
            while pending:
                yield _sse(pending.pop(0))
        finally:
            # Client disconnected (GeneratorExit) or the stream ended normally:
            # set the cancel flag (R9)
            cancelled.set()

        if finished["error"] is not None:
            status, detail = finished["error"]
            yield _sse({"type": "error", "status": status, "detail": detail})
            return
        payload = finished["payload"]
        if payload is None:
            return  # Cancelled or converged silently: no deliverable payload
        yield _sse({"type": "done",
                    "answer": payload["answer"],
                    "graph": payload.get("graph"),
                    "highlights": payload.get("highlights"),
                    "suggestions": payload.get("suggestions"),
                    "drafts": payload.get("drafts"),
                    "tool_trace": payload["tool_trace"]})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(event: dict) -> str:
    event_type = event.get("type", "message")
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/ai/description-drafts")
def ai_drafts_list(dataset: str | None = None, status: str | None = None,
                   user: dict = Depends(require_role("viewer"))):
    """List description drafts (optionally filtered by dataset / status)."""
    if status is not None and status not in ("pending", "accepted", "rejected"):
        raise HTTPException(400, "status allows only pending/accepted/rejected")
    with get_db() as conn:
        items = descriptions.list_drafts(conn, dataset, status)
    return {"items": items}


@router.post("/ai/description-drafts/{draft_id}/accept")
def ai_draft_accept(draft_id: int, user: dict = Depends(require_role("editor"))):
    """Accept a description draft: write an annotation (append-only) + set accepted."""
    with get_db() as conn:
        try:
            item = descriptions.accept_draft(conn, draft_id, user["username"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except descriptions.DescriptionError as exc:
            raise HTTPException(409, str(exc)) from None
    return {"draft": item}


@router.post("/ai/description-drafts/{draft_id}/reject")
def ai_draft_reject(draft_id: int, user: dict = Depends(require_role("editor"))):
    """Reject a description draft: set rejected so the field is not generated again."""
    with get_db() as conn:
        try:
            descriptions.reject_draft(conn, draft_id, user["username"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
        except descriptions.DescriptionError as exc:
            raise HTTPException(409, str(exc)) from None
    return Response(status_code=204)


@router.post("/ai/suggest")
def ai_suggest(body: AiSuggestIn,
               user: dict = Depends(ai_suggest_limiter)):
    """Generate candidate edges heuristically from same-named fields/containment (source='ai') and persist them."""
    dataset = body.dataset.strip()
    if not dataset:
        raise HTTPException(400, "dataset cannot be empty")
    field = _clean_optional(body.field)
    with get_db() as conn:
        try:
            candidates = suggest.suggest_edges(
                conn, dataset, field, user["username"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
    return {"candidates": candidates}


@router.post("/ai/suggest/confirm")
def ai_suggest_confirm(body: AiEdgeKeyIn,
                       user: dict = Depends(require_role("editor"))):
    """Manually confirm an AI suggestion: change source to manual and write change_log(updated)."""
    key = _edge_key(body)
    with get_db() as conn:
        try:
            edge = suggest.confirm_suggestion(conn, *key, user["username"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
    return {"edge": edge}


@router.post("/ai/suggest/reject", status_code=204)
def ai_suggest_reject(body: AiEdgeKeyIn,
                      user: dict = Depends(require_role("editor"))):
    """Reject an AI suggestion: delete the ai edge and write change_log(deleted)."""
    key = _edge_key(body)
    with get_db() as conn:
        try:
            suggest.reject_suggestion(conn, *key, user["username"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None
    return Response(status_code=204)
