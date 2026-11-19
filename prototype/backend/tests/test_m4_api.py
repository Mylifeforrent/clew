"""M4 acceptance: AI status/chat (function calling) and the full heuristic lineage suggestion flow.

Endpoints covered:
- GET /ai/status (viewer+, both unconfigured/configured states)
- POST /ai/chat (viewer+): unconfigured 503, tool loop, tool_trace, graph return,
  tool error pass-through, 5-round cap, LLM upstream error 502
- POST /ai/suggest (editor+): same-name fields/containment/exclude existing edges/persist source='ai'
- POST /ai/suggest/confirm (editor+): ai → manual + change_log(updated)
- POST /ai/suggest/reject (editor+): delete + change_log(deleted)

All LLM calls are replaced by monkeypatch (``lineagelite.ai.llm.complete``); another case
monkeypatches ``urllib.request.urlopen`` to verify request construction—no network access at all.
"""

import copy
import json
import sqlite3

import pytest

from lineagelite.config import db_path

from tests.conftest import create_user, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes

EDGE_FIELDS = ("from_dataset", "from_field", "to_dataset", "to_field")


def _configure_llm(monkeypatch, base_url="https://llm.invalid/v1",
                   api_key="test-key", model="test-model") -> None:
    monkeypatch.setenv("LLM_BASE_URL", base_url)
    monkeypatch.setenv("LLM_API_KEY", api_key)
    monkeypatch.setenv("LLM_MODEL", model)


def _seed(client, headers) -> None:
    """Upload three-format source files and import 4 datasets / 7 fields / 1 field-level edge."""
    files = upload(client, headers, [
        ("order_details.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])
    source_ids = ",".join(str(f["id"]) for f in files)
    manifest = {
        "datasets": [
            {"dataset_id": "ods_order", "dataset_name": "Raw Orders",
             "field_name": "order_no", "field_type": "STRING",
             "src_file": "order_details.xlsx", "src_type": "xlsx",
             "src_locator": {"sheet": "Orders", "column": "C", "row_start": 3},
             "description": "Order No"},
            {"dataset_id": "ods_order", "dataset_name": "Raw Orders",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}, "description": "User name"},
            {"dataset_id": "dwd_order", "dataset_name": "Order Wide Table",
             "field_name": "order_no", "field_type": "STRING",
             "src_file": "order_details.xlsx", "src_type": "xlsx",
             "src_locator": {"sheet": "Orders", "column": "C", "row_start": 3},
             "description": "Wide table order number"},
            {"dataset_id": "dwd_order", "dataset_name": "Order Wide Table",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}, "description": "Wide table user name"},
            {"dataset_id": "dws_order", "dataset_name": "Order Summary",
             "field_name": "ext_order_no", "field_type": "STRING",
             "src_file": "source.json", "src_type": "json",
             "src_locator": {"json_path": "$.data.items[*].order_no"},
             "description": "External order number"},
            {"dataset_id": "dim_user", "dataset_name": "User Dimension",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}, "description": "Dimension user name"},
            {"dataset_id": "dim_user", "dataset_name": "User Dimension",
             "field_name": "user_id", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 1}, "description": "User ID"},
        ],
        "lineage": [
            {"from_dataset": "ods_order", "from_field": "order_no",
             "to_dataset": "dwd_order", "to_field": "order_no",
             "transform": "trim/cast", "confidence": 1.0, "note": "Existing edge"},
        ],
    }
    r = client.post(
        "/import", headers=headers,
        data={"format": "json", "source_file_ids": source_ids},
        files={"manifest": ("manifest.json",
                            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                            "application/json")})
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["rejected"] == 0, r.text


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _db_count(sql: str, args: tuple = ()) -> int:
    conn = _db_conn()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _edge_row(from_dataset: str, from_field: str | None,
              to_dataset: str, to_field: str | None):
    conn = _db_conn()
    try:
        return conn.execute(
            "SELECT * FROM edge WHERE from_dataset=? AND from_field IS ?"
            " AND to_dataset=? AND to_field IS ?",
            (from_dataset, from_field, to_dataset, to_field)).fetchone()
    finally:
        conn.close()


def _candidate_payload(candidate: dict) -> dict:
    return {key: candidate[key] for key in EDGE_FIELDS}


def _final_answer(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}]}


def _tool_round(calls: list[dict]) -> dict:
    return {"choices": [{
        "message": {"role": "assistant", "content": None, "tool_calls": calls},
        "finish_reason": "tool_calls",
    }]}


