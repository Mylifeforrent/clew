"""M3 acceptance: annotations, manual field/edge editing, change history, version-tag diff and idempotent rollback.

Endpoints covered:
- POST/GET /annotations (target existence validation, append-only)
- PATCH /fields/{ds}/{field} (locator real-file verification and resolved re-materialization)
- POST/PATCH/DELETE /edges (source=manual, natural-key uniqueness, mixed-field validation)
- GET /changes (filtering + descending order + limit)
- POST/GET /version-tags, GET /version-tags/diff, POST /version-tags/{name}/rollback
- GraphPayload.edges[].id

Permissions: viewer gets 403 on all write endpoints; tag rollback is admin-only.
All data enters the database through the formal upload + import APIs.
"""

import json
import sqlite3

from clew.config import db_path

from tests.conftest import create_user, login, upload
from tests.fixtures import order_xlsx_bytes, user_csv_bytes

# users.csv header: user_id,user_name,phone; the order number in orders.xlsx is in column C
XLSX_ORDER_LOCATOR = {"sheet": "Orders", "column": "C", "row_start": 3}
CSV_USER_LOCATOR = {"column": 2}


def _seed(client, headers) -> str:
    """Upload two kinds of source files and import 3 datasets / 4 fields / 1 field-level edge + 1 table-level edge."""
    files = upload(client, headers, [
        ("orders.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
    ])
    source_ids = ",".join(str(f["id"]) for f in files)
    manifest = {
        "datasets": [
            {"dataset_id": "ods_order", "dataset_name": "Raw Orders",
             "field_name": "order_no", "field_type": "STRING",
             "src_file": "orders.xlsx", "src_type": "xlsx",
             "src_locator": XLSX_ORDER_LOCATOR, "description": "Order number"},
            {"dataset_id": "ods_order", "dataset_name": "Raw Orders",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": CSV_USER_LOCATOR, "description": "User name"},
            {"dataset_id": "dwd_order", "dataset_name": "Order Wide Table",
             "field_name": "order_no", "field_type": "STRING",
             "src_file": "orders.xlsx", "src_type": "xlsx",
             "src_locator": XLSX_ORDER_LOCATOR, "description": "Wide-table order number"},
            {"dataset_id": "dwd_order", "dataset_name": "Order Wide Table",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": CSV_USER_LOCATOR, "description": "Wide-table user name"},
            {"dataset_id": "dim_user", "dataset_name": "User Dimension",
             "field_name": "user_name", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": CSV_USER_LOCATOR, "description": "Dimension user name"},
        ],
        "lineage": [
            {"from_dataset": "ods_order", "from_field": "order_no",
             "to_dataset": "dwd_order", "to_field": "order_no",
             "transform": "trim/cast", "confidence": 1.0, "note": "imported field-level"},
            {"from_dataset": "ods_order", "from_field": None,
             "to_dataset": "dwd_order", "to_field": None,
             "transform": "table_projection", "confidence": 1.0,
             "note": "imported table-level"},
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
    return source_ids


def _import_phone_field(client, headers, source_ids: str) -> None:
    """Import once more after the tag (to verify that tag rollback reverses import-batch logs)."""
    manifest = {
        "datasets": [
            {"dataset_id": "ods_order", "dataset_name": "Raw Orders",
             "field_name": "phone", "field_type": "STRING",
             "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 3}, "description": "Phone number"},
        ],
        "lineage": [],
    }
    r = client.post(
        "/import", headers=headers,
        data={"format": "json", "source_file_ids": source_ids},
        files={"manifest": ("manifest.json",
                            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                            "application/json")})
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["rejected"] == 0, r.text


def _subgraph(client, headers, dataset: str = "ods_order", hops: int = 3) -> dict:
    r = client.get("/lineage/subgraph", headers=headers,
                   params={"dataset": dataset, "hops": hops})
    assert r.status_code == 200, r.text
    return r.json()


def _edge_id(client, headers, *, from_dataset: str, from_field: str | None,
             to_dataset: str, to_field: str | None) -> int:
    payload = _subgraph(client, headers)
    for edge in payload["edges"]:
        if (edge["from_dataset"] == from_dataset
                and edge["from_field"] == from_field
                and edge["to_dataset"] == to_dataset
                and edge["to_field"] == to_field):
            return edge["id"]
    raise AssertionError(f"Edge {from_dataset}.{from_field}-->"
                         f"{to_dataset}.{to_field} not found")


def _db_count(sql: str, args: tuple = ()) -> int:
    conn = sqlite3.connect(db_path())
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _max_change_id() -> int:
    return _db_count("SELECT COALESCE(MAX(id),0) FROM change_log")


# ---------- Annotations ----------

def test_annotations_append_only_and_target_validation(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)  # triggers DB creation and prepares annotation targets
    log_count = _db_count("SELECT COUNT(*) FROM change_log")

    targets = [
        ("dataset", "ods_order"),
        ("field", "ods_order.order_no"),
        ("edge", "ods_order.order_no-->dwd_order.order_no"),
        ("edge", "ods_order.*-->dwd_order.*"),
        ("edge", "ods_order-->dwd_order"),  # table-level shorthand
    ]
    created = []
    for kind, target_id in targets:
        r = client.post("/annotations", headers=editor_headers,
                        json={"target_kind": kind, "target_id": target_id,
                              "body": f"{kind} note"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["author"] == "editor_m3"
        assert body["target_kind"] == kind and body["target_id"] == target_id
        created.append(body["id"])

    # Append-only: write one more note for the same field; the old record is kept as-is
    r = client.post("/annotations", headers=editor_headers,
                    json={"target_kind": "field",
                          "target_id": "ods_order.order_no",
                          "body": "second note"})
    assert r.status_code == 201, r.text
    rows = client.get("/annotations", headers=viewer_headers,
                      params={"target_kind": "field",
                              "target_id": "ods_order.order_no"}).json()
    assert [row["body"] for row in rows] == ["field note", "second note"]
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)
    assert len(client.get("/annotations", headers=viewer_headers).json()) == 6
    # Annotations do not write change_log (append-only, not deleted by rollback)
    assert _db_count("SELECT COUNT(*) FROM change_log") == log_count
    # There are no annotation update/delete endpoints
    assert client.patch(f"/annotations/{created[0]}", headers=editor_headers,
                        json={"body": "modified"}).status_code in (404, 405)
    assert client.delete(f"/annotations/{created[0]}",
                         headers=editor_headers).status_code in (404, 405)

    # All three target kinds missing → 404
    for kind, target_id in [
        ("dataset", "no_such"),
        ("field", "ods_order.no_such"),
        ("edge", "ods_order.no_such-->dwd_order.order_no"),
        ("edge", "no_such-->dwd_order"),
    ]:
        r = client.post("/annotations", headers=editor_headers,
                        json={"target_kind": kind, "target_id": target_id,
                              "body": "x"})
        assert r.status_code == 404, (kind, target_id, r.text)

    # Invalid format → 400
    for kind, target_id in [("field", "no_dot"), ("edge", "a->b")]:
        r = client.post("/annotations", headers=editor_headers,
                        json={"target_kind": kind, "target_id": target_id,
                              "body": "x"})
        assert r.status_code == 400, (kind, target_id, r.text)

    # Blank body rejected; viewer can read but not write
    assert client.post("/annotations", headers=editor_headers,
                       json={"target_kind": "dataset", "target_id": "ods_order",
                             "body": "   "}).status_code == 400
    assert client.post("/annotations", headers=viewer_headers,
                       json={"target_kind": "dataset", "target_id": "ods_order",
                             "body": "x"}).status_code == 403
    assert client.get("/annotations", headers=viewer_headers).status_code == 200
    assert client.get("/annotations").status_code == 401


# ---------- Field editing ----------

def test_patch_field_description_and_locator_recheck(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)

    # Change description/type
    r = client.patch("/fields/ods_order/user_name", headers=editor_headers,
                     json={"description": "manually corrected", "field_type": "TEXT"})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "manually corrected"
    assert r.json()["field_type"] == "TEXT"

    # Change locator: column 2 → 3, requiring structural validation + real-file
    # verification and resolved re-materialization
    r = client.patch("/fields/ods_order/user_name", headers=editor_headers,
                     json={"src_locator": {"column": 3}})
    assert r.status_code == 200, r.text
    locator = r.json()["src_locator"]
    assert locator["type"] == "csv"
    assert locator["input"] == {"column": 3}
    assert locator["resolved"]["column_index"] == 3
    assert locator["resolved"]["header"] == "phone"

    ds = client.get("/datasets/ods_order", headers=editor_headers).json()
    field = next(f for f in ds["fields"] if f["name"] == "user_name")
    assert field["description"] == "manually corrected"
    assert field["src_locator"]["resolved"]["column_index"] == 3

    # change_log: two updated entries for the same entity, descending, with the correct actor
    rows = client.get("/changes", headers=editor_headers,
                      params={"entity_kind": "field",
                              "entity_key": "ods_order.user_name"}).json()
    assert [row["op"] for row in rows[:2]] == ["updated", "updated"]
    assert rows[0]["actor"] == "editor_m3"
    assert rows[0]["before"]["src_locator"] != rows[0]["after"]["src_locator"]
    assert rows[1]["before"]["description"] == "User name"

    # Real-file verification failure → 409, the field keeps its previous value
    r = client.patch("/fields/ods_order/user_name", headers=editor_headers,
                     json={"src_locator": {"column": 99}})
    assert r.status_code == 409, r.text
    assert "real-file verification failed" in r.json()["detail"]
    assert "exceeds the source file's column count" in r.json()["detail"]
    ds = client.get("/datasets/ods_order", headers=editor_headers).json()
    assert next(f for f in ds["fields"]
                if f["name"] == "user_name")["src_locator"]["resolved"]["column_index"] == 3

    # Structural validation failure / type mismatch → 409
    r = client.patch("/fields/ods_order/user_name", headers=editor_headers,
                     json={"src_locator": {"column": 0}})
    assert r.status_code == 409 and "structural validation failed" in r.json()["detail"]
    r = client.patch("/fields/ods_order/user_name", headers=editor_headers,
                     json={"src_locator": {"type": "json",
                                           "input": {"json_path": "$"}}})
    assert r.status_code == 409 and "does not match" in r.json()["detail"]

    # Parameters/permissions/non-existence
    assert client.patch("/fields/ods_order/user_name", headers=editor_headers,
                        json={}).status_code == 400
    assert client.patch("/fields/ods_order/user_name", headers=editor_headers,
                        json={"src_locator": None}).status_code == 400
    assert client.patch("/fields/ods_order/no_such", headers=editor_headers,
                        json={"description": "x"}).status_code == 404
    assert client.patch("/fields/ods_order/user_name", headers=viewer_headers,
                        json={"description": "x"}).status_code == 403
    assert client.patch("/fields/ods_order/user_name",
                        json={"description": "x"}).status_code == 401


# ---------- Edge editing ----------

def test_edge_crud_natural_key_and_changes(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)

    # Add a field-level manual edge
    r = client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "user_name",
        "to_dataset": "dim_user", "to_field": "user_name",
        "transform": "lookup", "confidence": 0.8, "note": "manually added edge",
    })
    assert r.status_code == 201, r.text
    edge = r.json()
    edge_id = edge["id"]
    assert isinstance(edge_id, int) and edge["source"] == "manual"
    assert edge["confidence"] == 0.8

    # Duplicate natural key → 409
    r = client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "user_name",
        "to_dataset": "dim_user", "to_field": "user_name"})
    assert r.status_code == 409, r.text

    # Add a table-level manual edge; a duplicate is likewise 409
    table_payload = {"from_dataset": "dwd_order", "to_dataset": "dim_user"}
    r = client.post("/edges", headers=editor_headers, json=table_payload)
    assert r.status_code == 201, r.text
    assert r.json()["from_field"] is None and r.json()["to_field"] is None
    assert isinstance(r.json()["id"], int)
    assert client.post("/edges", headers=editor_headers,
                       json=table_payload).status_code == 409

    # Mixed-field edge / non-existent references → 400 / 404
    for payload in [
        {"from_dataset": "ods_order", "from_field": "order_no",
         "to_dataset": "dim_user", "to_field": None},
        {"from_dataset": "ods_order", "from_field": None,
         "to_dataset": "dim_user", "to_field": "user_name"},
    ]:
        r = client.post("/edges", headers=editor_headers, json=payload)
        assert r.status_code == 400, r.text
        assert "must provide both upstream and downstream fields" in r.json()["detail"]
    assert client.post("/edges", headers=editor_headers, json={
        "from_dataset": "no_such", "to_dataset": "dim_user"}).status_code == 404
    assert client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "no_such",
        "to_dataset": "dim_user", "to_field": "user_name"}).status_code == 404

    # PATCH: change transform/note/confidence and write an updated log
    r = client.patch(f"/edges/{edge_id}", headers=editor_headers,
                     json={"transform": "lookup/cast", "confidence": 0.5,
                           "note": "corrected"})
    assert r.status_code == 200, r.text
    assert r.json()["transform"] == "lookup/cast"
    assert r.json()["confidence"] == 0.5
    assert r.json()["source"] == "manual"

    rows = client.get("/changes", headers=editor_headers,
                      params={"entity_kind": "edge",
                              "entity_key": "ods_order.user_name-->dim_user.user_name"}
                      ).json()
    assert rows[0]["op"] == "updated"
    assert rows[0]["before"]["transform"] == "lookup"
    assert rows[0]["after"]["transform"] == "lookup/cast"
    assert rows[0]["actor"] == "editor_m3"

    # Confidence bounds / empty patch / non-existence
    assert client.patch(f"/edges/{edge_id}", headers=editor_headers,
                        json={"confidence": 1.5}).status_code == 422
    assert client.patch(f"/edges/{edge_id}", headers=editor_headers,
                        json={"confidence": None}).status_code == 400
    assert client.patch(f"/edges/{edge_id}", headers=editor_headers,
                        json={}).status_code == 400
    assert client.patch("/edges/99999", headers=editor_headers,
                        json={"note": "x"}).status_code == 404

    # DELETE an imported table-level edge → 204, write a deleted log, repeated delete 404
    imported_table_edge = _edge_id(
        client, editor_headers, from_dataset="ods_order", from_field=None,
        to_dataset="dwd_order", to_field=None)
    assert client.delete(f"/edges/{imported_table_edge}",
                         headers=editor_headers).status_code == 204
    assert client.delete(f"/edges/{imported_table_edge}",
                         headers=editor_headers).status_code == 404
    rows = client.get("/changes", headers=editor_headers,
                      params={"entity_kind": "edge",
                              "entity_key": "ods_order.*-->dwd_order.*"}).json()
    assert rows[0]["op"] == "deleted"
    assert rows[0]["before"]["transform"] == "table_projection"
    assert rows[0]["after"] is None

    # viewer gets 403 on all write endpoints (role guard precedes target existence checks)
    assert client.post("/edges", headers=viewer_headers,
                       json={"from_dataset": "ods_order",
                             "to_dataset": "dim_user"}).status_code == 403
    assert client.patch(f"/edges/{edge_id}", headers=viewer_headers,
                        json={"note": "x"}).status_code == 403
    assert client.delete(f"/edges/{edge_id}",
                         headers=viewer_headers).status_code == 403


def test_graph_payload_edges_include_unique_id(client):
    headers = login(client)
    _seed(client, headers)
    payload = _subgraph(client, headers)
    ids = [edge["id"] for edge in payload["edges"]]
    assert len(ids) == len(set(ids)) == 2
    assert all(isinstance(edge_id, int) for edge_id in ids)


# ---------- Change history ----------

def test_changes_filter_order_limit_and_permissions(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)

    assert client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "user_name",
        "to_dataset": "dim_user", "to_field": "user_name"}).status_code == 201
    for description in ("first correction", "second correction"):
        assert client.patch("/fields/ods_order/order_no", headers=editor_headers,
                            json={"description": description}).status_code == 200

    rows = client.get("/changes", headers=viewer_headers,
                      params={"entity_kind": "field",
                              "entity_key": "ods_order.order_no"}).json()
    assert len(rows) == 3  # import added + two manual updated
    assert [row["op"] for row in rows[:2]] == ["updated", "updated"]
    assert [row["id"] for row in rows] == sorted(
        (row["id"] for row in rows), reverse=True)
    assert set(rows[0]) == {"id", "op", "before", "after", "actor", "created_at"}
    assert isinstance(rows[0]["before"], dict)
    assert isinstance(rows[0]["after"], dict)

    limited = client.get("/changes", headers=viewer_headers,
                         params={"limit": 1}).json()
    assert len(limited) == 1
    assert limited[0]["id"] == max(row["id"] for row in rows)

    edge_rows = client.get(
        "/changes", headers=viewer_headers,
        params={"entity_kind": "edge",
                "entity_key": "ods_order.user_name-->dim_user.user_name"}).json()
    assert [row["op"] for row in edge_rows] == ["added"]

    # Parameters and authentication
    assert client.get("/changes", headers=viewer_headers,
                      params={"entity_kind": "tag"}).status_code == 422
    assert client.get("/changes", headers=viewer_headers,
                      params={"limit": 0}).status_code == 422
    assert client.get("/changes").status_code == 401


