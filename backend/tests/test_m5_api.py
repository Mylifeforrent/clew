"""M5 AI evolution regression tests: SSE streaming chat and MCP tool exposure."""

from __future__ import annotations

import json

from tests.conftest import login, upload
from tests.fixtures import order_xlsx_bytes
from tests.test_m4_api import _configure_llm, _seed


def test_ai_chat_stream_sse_events(client, monkeypatch):
    """SSE event sequence: tool (highlight declaration) → token (incremental) → done (with highlights)."""
    headers = login(client)
    _seed(client, headers)
    _configure_llm(monkeypatch)

    calls: list[dict] = []

    def fake_stream_complete(messages, tools=None, on_delta=None):
        calls.append({"tools": tools})
        if len(messages) == 2:  # first round: declare highlights (tool round, no tokens emitted)
            return {"choices": [{"message": {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "mark_highlight",
                                             "arguments": json.dumps({"fields": [
                                                 {"dataset": "ods_order",
                                                  "field": "order_no"}]})}}]}}]}
        if on_delta is not None:
            on_delta("Hello")
            on_delta(", world")
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "Hello, world"}}]}

    monkeypatch.setattr("clew.ai.llm.stream_complete",
                        fake_stream_complete)

    r = client.post("/ai/chat/stream", headers=headers, json={
        "messages": [{"role": "user", "content": "Highlight order_no"}]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")

    events: list[dict] = []
    current: dict = {}
    for line in r.text.splitlines():
        if line.startswith("event: "):
            current = {"type": line[7:].strip()}
        elif line.startswith("data: "):
            current["data"] = json.loads(line[6:])
            events.append(current)
    assert [event["type"] for event in events] == ["tool", "token", "token", "done"]
    assert events[0]["data"]["tool"] == "mark_highlight"
    assert [e["data"]["delta"] for e in events[1:3]] == ["Hello", ", world"]
    done = events[3]["data"]
    assert done["answer"] == "Hello, world"
    assert done["highlights"] == [{"dataset": "ods_order", "field": "order_no"}]
    # Tool rounds emit no tokens; round 2 still carries tools (only the 6th request forces a conclusion without tools)
    assert calls[0]["tools"] is not None
    assert calls[1]["tools"] is not None


def test_mcp_server_exposes_readonly_query_tools():
    """The MCP server exposes only 5 query tools (no write-candidate/draft capability)."""
    import asyncio

    from clew.ai.mcp_server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "lineage_search_fields", "lineage_field_details", "lineage_trace",
        "lineage_field_history", "lineage_overview"}