def _call(call_id: str, name: str, arguments: dict) -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": name,
                         "arguments": json.dumps(arguments, ensure_ascii=False)}}


# ---------- LLM client (no network, LangChain message conversion layer) ----------

def test_llm_client_message_conversion_and_not_configured(monkeypatch):
    """After the M5 LangChain migration: verify OpenAI dict ↔ LangChain message conversion and unconfigured semantics."""
    from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

    from lineagelite.ai import llm

    monkeypatch.setenv("LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    captured: dict = {}

    class FakeChatModel:
        def bind_tools(self, tools):
            captured["tools"] = tools
            return self

        def invoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="ok", tool_calls=[{
                "name": "search_fields", "args": {"q": "order_no"}, "id": "c1"}])

    monkeypatch.setattr("lineagelite.ai.llm.get_chat_model",
                        lambda settings=None: FakeChatModel())

    tools = [{"type": "function",
              "function": {"name": "search_fields", "parameters": {}}}]
    result = llm.complete([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c0", "type": "function",
                         "function": {"name": "search_fields",
                                      "arguments": "{\"q\": \"x\"}"}}]},
        {"role": "tool", "tool_call_id": "c0", "content": "{\"results\": []}"},
    ], tools)
    # The return shape stays an OpenAI dict (chat.py orchestration depends on it)
    message = result["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "ok"
    assert message["tool_calls"][0]["function"]["name"] == "search_fields"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {
        "q": "order_no"}
    # The tool schema is passed to bind_tools unchanged
    assert captured["tools"] == tools
    # OpenAI dict messages are converted to LangChain message types
    kinds = [type(m) for m in captured["messages"]]
    assert kinds[0] is SystemMessage
    assert isinstance(captured["messages"][2], AIMessage)
    assert captured["messages"][2].tool_calls[0]["args"] == {"q": "x"}
    assert isinstance(captured["messages"][3], ToolMessage)
    assert captured["messages"][3].tool_call_id == "c0"

    # Not configured (empty base_url) → LLMNotConfigured, no request is made
    monkeypatch.setenv("LLM_BASE_URL", "")
    with pytest.raises(llm.LLMNotConfigured):
        llm.complete([{"role": "user", "content": "hi"}])


# ---------- Status and unconfigured state ----------

def test_ai_status_and_chat_requires_configuration(client, monkeypatch):
    admin_headers = login(client)
    viewer_headers = create_user(client, admin_headers, "viewer_m4", "viewer")

    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setenv(key, "")

    def forbidden(*args, **kwargs):
        raise AssertionError("The LLM must not be called when it is not configured")

    monkeypatch.setattr("lineagelite.ai.llm.complete", forbidden)

    r = client.get("/ai/status", headers=viewer_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"configured": False, "model": None}
    assert client.get("/ai/status").status_code == 401

    r = client.post("/ai/chat", headers=viewer_headers,
                    json={"messages": [{"role": "user", "content": "Hello"}]})
    assert r.status_code == 503, r.text
    assert r.json()["detail"].startswith("LLM is not configured")

    # Only base_url + model configured (local services may not need an API key) counts as configured
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    assert client.get("/ai/status", headers=viewer_headers).json() == {
        "configured": True, "model": "test-model"}

    seen: dict = {}

    def fake_final(messages, tools=None):
        seen["messages"] = copy.deepcopy(messages)
        seen["tools"] = tools
        return _final_answer("Hello, I am the LineageLite assistant.")

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_final)
    r = client.post("/ai/chat", headers=viewer_headers,
                    json={"messages": [{"role": "user", "content": "Hello"}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"answer": "Hello, I am the LineageLite assistant.",
                        "tool_trace": []}
    # The system prompt is fixed by the backend, and this request carries eight tools
    # (including canvas highlight/suggest/impact/draft)
    assert seen["messages"][0]["role"] == "system"
    assert {tool["function"]["name"] for tool in seen["tools"]} == {
        "search_fields", "get_field_details", "trace_lineage",
        "get_field_history", "mark_highlight", "suggest_lineage",
        "analyze_impact", "draft_descriptions"}


# ---------- Tool loop and graph rendering ----------

def test_ai_chat_tool_loop_returns_answer_and_graph(client, monkeypatch):
    headers = login(client)
    _seed(client, headers)
    _configure_llm(monkeypatch)

    calls: list[dict] = []

    def fake_complete(messages, tools=None):
        calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        if len(calls) == 1:
            return _tool_round([
                _call("call_search", "search_fields", {"q": "order_no"}),
                _call("call_details", "get_field_details",
                      {"dataset": "ods_order", "field": "order_no"}),
                _call("call_history", "get_field_history",
                      {"dataset": "ods_order", "field": "order_no"}),
                _call("call_trace", "trace_lineage",
                      {"dataset": "dwd_order", "field": "order_no",
                       "direction": "up", "hops": 2}),
            ])
        return _final_answer("dwd_order.order_no comes from ods_order.order_no.")

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user",
                      "content": "Where does dwd_order.order_no come from?"}],
        "focus": {"dataset": "dwd_order", "field": "order_no"},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "dwd_order.order_no comes from ods_order.order_no."
    assert body["tool_trace"] == [
        {"tool": "search_fields", "args": {"q": "order_no"}, "ok": True},
        {"tool": "get_field_details",
         "args": {"dataset": "ods_order", "field": "order_no"}, "ok": True},
        {"tool": "get_field_history",
         "args": {"dataset": "ods_order", "field": "order_no"}, "ok": True},
        {"tool": "trace_lineage",
         "args": {"dataset": "dwd_order", "field": "order_no",
                  "direction": "up", "hops": 2}, "ok": True},
    ]

    # graph takes the GraphPayload of the last trace_lineage
    graph = body["graph"]
    assert {dataset["id"] for dataset in graph["datasets"]} == {
        "dwd_order", "ods_order"}
    assert any(edge["from_dataset"] == "ods_order"
               and edge["to_dataset"] == "dwd_order"
               and edge["from_field"] == "order_no"
               and edge["to_field"] == "order_no"
               for edge in graph["edges"])

    # First request: system + user; second request: assistant plus 4 tool messages appended
    first = calls[0]
    assert [message["role"] for message in first["messages"]] == [
        "system", "user"]
    assert "dwd_order" in first["messages"][0]["content"]
    assert first["tools"] is not None

    second = calls[1]
    assert second["tools"] is not None  # only 1 round used, tools can still be called
    tool_messages = [message for message in second["messages"]
                     if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "call_search", "call_details", "call_history", "call_trace"]
    search_result = json.loads(tool_messages[0]["content"])
    assert any(item["name"] == "order_no"
               for item in search_result["results"])
    details_result = json.loads(tool_messages[1]["content"])
    assert details_result["dataset"] == "ods_order"
    assert details_result["field"] == "order_no"
    assert details_result["preview"]["file"]["original_name"] == "order_details.xlsx"
    history_result = json.loads(tool_messages[2]["content"])
    assert history_result["history"]
    assert history_result["history"][0]["op"] == "added"
    trace_result = json.loads(tool_messages[3]["content"])
    assert trace_result["graph"]["datasets"]