# ---------- Version tags ----------

def test_version_tags_create_list_and_diff(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)

    before_count = _db_count("SELECT COUNT(*) FROM change_log")
    base_seq = _max_change_id()
    r = client.post("/version-tags", headers=editor_headers,
                    json={"name": "base", "note": "baseline"})
    assert r.status_code == 201, r.text
    tag = r.json()
    assert tag["name"] == "base" and tag["note"] == "baseline"
    assert tag["change_seq"] == base_seq
    assert tag["created_by"] == "editor_m3"
    # Tag creation leaves a trail via created_by and does not write change_log (avoiding rollback-deletes-tag)
    assert _db_count("SELECT COUNT(*) FROM change_log") == before_count

    assert client.post("/version-tags", headers=editor_headers,
                       json={"name": "base"}).status_code == 409
    assert client.post("/version-tags", headers=viewer_headers,
                       json={"name": "forbidden"}).status_code == 403

    base_list = client.get("/version-tags", headers=viewer_headers).json()
    assert [row["name"] for row in base_list] == ["base"]

    # After the tag: 1 field update + 1 new edge + 1 imported-edge deletion
    assert client.patch("/fields/ods_order/order_no", headers=editor_headers,
                        json={"description": "corrected"}).status_code == 200
    r = client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "user_name",
        "to_dataset": "dim_user", "to_field": "user_name"})
    assert r.status_code == 201, r.text
    imported_table_edge = _edge_id(
        client, admin_headers, from_dataset="ods_order", from_field=None,
        to_dataset="dwd_order", to_field=None)
    assert client.delete(f"/edges/{imported_table_edge}",
                         headers=editor_headers).status_code == 204

    r = client.post("/version-tags", headers=editor_headers,
                    json={"name": "next"})
    assert r.status_code == 201, r.text
    assert r.json()["change_seq"] > base_seq
    assert [row["name"] for row in
            client.get("/version-tags", headers=viewer_headers).json()] == ["base", "next"]

    diff = client.get("/version-tags/diff", headers=viewer_headers,
                      params={"from": "base", "to": "next"}).json()
    assert diff["summary"] == {"added": 1, "updated": 1, "deleted": 1}
    ops = {(item["entity_kind"], item["entity_key"]): item["op"]
           for item in diff["items"]}
    assert ops == {
        ("field", "ods_order.order_no"): "updated",
        ("edge", "ods_order.user_name-->dim_user.user_name"): "added",
        ("edge", "ods_order.*-->dwd_order.*"): "deleted",
    }
    for item in diff["items"]:
        if item["op"] == "added":
            assert item["before"] is None and item["after"] is not None
        elif item["op"] == "deleted":
            assert item["before"] is not None and item["after"] is None
        else:
            assert item["before"]["description"] == "Order number"
            assert item["after"]["description"] == "corrected"

    # Non-existent tags / reversed order
    assert client.get("/version-tags/diff", headers=viewer_headers,
                      params={"from": "no_such", "to": "next"}).status_code == 404
    assert client.get("/version-tags/diff", headers=viewer_headers,
                      params={"from": "next", "to": "base"}).status_code == 400


