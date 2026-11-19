"""LLM access layer (M5: LangChain-based, evolution plan 07 §4.2).

In M4 this was a hand-written urllib client; from M5 it uniformly goes through LangChain:

- ``get_chat_model()``: ``ChatOpenAI`` (OpenAI / Alibaba DashScope compatible
  mode / DeepSeek and other OpenAI-compatible providers, switched via `base_url`);
- ``complete()``: **keeps M4's OpenAI dict signature and return shape**
  (``chat.py`` orchestration and tests' monkeypatching depend on it); internally
  the conversion is done via LangChain ``invoke``;
- ``stream_complete()``: streaming aggregation (used by SSE), with a per-token
  callback + returning the aggregated OpenAI dict shape;
- ``get_embeddings()``: ``OpenAIEmbeddings`` (returned only when EMBEDDING_*
  configuration is complete, otherwise None — semantic suggestions degrade to
  pure heuristics).

Provider matrix: see the AI module evolution plan (doc 07) §4.1:
DeepSeek (chat only) / Alibaba DashScope / OpenAI.

Testing convention: ``chat.py`` calls through the module attribute
``llm.complete``, and tests use ``monkeypatch.setattr("clew.ai.llm.complete",
fake)`` to completely avoid real network access; streaming tests likewise
monkeypatch ``llm.stream_complete``.
"""

from __future__ import annotations

import json
from typing import Callable, Iterator

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..config import Settings, get_settings

REQUEST_TIMEOUT_SECONDS = 60

NOT_CONFIGURED_MESSAGE = (
    "LLM not configured: set LLM_BASE_URL / LLM_MODEL in the repository-root .env"
    " (set LLM_API_KEY if your provider requires it)"
)

_EMBEDDING_NOT_CONFIGURED_MESSAGE = (
    "Embedding not configured: set EMBEDDING_BASE_URL / EMBEDDING_MODEL in .env"
    " (set EMBEDDING_API_KEY if your provider requires it)"
)


class LLMNotConfigured(RuntimeError):
    """Required LLM configuration is missing (route layer turns it into 503)."""


class LLMError(RuntimeError):
    """LLM service unreachable, non-200 response, or invalid response structure (route layer turns it into 502)."""


def is_configured(settings: Settings | None = None) -> bool:
    """Configured when both base_url and model are non-empty; the API key may be omitted for local services."""
    s = settings or get_settings()
    return bool(s.llm_base_url.strip() and s.llm_model.strip())


def endpoint_url(base_url: str) -> str:
    """Compatibility helper: normalize base_url into a chat/completions endpoint
    (LangChain does not need this; used for logging and external scripts to
    locate the endpoint)."""
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _require_configured(settings: Settings) -> None:
    if not is_configured(settings):
        raise LLMNotConfigured(NOT_CONFIGURED_MESSAGE)


def get_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """Build a ChatOpenAI from configuration (created per call; model instances are not thread-safe and are not cached)."""
    s = settings or get_settings()
    _require_configured(s)
    return ChatOpenAI(
        model=s.llm_model.strip(),
        api_key=s.llm_api_key.strip() or None,
        base_url=s.llm_base_url.strip(),
        temperature=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=1,
    )


def get_embeddings(settings: Settings | None = None) -> OpenAIEmbeddings | None:
    """Return None when embeddings are not configured (semantic suggestions degrade to pure heuristics)."""
    s = settings or get_settings()
    if not (s.embedding_base_url.strip() and s.embedding_model.strip()):
        return None
    return OpenAIEmbeddings(
        model=s.embedding_model.strip(),
        api_key=s.embedding_api_key.strip() or None,
        base_url=s.embedding_base_url.strip(),
        # Non-OpenAI providers (e.g. DashScope) do not support its local
        # tokenizer's context-length pre-check; disable it and send the full
        # segment directly
        check_embedding_ctx_length=False,
        chunk_size=16,
        max_retries=1,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


# ---------- Message and tool format conversion (OpenAI dict ↔ LangChain) ----------


def _to_lc_messages(messages: list[dict]) -> list:
    lc: list = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            lc.append(SystemMessage(content=str(content or "")))
        elif role == "user":
            lc.append(HumanMessage(content=str(content or "")))
        elif role == "assistant":
            tool_calls = []
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError):
                    args = {}
                tool_calls.append({
                    "name": function.get("name") or "",
                    "args": args if isinstance(args, dict) else {},
                    "id": call.get("id") or "",
                })
            lc.append(AIMessage(content=str(content or ""), tool_calls=tool_calls))
        elif role == "tool":
            lc.append(ToolMessage(
                content=str(content or ""),
                tool_call_id=str(message.get("tool_call_id") or ""),
            ))
    return lc