def test_ai_chat_mark_highlight_returns_highlights(client, monkeypatch):
    """mark_highlight verifies field existence and puts deduplicated fields into highlights."""
    headers = login(client)
    _seed(client, headers)
    _configure_llm(monkeypatch)

    def fake_complete(messages, tools=None):
        if len(messages) == 2:
            return _tool_round([
                _call("call_mark", "mark_highlight", {"fields": [
                    {"dataset": "ods_order", "field": "order_no"},
                    # duplicates deduplicated, non-existent items ignored
                    {"dataset": "ods_order", "field": "order_no"},
                    {"dataset": "ods_order", "field": "no_such_field"},
                ]}),
            ])
        return _final_answer("Highlighted the upstream and downstream of ods_order.order_no.")

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user",
                      "content": "Highlight the upstream and downstream of order_no"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Highlighted the upstream and downstream of ods_order.order_no."
    assert body["highlights"] == [
        {"dataset": "ods_order", "field": "order_no"}]
    assert body["tool_trace"] == [
        {"tool": "mark_highlight",
         "args": {"fields": [
             {"dataset": "ods_order", "field": "order_no"},
             {"dataset": "ods_order", "field": "order_no"},
             {"dataset": "ods_order", "field": "no_such_field"}]},
         "ok": True},
    ]
    # The key must be absent when no graph is returned
    assert "graph" not in body


def test_ai_chat_mark_highlight_all_invalid_is_tool_error(client, monkeypatch):
    """When none of fields exist, the tool reports an error back to the model and produces no highlights."""
    headers = login(client)
    _seed(client, headers)
    _configure_llm(monkeypatch)

    def fake_complete(messages, tools=None):
        if len(messages) == 2:
            return _tool_round([
                _call("call_mark", "mark_highlight", {"fields": [
                    {"dataset": "no_ds", "field": "no_field"},
                ]}),
            ])
        return _final_answer("No fields to highlight were found.")

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user", "content": "Highlight something"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool_trace"][0]["ok"] is False
    assert "highlights" not in body