def test_rollback_to_tag_is_idempotent_and_keeps_annotations(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_m3", "editor")
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    source_ids = _seed(client, admin_headers)

    base_seq = _max_change_id()
    r = client.post("/version-tags", headers=admin_headers,
                    json={"name": "base", "note": "rollback baseline"})
    assert r.status_code == 201, r.text
    baseline = client.get("/lineage/snapshot", headers=admin_headers).json()

    imported_field_edge = _edge_id(
        client, admin_headers, from_dataset="ods_order", from_field="order_no",
        to_dataset="dwd_order", to_field="order_no")
    imported_table_edge = _edge_id(
        client, admin_headers, from_dataset="ods_order", from_field=None,
        to_dataset="dwd_order", to_field=None)

    # Changes after the tag: field updated / edge added / edge updated / edge deleted / import batch added
    assert client.patch("/fields/ods_order/user_name", headers=editor_headers,
                        json={"description": "broken", "src_locator": {"column": 3}}
                        ).status_code == 200
    r = client.post("/edges", headers=editor_headers, json={
        "from_dataset": "ods_order", "from_field": "user_name",
        "to_dataset": "dim_user", "to_field": "user_name"})
    assert r.status_code == 201, r.text
    assert client.patch(f"/edges/{imported_field_edge}", headers=editor_headers,
                        json={"transform": "broken", "confidence": 0.3}
                        ).status_code == 200
    assert client.delete(f"/edges/{imported_table_edge}",
                         headers=editor_headers).status_code == 204
    _import_phone_field(client, admin_headers, source_ids)
    # The annotation is written after the tag: no change_log and not deleted by rollback
    assert client.post("/annotations", headers=editor_headers,
                       json={"target_kind": "dataset", "target_id": "ods_order",
                             "body": "keep after rollback"}).status_code == 201

    expected_reverted = _max_change_id() - base_seq
    assert expected_reverted == 5
    log_count_before_rollback = _db_count("SELECT COUNT(*) FROM change_log")

    # Only admin can roll back
    assert client.post("/version-tags/base/rollback",
                       headers=editor_headers).status_code == 403
    assert client.post("/version-tags/base/rollback",
                       headers=viewer_headers).status_code == 403
    assert client.post("/version-tags/no_such/rollback",
                       headers=admin_headers).status_code == 404

    r = client.post("/version-tags/base/rollback", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"reverted": expected_reverted}

    # Data returns to the tag point; field locator/description restored as well
    assert client.get("/lineage/snapshot", headers=admin_headers).json() == baseline
    ds = client.get("/datasets/ods_order", headers=admin_headers).json()
    assert [f["name"] for f in ds["fields"]] == ["order_no", "user_name"]
    user_name = next(f for f in ds["fields"] if f["name"] == "user_name")
    assert user_name["description"] == "User name"
    assert user_name["src_locator"]["resolved"]["column_index"] == 2
    payload = _subgraph(client, admin_headers)
    field_edge = next(e for e in payload["edges"]
                      if e["from_field"] == "order_no" and e["to_field"] == "order_no")
    assert field_edge["transform"] == "trim/cast"
    assert field_edge["confidence"] == 1.0
    assert any(e["from_field"] is None and e["to_field"] is None
               for e in payload["edges"])

    # The rollback itself does not write change_log (otherwise repeated rollbacks
    # would reverse rollback logs); the audit goes to rollback_record
    assert _db_count("SELECT COUNT(*) FROM change_log") == log_count_before_rollback
    assert _db_count("SELECT COUNT(*) FROM rollback_record") == 1
    annotations = client.get("/annotations", headers=viewer_headers,
                             params={"target_kind": "dataset",
                                     "target_id": "ods_order"}).json()
    assert [row["body"] for row in annotations] == ["keep after rollback"]

    # Repeated rollback is safe: already-reversed logs are skipped, reverted=0,
    # state unchanged, and another audit row is appended
    r = client.post("/version-tags/base/rollback", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"reverted": 0}
    assert client.get("/lineage/snapshot", headers=admin_headers).json() == baseline
    assert _db_count("SELECT COUNT(*) FROM rollback_record") == 2
    assert _db_count(
        "SELECT COUNT(*) FROM rollback_record WHERE actor=? AND tag_name=?",
        ("admin", "base")) == 2


# ---------- Permission matrix ----------

def test_viewer_read_only_on_all_m3_endpoints(client):
    admin_headers = login(client)
    viewer_headers = create_user(client, admin_headers, "viewer_m3", "viewer")
    _seed(client, admin_headers)

    assert client.get("/annotations", headers=viewer_headers).status_code == 200
    assert client.get("/changes", headers=viewer_headers).status_code == 200
    assert client.get("/version-tags", headers=viewer_headers).status_code == 200
    assert client.get("/version-tags/diff", headers=viewer_headers,
                      params={"from": "a", "to": "b"}).status_code == 404

    assert client.post("/annotations", headers=viewer_headers, json={
        "target_kind": "dataset", "target_id": "ods_order", "body": "x"}).status_code == 403
    assert client.patch("/fields/ods_order/order_no", headers=viewer_headers,
                        json={"description": "x"}).status_code == 403
    assert client.post("/edges", headers=viewer_headers, json={
        "from_dataset": "ods_order", "to_dataset": "dim_user"}).status_code == 403
    assert client.patch("/edges/1", headers=viewer_headers,
                        json={"note": "x"}).status_code == 403
    assert client.delete("/edges/1", headers=viewer_headers).status_code == 403
    assert client.post("/version-tags", headers=viewer_headers,
                       json={"name": "x"}).status_code == 403
    assert client.post("/version-tags/x/rollback",
                       headers=viewer_headers).status_code == 403