def _to_openai_message(message: AIMessage) -> dict:
    """Convert a LangChain AIMessage back into the OpenAI message dict chat.py expects."""
    content = message.content
    if not isinstance(content, str):
        # Support the segmented-array shape by concatenating into plain text
        content = "".join(
            part if isinstance(part, str)
            else (part.get("text") or "") if isinstance(part, dict) else str(part)
            for part in (content or [])
        )
    result: dict = {"role": "assistant", "content": content}
    if message.tool_calls:
        result["tool_calls"] = [{
            "id": call.get("id") or "",
            "type": "function",
            "function": {
                "name": call.get("name") or "",
                "arguments": json.dumps(
                    call.get("args") or {}, ensure_ascii=False),
            },
        } for call in message.tool_calls]
    return result


def _openai_response(message: AIMessage) -> dict:
    return {"choices": [{"message": _to_openai_message(message)}]}


def _bind_tools(model: ChatOpenAI, tools: list[dict] | None):
    if not tools:
        return model
    # bind_tools directly accepts OpenAI function-calling JSON Schema
    return model.bind_tools(tools)


def complete(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Non-streaming call: keeps M4's OpenAI dict signature (chat.py orchestration and tests depend on it).

    When ``tools`` is empty (None or an empty list), tools/tool_choice are not
    sent, used to force a final answer. Missing configuration raises
    :class:`LLMNotConfigured`; provider errors raise :class:`LLMError`.
    """
    settings = get_settings()
    _require_configured(settings)
    model = _bind_tools(get_chat_model(settings), tools)
    try:
        result = model.invoke(_to_lc_messages(messages))
    except LLMNotConfigured:
        raise
    except Exception as exc:  # LangChain uniformly raises Exception subclasses; converge to LLMError
        raise LLMError(f"LLM call failed: {exc}") from None
    if not isinstance(result, AIMessage):
        raise LLMError("LLM returned an unexpected message type")
    return _openai_response(result)


def stream_complete(
    messages: list[dict],
    tools: list[dict] | None,
    on_delta: Callable[[str], None] | None = None,
) -> dict:
    """Streaming call: invoke ``on_delta`` per content token and return a dict shaped like :func:`complete`.

    Chunks containing ``tool_call_chunks`` belong to a tool-call round and emit
    no text; only the final answer round's content triggers ``on_delta``.
    """
    settings = get_settings()
    _require_configured(settings)
    model = _bind_tools(get_chat_model(settings), tools)
    aggregated: AIMessageChunk | None = None
    try:
        for chunk in model.stream(_to_lc_messages(messages)):
            aggregated = chunk if aggregated is None else aggregated + chunk
            has_tool = bool(getattr(chunk, "tool_call_chunks", None))
            if not has_tool and on_delta is not None:
                text = chunk.content if isinstance(chunk.content, str) else ""
                if text:
                    on_delta(text)
    except LLMNotConfigured:
        raise
    except Exception as exc:
        raise LLMError(f"LLM streaming call failed: {exc}") from None
    if aggregated is None or not isinstance(aggregated, AIMessage):
        raise LLMError("LLM streaming response is empty")
    return _openai_response(aggregated)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-vectorize texts; raises :class:`LLMNotConfigured` when embeddings are not configured."""
    model = get_embeddings()
    if model is None:
        raise LLMNotConfigured(_EMBEDDING_NOT_CONFIGURED_MESSAGE)
    try:
        return model.embed_documents(texts)
    except Exception as exc:
        raise LLMError(f"embedding call failed: {exc}") from None
