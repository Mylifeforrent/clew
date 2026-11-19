"""Review-fix regression tests (R1-R18): edge uniqueness constraints, mixed-field edges, rollback FK conflicts, immediate role changes,
manifest row-level parse errors, same-pair merging and re-import idempotence, upload hardening (R1-R7, 2026-10-24 round);
AI write-tool role guards, SSE heartbeat and disconnect-stops, context budget, AI route rate limiting, draft language
(R8-R12, 2026-10-26 round, see the review-fix batch doc for 2026-10-26, doc 08)."""

import copy
import json
import sqlite3
import time

import pytest

from clew.ai import chat as chat_mod
from clew.config import db_path
from clew.routes import ai as ai_routes

from tests.conftest import csv_bytes, create_user, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes
from tests.test_m4_api import (_call, _configure_llm, _final_answer, _seed,
                               _tool_round)


def _seed_sources(client, headers) -> None:
    upload(client, headers, [
        ("orders.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])


def _import_json(client, headers, manifest: dict):
    return client.post("/import", headers=headers,
                       data={"format": "json", "source_file_ids": "1,2,3"},
                       files={"manifest": ("manifest.json",
                                           json.dumps(manifest, ensure_ascii=False).encode(),
                                           "application/json")})


def _import_csv(client, headers, ds_rows, edge_rows):
    return client.post("/import", headers=headers,
                       data={"format": "csv", "source_file_ids": "1,2,3"},
                       files={
                           "manifest_datasets": ("datasets.csv", csv_bytes(ds_rows), "text/csv"),
                           "manifest_lineage": ("lineage.csv", csv_bytes(edge_rows), "text/csv"),
                       })


def _db() -> sqlite3.Connection:
    return sqlite3.connect(db_path())


def _ods_user_manifest(transform: str = "trim") -> dict:
    return {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name", "transform": transform},
        ],
    }


# ---------- R1: uniqueness constraints for table-level/field-level edges (partial unique indexes) ----------

def test_r1_duplicate_edges_blocked_by_partial_unique_index(client):
    login(client)  # triggers init_db to create the database and indexes
    ins = ("INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
           " source, created_at, updated_at) VALUES (?,?,?,?,?,?,?)")
    ts = "2026-01-01T00:00:00+00:00"
    for key in [("A", None, "B", None),  # table-level edge: UNIQUE columns contain NULL, caught by uq_edge_table
                ("A", "f", "B", "g")]:   # field-level edge: caught by uq_edge_field
        conn = _db()
        conn.execute(ins, (*key, "manual", ts, ts))
        try:
            conn.execute(ins, (*key, "manual", ts, ts))
            dup_ok = True
        except sqlite3.IntegrityError:
            dup_ok = False
        finally:
            conn.close()
        assert not dup_ok, f"duplicate edge for natural key {key} was not blocked"


# ---------- R2: mixed-field edges are rejected as a whole row ----------

def test_r2_mixed_field_edge_rejected(client):
    headers = login(client)
    _seed_sources(client, headers)
    ds_rows = [
        ["dataset_id", "dataset_name", "field_name", "field_type", "src_file",
         "src_type", "src_locator", "description"],
        ["ods_raw", "Order Details", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                     "header_rows": 2, "row_start": 3}), "Order number"],
        ["dwd_order", "Order Wide Table", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "column": "C", "row_start": 3}), "Wide-table order number"],
    ]
    edge_rows = [
        ["from_dataset", "from_field", "to_dataset", "to_field", "transform",
         "confidence", "note"],
        ["ods_raw", "order_no", "dwd_order", "", "", "", ""],   # upstream field only: rejected
        ["ods_raw", "", "dwd_order", "order_no", "", "", ""],   # downstream field only: rejected
        ["ods_raw", "", "dwd_order", "", "", "", ""],           # table-level edge: valid
        ["ods_raw", "order_no", "dwd_order", "order_no", "trim/cast", "1.0", ""],
    ]
    r = _import_csv(client, headers, ds_rows, edge_rows)
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    assert report["summary"] == {"total": 6, "ok": 4, "merged": 0, "rejected": 2}
    rejected = [i for i in report["items"] if i["status"] == "rejected"]
    for item in rejected:
        assert item["kind"] == "edge"
        assert item["reason"] == ("Lineage edges must provide both upstream and"
                                  " downstream fields (field-level) or neither (table-level)")

    conn = _db()
    n_mixed = conn.execute(
        "SELECT COUNT(*) FROM edge WHERE (from_field IS NULL) != (to_field IS NULL)"
    ).fetchone()[0]
    n_table = conn.execute(
        "SELECT COUNT(*) FROM edge WHERE from_field IS NULL AND to_field IS NULL"
    ).fetchone()[0]
    conn.close()
    assert n_mixed == 0
    assert n_table == 1