def test_ai_chat_reports_tool_errors(client, monkeypatch):
    headers = login(client)
    _seed(client, headers)
    _configure_llm(monkeypatch)

    calls: list[dict] = []

    def fake_complete(messages, tools=None):
        calls.append(copy.deepcopy(messages))
        if len(calls) == 1:
            return _tool_round([
                _call("bad_tool", "no_such_tool", {}),
                _call("missing_field", "get_field_details",
                      {"dataset": "ods_order", "field": "missing"}),
            ])
        return _final_answer("The field was not found.")

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user", "content": "Look up a field that does not exist"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [item["ok"] for item in body["tool_trace"]] == [False, False]
    assert "graph" not in body
    tool_messages = [message for message in calls[1]
                     if message["role"] == "tool"]
    errors = [json.loads(message["content"])["error"]
              for message in tool_messages]
    assert "Unknown tool" in errors[0]
    assert "does not exist" in errors[1]


def test_ai_chat_stops_after_five_tool_rounds(client, monkeypatch):
    headers = login(client)
    _configure_llm(monkeypatch)

    calls: list = []

    def fake_complete(messages, tools=None):
        calls.append(tools)
        return _tool_round([
            _call(f"call_{len(calls)}", "search_fields", {"q": "x"})])

    monkeypatch.setattr("lineagelite.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user", "content": "Keep searching"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    # At most 5 tool rounds; the 6th request carries no tools, forcing closure
    assert len(body["tool_trace"]) == 5
    assert len(calls) == 6
    assert all(tools is not None for tools in calls[:5])
    assert calls[-1] is None
    assert body["answer"] == ""


def test_ai_chat_maps_llm_error_to_502(client, monkeypatch):
    headers = login(client)
    _configure_llm(monkeypatch)

    from lineagelite.ai import llm

    def boom(messages, tools=None):
        raise llm.LLMError("Upstream timeout")

    monkeypatch.setattr("lineagelite.ai.llm.complete", boom)

    r = client.post("/ai/chat", headers=headers, json={
        "messages": [{"role": "user", "content": "Hello"}]})
    assert r.status_code == 502, r.text
    assert "Upstream timeout" in r.json()["detail"]


# ---------- Heuristic suggestions ----------

def test_ai_suggest_heuristic_exact_containment_and_existing_edges(client):
    headers = login(client)
    _seed(client, headers)

    # Field-level: the only candidate for order_no is containment (dwd_order.order_no already has an edge and is excluded)
    r = client.post("/ai/suggest", headers=headers,
                    json={"dataset": "ods_order", "field": "order_no"})
    assert r.status_code == 200, r.text
    candidates = r.json()["candidates"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert set(candidate) == {*EDGE_FIELDS, "confidence", "reason"}
    assert (candidate["from_dataset"], candidate["from_field"],
            candidate["to_dataset"], candidate["to_field"]) == (
        "ods_order", "order_no", "dws_order", "ext_order_no")
    assert candidate["confidence"] == 0.6
    assert "containment" in candidate["reason"]

    row = _edge_row("ods_order", "order_no", "dws_order", "ext_order_no")
    assert row is not None
    assert row["source"] == "ai" and row["confidence"] == 0.6
    assert _db_count(
        "SELECT COUNT(*) FROM change_log WHERE entity_kind='edge'"
        " AND entity_key=? AND op='added'",
        ("ods_order.order_no-->dws_order.ext_order_no",)) == 1

    # Dataset-level: same field names take precedence (0.7); existing imported edges and the just-created ai edge are excluded
    r = client.post("/ai/suggest", headers=headers,
                    json={"dataset": "ods_order"})
    assert r.status_code == 200, r.text
    candidates = r.json()["candidates"]
    assert len(candidates) == 2
    assert all(item["confidence"] == 0.7 for item in candidates)
    assert all("Same field name" in item["reason"] for item in candidates)
    keys = {(item["from_dataset"], item["from_field"],
             item["to_dataset"], item["to_field"]) for item in candidates}
    assert keys == {
        ("ods_order", "user_name", "dwd_order", "user_name"),
        ("ods_order", "user_name", "dim_user", "user_name"),
    }
    assert ("ods_order", "order_no", "dwd_order", "order_no") not in keys

    # Repeated call: all candidate edges already exist → nothing new persisted
    r = client.post("/ai/suggest", headers=headers,
                    json={"dataset": "ods_order"})
    assert r.status_code == 200 and r.json()["candidates"] == []
    assert _db_count("SELECT COUNT(*) FROM edge WHERE source='ai'") == 3

    # Arguments do not exist
    assert client.post("/ai/suggest", headers=headers,
                       json={"dataset": "no_such"}).status_code == 404
    assert client.post("/ai/suggest", headers=headers,
                       json={"dataset": "ods_order",
                             "field": "no_such"}).status_code == 404


def test_ai_suggest_confirm_reject_flow_and_permissions(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m4", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m4", "viewer")
    _seed(client, admin_headers)

    payload = {"dataset": "ods_order", "field": "user_name"}

    # viewer has no permission to suggest/confirm/reject; unauthenticated 401
    assert client.post("/ai/suggest", headers=viewer_headers,
                       json=payload).status_code == 403
    assert client.post("/ai/suggest/confirm", headers=viewer_headers,
                       json={"from_dataset": "ods_order",
                             "from_field": "user_name",
                             "to_dataset": "dwd_order",
                             "to_field": "user_name"}).status_code == 403
    assert client.post("/ai/suggest/reject", headers=viewer_headers,
                       json={"from_dataset": "ods_order",
                             "from_field": "user_name",
                             "to_dataset": "dwd_order",
                             "to_field": "user_name"}).status_code == 403
    assert client.post("/ai/suggest", json=payload).status_code == 401

    # editor generates two same-name field candidates
    r = client.post("/ai/suggest", headers=editor_headers, json=payload)
    assert r.status_code == 200, r.text
    candidates = r.json()["candidates"]
    assert len(candidates) == 2
    assert all(item["confidence"] == 0.7 for item in candidates)
    assert _db_count("SELECT COUNT(*) FROM edge WHERE source='ai'") == 2
    assert _db_count(
        "SELECT COUNT(*) FROM change_log WHERE entity_kind='edge'"
        " AND op='added'") == 3  # 1 imported edge + 2 AI candidates

    confirm_target = next(item for item in candidates
                          if item["to_dataset"] == "dwd_order")
    reject_target = next(item for item in candidates
                         if item["to_dataset"] == "dim_user")

    # Confirm: source ai → manual, write an updated log
    r = client.post("/ai/suggest/confirm", headers=editor_headers,
                    json=_candidate_payload(confirm_target))
    assert r.status_code == 200, r.text
    edge = r.json()["edge"]
    assert edge["source"] == "manual"
    assert isinstance(edge["id"], int)
    assert edge["confidence"] == 0.7
    assert _edge_row("ods_order", "user_name", "dwd_order",
                     "user_name")["source"] == "manual"

    logs = client.get(
        "/changes", headers=viewer_headers,
        params={"entity_kind": "edge",
                "entity_key": "ods_order.user_name-->dwd_order.user_name"}
    ).json()
    assert [item["op"] for item in logs[:2]] == ["updated", "added"]
    assert logs[0]["actor"] == "editor_m4"
    assert logs[0]["before"]["source"] == "ai"
    assert logs[0]["after"]["source"] == "manual"
    assert logs[1]["after"]["source"] == "ai"

    # Repeated confirm on a promoted edge → 404 (only source='ai' can be operated on)
    assert client.post("/ai/suggest/confirm", headers=editor_headers,
                       json=_candidate_payload(confirm_target)
                       ).status_code == 404

    # Reject: delete the ai edge, write a deleted log
    r = client.post("/ai/suggest/reject", headers=editor_headers,
                    json=_candidate_payload(reject_target))
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert _edge_row("ods_order", "user_name", "dim_user", "user_name") is None
    logs = client.get(
        "/changes", headers=viewer_headers,
        params={"entity_kind": "edge",
                "entity_key": "ods_order.user_name-->dim_user.user_name"}
    ).json()
    assert [item["op"] for item in logs[:2]] == ["deleted", "added"]
    assert logs[0]["before"]["source"] == "ai"
    assert logs[0]["after"] is None

    # Non-AI edges cannot be confirmed/rejected; mixed fields 400
    imported = {"from_dataset": "ods_order", "from_field": "order_no",
                "to_dataset": "dwd_order", "to_field": "order_no"}
    assert client.post("/ai/suggest/confirm", headers=editor_headers,
                       json=imported).status_code == 404
    assert client.post("/ai/suggest/reject", headers=editor_headers,
                       json=imported).status_code == 404
    assert _edge_row("ods_order", "order_no", "dwd_order",
                     "order_no")["source"] == "imported"
    assert client.post("/ai/suggest/confirm", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": None,
        "to_dataset": "dwd_order", "to_field": "user_name"}).status_code == 400