# ---------- R3: batch rollback hitting a foreign-key reference → 409 ----------

def test_r3_rollback_blocked_by_later_batch_fk(client):
    headers = login(client)
    _seed_sources(client, headers)

    # batch1: create two ods_user fields
    r1 = _import_json(client, headers, {**_ods_user_manifest(), "lineage": []})
    assert r1.status_code == 201, r1.text
    batch1 = r1.json()["batch_id"]

    # batch2: an edge references a field added by batch1
    manifest2 = {
        "datasets": [],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_name",
             "to_dataset": "ods_user", "to_field": "user_id", "transform": "lookup"},
        ],
    }
    r2 = _import_json(client, headers, manifest2)
    assert r2.status_code == 201, r2.text
    batch2 = r2.json()["batch_id"]

    # Roll back batch1 directly: its fields are referenced by batch2's edge → 409
    r = client.post(f"/import/batches/{batch1}/rollback", headers=headers)
    assert r.status_code == 409, r.text
    assert "roll back the later batches first" in r.json()["detail"]

    # Roll back batch2 first (deleting the edge) then batch1 → both succeed and the DB is clean
    assert client.post(f"/import/batches/{batch2}/rollback",
                       headers=headers).status_code == 200
    assert client.post(f"/import/batches/{batch1}/rollback",
                       headers=headers).status_code == 200
    snap = client.get("/lineage/snapshot", headers=headers).json()
    assert snap["fields"] == []
    assert snap["datasets"] == []


# ---------- R4: role changes take effect immediately ----------

def test_r4_role_change_takes_effect_immediately(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "lisi", "editor")
    # Before the downgrade the editor can upload
    upload(client, editor_headers, [("users.csv", user_csv_bytes(), "text/csv")])

    # M1 has no role-change endpoint yet; modify the database directly to simulate an
    # admin downgrading lisi to viewer
    conn = _db()
    conn.execute("UPDATE user SET role='viewer' WHERE username='lisi'")
    conn.commit()
    conn.close()

    # The old token (still declaring editor in the JWT) uploads again → the DB role wins, 403
    r = client.post("/files", headers=editor_headers,
                    files=[("files", ("x.csv", b"a,b\n1,2\n", "text/csv"))])
    assert r.status_code == 403, r.text


# ---------- R5: manifest row-level parse errors reject only that row ----------

def test_r5_row_parse_error_rejects_row_not_batch(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "bad_loc",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": "not-json"},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name",
             "transform": "lookup", "confidence": "abc"},
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name",
             "transform": "lookup2", "confidence": "1.0"},
        ],
    }
    r = _import_json(client, headers, manifest)
    assert r.status_code == 201, r.text  # row-level errors do not fail the whole batch with 400
    report = r.json()["report"]
    assert report["summary"] == {"total": 5, "ok": 3, "merged": 0, "rejected": 2}
    bad_loc = next(i for i in report["items"] if i["ref"] == "ods_user.bad_loc")
    assert bad_loc["status"] == "rejected" and "src_locator" in bad_loc["reason"]
    bad_edge = next(i for i in report["items"]
                    if i["kind"] == "edge" and i["status"] == "rejected")
    assert "confidence" in bad_edge["reason"]

    # Valid rows are persisted normally
    ods = client.get("/datasets/ods_user", headers=headers).json()
    assert [f["name"] for f in ods["fields"]] == ["user_id", "user_name"]


# ---------- R6: same-pair merging / re-import idempotence ----------

def test_r6_same_pair_different_transform_merged(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = _ods_user_manifest()
    manifest["lineage"] = [
        {"from_dataset": "ods_user", "from_field": "user_id",
         "to_dataset": "ods_user", "to_field": "user_name", "transform": "t1"},
        {"from_dataset": "ods_user", "from_field": "user_id",
         "to_dataset": "ods_user", "to_field": "user_name", "transform": "t2"},
    ]
    r = _import_json(client, headers, manifest)
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["merged"] == 1

    conn = _db()
    row = conn.execute(
        "SELECT transform FROM edge WHERE from_dataset='ods_user'"
        " AND from_field='user_id' AND to_dataset='ods_user' AND to_field='user_name'"
    ).fetchone()
    conn.close()
    assert row[0] == "t2"  # the database holds the later value


def test_r6_reimport_idempotent_no_change_log(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = _ods_user_manifest()

    r1 = _import_json(client, headers, manifest)
    assert r1.status_code == 201, r1.text
    conn = _db()
    before = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    conn.close()

    r2 = _import_json(client, headers, manifest)
    assert r2.status_code == 201, r2.text
    report2 = r2.json()["report"]
    assert report2["items"]  # non-empty and all ok + unchanged
    assert all(i["status"] == "ok" and i["reason"] == "unchanged"
               for i in report2["items"])

    conn = _db()
    after = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    conn.close()
    assert after == before  # the second import added no change_log rows


# ---------- R7: upload hardening ----------

def test_r7_upload_empty_file_list_400(client):
    headers = login(client)
    r = client.post("/files", headers=headers)
    assert r.status_code == 400, r.text
    assert "Upload at least one file" in r.json()["detail"]


def test_r7_upload_oversize_413(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    headers = login(client)
    big = b"a,b\n" + b"1,2\n" * 300_000  # ≈1.4MB, over the 1MB limit
    r = client.post("/files", headers=headers,
                    files=[("files", ("big.csv", big, "text/csv"))])
    assert r.status_code == 413, r.text


# ---------- R8: editor role guard on write-type tools (doc 08) ----------

def test_r8_suggest_lineage_denied_for_viewer_via_chat(client, monkeypatch):
    admin_headers = login(client)
    _seed(client, admin_headers)
    viewer_headers = create_user(client, admin_headers, "viewer_r8a", "viewer")
    editor_headers = create_user(client, admin_headers, "editor_r8a", "editor")
    _configure_llm(monkeypatch)
    ai_routes.ai_chat_limiter.reset()

    def fake_complete(messages, tools=None):
        if not any(m.get("role") == "tool" for m in messages):
            return _tool_round(
                [_call("call_suggest", "suggest_lineage",
                       {"dataset": "ods_order"})])
        return _final_answer("Lineage suggestions requested.")

    monkeypatch.setattr("clew.ai.llm.complete", fake_complete)

    # viewer: the write-type tool is rejected by the role guard and nothing is persisted
    r = client.post("/ai/chat", headers=viewer_headers, json={
        "messages": [{"role": "user", "content": "Help me add lineage"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool_trace"][0]["tool"] == "suggest_lineage"
    assert body["tool_trace"][0]["ok"] is False
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM edge WHERE source='ai'")\
        .fetchone()[0] == 0
    conn.close()

    # editor: the same input is persisted normally (same-named dim_user.user_name is available for suggestion)
    r2 = client.post("/ai/chat", headers=editor_headers, json={
        "messages": [{"role": "user", "content": "Help me add lineage"}]})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["tool_trace"][0]["ok"] is True
    assert body2.get("suggestions"), body2
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM edge WHERE source='ai'")\
        .fetchone()[0] >= 1
    conn.close()


def test_r8_draft_descriptions_denied_for_viewer_via_chat(client, monkeypatch):
    admin_headers = login(client)
    viewer_headers = create_user(client, admin_headers, "viewer_r8b", "viewer")
    _configure_llm(monkeypatch)
    ai_routes.ai_chat_limiter.reset()

    def fake_complete(messages, tools=None):
        if not any(m.get("role") == "tool" for m in messages):
            return _tool_round(
                [_call("call_draft", "draft_descriptions",
                       {"dataset": "ods_order"})])
        return _final_answer("Drafts require higher permission.")

    monkeypatch.setattr("clew.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=viewer_headers, json={
        "messages": [{"role": "user", "content": "Help me generate descriptions"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool_trace"][0]["tool"] == "draft_descriptions"
    assert body["tool_trace"][0]["ok"] is False
    assert "drafts" not in body
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM description_draft")\
        .fetchone()[0] == 0
    conn.close()


# ---------- R9: disconnect-stops + SSE heartbeat (doc 08) ----------

def test_r9_cancel_stops_further_rounds(client):
    """After should_interrupt is set: no further LLM call is made and ChatInterrupted is raised."""
    client_fixture_guards_tmp_db = client  # noqa: F841 — the client fixture points DATA_DIR at a temp dir
    calls: list[list] = []

    def fake_complete(messages, tools=None):
        calls.append(copy.deepcopy(messages))
        return _tool_round([_call("call_mark", "mark_highlight",
                                  {"fields": [{"dataset": "zz", "field": "yy"}]})])

    with pytest.raises(chat_mod.ChatInterrupted):
        chat_mod._drive(
            [{"role": "user", "content": "Keep querying for me"}], None, "actor",
            "viewer", fake_complete, None,
            should_interrupt=lambda: len(calls) >= 1)

    assert len(calls) == 1, "a further LLM call was made after the interruption"


def test_r9_sse_ping_heartbeat(client, monkeypatch):
    admin_headers = login(client)
    _configure_llm(monkeypatch)
    monkeypatch.setattr(ai_routes, "PING_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr("clew.ai.llm.is_configured", lambda settings: True)
    ai_routes.ai_chat_limiter.reset()

    def fake_stream(messages, tools=None, on_delta=None):
        time.sleep(0.3)  # the event queue is empty during this time; a heartbeat comment frame should appear
        return _final_answer("Streaming answer complete.")

    monkeypatch.setattr("clew.ai.llm.stream_complete", fake_stream)

    with client.stream("POST", "/ai/chat/stream", headers=admin_headers,
                       json={"messages": [{"role": "user", "content": "hi"}]})\
            as response:
        assert response.status_code == 200, response
        body = response.read()
    assert b": ping" in body, body
    assert b"event: done" in body, body


# ---------- R10: tool result truncation + context budget (doc 08) ----------

def test_r10_tool_result_truncated_before_feeding(client, monkeypatch):
    admin_headers = login(client)
    _seed(client, admin_headers)
    _configure_llm(monkeypatch)
    monkeypatch.setattr(chat_mod, "MAX_TOOL_RESULT_CHARS", 100)
    ai_routes.ai_chat_limiter.reset()

    captured: list[list] = []

    def fake_complete(messages, tools=None):
        captured.append(copy.deepcopy(messages))
        if not any(m.get("role") == "tool" for m in messages):
            return _tool_round([_call("call_details", "get_field_details",
                                      {"dataset": "ods_order",
                                       "field": "order_no"})])
        return _final_answer("Returned truncated.")

    monkeypatch.setattr("clew.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=admin_headers, json={
        "messages": [{"role": "user", "content": "Show me the details of order_no"}]})
    assert r.status_code == 200, r.text
    assert r.json()["tool_trace"][0]["ok"] is True

    tool_messages = [m for m in captured[1] if m.get("role") == "tool"]
    assert tool_messages, captured[1]
    content = tool_messages[0]["content"]
    assert "truncated" in content, content
    assert len(content) < 500, content  # the original result contains a 50-row preview and is necessarily longer


def test_r10_context_budget_prunes_oldest_block(client, monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_TOKEN_BUDGET", "10")  # extremely small, forcing trimming
    admin_headers = login(client)
    _configure_llm(monkeypatch)
    ai_routes.ai_chat_limiter.reset()

    captured: list[list] = []

    def fake_complete(messages, tools=None):
        captured.append(copy.deepcopy(messages))
        if not any(m.get("role") == "tool" for m in messages):
            return _tool_round([_call("call_mark", "mark_highlight",
                                      {"fields": [{"dataset": "zz",
                                                   "field": "yy"}]})])
        return _final_answer("Trimmed the history.")

    monkeypatch.setattr("clew.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=admin_headers, json={
        "messages": [
            {"role": "user", "content": "old question AAA this is a sufficiently long old context"},
            {"role": "assistant", "content": "old answer BBB"},
            {"role": "user", "content": "new question CCC"},
        ]})
    assert r.status_code == 200, r.text

    # On the second call: system + the new question block (including this round's
    # assistant/tool); the old block has been deleted as a whole
    second = captured[1]
    serialized = json.dumps(second, ensure_ascii=False)
    assert "old question AAA" not in serialized, serialized
    assert "new question CCC" in serialized, serialized
    assert [m["role"] for m in second][0] == "system"
    assert second[1]["role"] == "user"


# ---------- R11: AI route rate limiting (doc 08) ----------

def test_r11_chat_rate_limit_429(client, monkeypatch):
    limiter_headers = create_user(client, login(client), "limit_user", "viewer")
    ai_routes.ai_chat_limiter.reset()
    # The rate-limit dependency runs before the handler: requests whose handler
    # returns 503 (not configured) still count
    monkeypatch.setattr("clew.ai.llm.is_configured", lambda settings: False)

    for i in range(10):
        r = client.post("/ai/chat", headers=limiter_headers,
                        json={"messages": [{"role": "user",
                                            "content": f"question {i}"}]})
        assert r.status_code == 503, (i, r.status_code, r.text)  # not-configured LLM takes precedence over 429

    r_extra = client.post("/ai/chat", headers=limiter_headers,
                          json={"messages": [{"role": "user", "content": "question 10"}]})
    assert r_extra.status_code == 429, r_extra.text
    assert "too frequent" in r_extra.json()["detail"]
    assert int(r_extra.headers["Retry-After"]) >= 1


def test_r11_suggest_rate_limit_429(client):
    editor_headers = create_user(client, login(client), "limit_editor", "editor")
    ai_routes.ai_suggest_limiter.reset()

    for i in range(6):
        r = client.post("/ai/suggest", headers=editor_headers,
                        json={"dataset": "no_such_ds"})
        assert r.status_code == 404, (i, r.status_code, r.text)  # dataset does not exist → 404

    r_extra = client.post("/ai/suggest", headers=editor_headers,
                          json={"dataset": "no_such_ds"})
    assert r_extra.status_code == 429, r_extra.text


# ---------- R12: description draft prompt language parameter (doc 08) ----------

def test_r12_draft_prompt_follows_lang(client, monkeypatch):
    admin_headers = login(client)
    _seed(client, admin_headers)
    editor_headers = create_user(client, admin_headers, "editor_r12", "editor")
    _configure_llm(monkeypatch)
    ai_routes.ai_chat_limiter.reset()

    prompts: list[str] = []

    def fake_complete(messages, tools=None):
        if len(messages) == 1 and messages[0].get("role") == "user":
            prompts.append(messages[0]["content"])  # draft generation call (single user message)
            return _final_answer("User id, first column of the CSV source.")
        if not any(m.get("role") == "tool" for m in messages):
            return _tool_round([_call("call_draft", "draft_descriptions",
                                      {"dataset": "ods_order",
                                       "fields": ["order_no"],
                                       "lang": "en"})])
        return _final_answer("Draft generated.")

    monkeypatch.setattr("clew.ai.llm.complete", fake_complete)

    r = client.post("/ai/chat", headers=editor_headers, json={
        "messages": [{"role": "user", "content": "Draft a description in English"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["drafts"], body
    assert prompts, prompts
    assert "Write one sentence in English" in prompts[0], prompts[0]
    assert "data catalog writer" in prompts[0], prompts[0]
    assert body["drafts"][0]["draft"] == "User id, first column of the CSV source."
