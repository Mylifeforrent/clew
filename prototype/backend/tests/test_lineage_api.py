"""M2 acceptance: recursive CTE subgraph, field-seed semantics, source preview for all three formats.

The chain is fixed as d0→d1→d2→d3→d4, and each hop contains one field-level edge and one
table-level edge; all data is ingested through the official upload + import APIs.
"""

import json
import sqlite3

from lineagelite.config import db_path

from tests.conftest import create_user, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes

CHAIN = ["d0", "d1", "d2", "d3", "d4"]

# Matches the headers of order_xlsx_bytes in tests/fixtures.py
ORDER_XLSX_HEADER_PATH = ["Product Info", "Order No"]


def _chain_manifest() -> dict:
    datasets = []
    for index, dataset_id in enumerate(CHAIN):
        locator = ({"sheet": "Orders", "header_path": ORDER_XLSX_HEADER_PATH,
                    "header_rows": 2, "row_start": 3}
                   if index == 0 else
                   {"sheet": "Orders", "column": "C", "row_start": 3})
        datasets.append({
            "dataset_id": dataset_id, "dataset_name": f"Chain {dataset_id}",
            "field_name": "order_no", "field_type": "STRING",
            "src_file": "order_details.xlsx", "src_type": "xlsx",
            "src_locator": locator, "description": "Order No",
        })
        datasets.append({
            "dataset_id": dataset_id, "dataset_name": f"Chain {dataset_id}",
            "field_name": "user_name", "field_type": "STRING",
            "src_file": "users.csv", "src_type": "csv",
            "src_locator": {"column": 2}, "description": "User name",
        })
    datasets.append({
        "dataset_id": "d0", "dataset_name": "Chain d0",
        "field_name": "ext_order_no", "field_type": "STRING",
        "src_file": "source.json", "src_type": "json",
        "src_locator": {"json_path": "$.data.items[*].order_no"},
        "description": "External order number",
    })

    lineage = []
    for i in range(len(CHAIN) - 1):
        lineage.append({
            "from_dataset": CHAIN[i], "from_field": "order_no",
            "to_dataset": CHAIN[i + 1], "to_field": "order_no",
            "transform": "trim/cast", "confidence": 1.0, "note": "field-level",
        })
        lineage.append({
            "from_dataset": CHAIN[i], "from_field": None,
            "to_dataset": CHAIN[i + 1], "to_field": None,
            "transform": "table_projection", "confidence": 1.0, "note": "table-level",
        })
    return {"datasets": datasets, "lineage": lineage}


def _upload_sources(client, headers) -> list[dict]:
    return upload(client, headers, [
        ("order_details.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])


def _import_manifest(client, headers, manifest: dict, source_files: list[dict]):
    # Use the real IDs from the upload response to avoid depending on the temp DB's autoincrement order
    source_file_ids = ",".join(str(f["id"]) for f in source_files)
    return client.post(
        "/import", headers=headers,
        data={"format": "json", "source_file_ids": source_file_ids},
        files={"manifest": ("manifest.json",
                            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                            "application/json")})


def _seed_chain(client, headers) -> None:
    source_files = _upload_sources(client, headers)
    r = _import_manifest(client, headers, _chain_manifest(), source_files)
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["rejected"] == 0, r.text


def _subgraph(client, headers, **params):
    return client.get("/lineage/subgraph", headers=headers, params=params)


def _dataset_ids(payload: dict) -> list[str]:
    return [d["id"] for d in payload["datasets"]]


# ---------- Dataset seed: hops and direction ----------

def test_dataset_seed_hops_3_covers_whole_chain(client):
    headers = login(client)
    _seed_chain(client, headers)

    r = _subgraph(client, headers, dataset="d1", hops=3)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert _dataset_ids(payload) == CHAIN  # 3 hops from d1 exactly covers d0..d4
    assert len(payload["edges"]) == 8  # 4 field-level + 4 table-level
    assert all(d["fields"] for d in payload["datasets"])


def test_dataset_seed_hops_1_and_direction_up(client):
    headers = login(client)
    _seed_chain(client, headers)

    r = _subgraph(client, headers, dataset="d1", hops=1)
    assert r.status_code == 200, r.text
    assert _dataset_ids(r.json()) == ["d0", "d1", "d2"]

    r = _subgraph(client, headers, dataset="d1", hops=3, direction="up")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert _dataset_ids(payload) == ["d0", "d1"]  # upstream only reaches d0
    assert len(payload["edges"]) == 2  # field-level + table-level of d0→d1


# ---------- Field seed: field-level edge propagation + table-level full connectivity ----------

def test_field_seed_propagates_along_field_edges(client):
    headers = login(client)
    _seed_chain(client, headers)

    up = _subgraph(client, headers, dataset="d1", field="order_no",
                   hops=1, direction="up")
    assert up.status_code == 200, up.text
    assert _dataset_ids(up.json()) == ["d0", "d1"]

    down = _subgraph(client, headers, dataset="d1", field="order_no",
                     hops=2, direction="down")
    assert down.status_code == 200, down.text
    assert _dataset_ids(down.json()) == ["d1", "d2", "d3"]


def test_field_seed_table_edge_connects_all_fields(client):
    headers = login(client)
    _seed_chain(client, headers)

    # user_name has no field-level edge; the d1→d0 table-level edge should fully connect d0's fields
    r = _subgraph(client, headers, dataset="d1", field="user_name",
                  hops=1, direction="up")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert _dataset_ids(payload) == ["d0", "d1"]
    d0 = next(d for d in payload["datasets"] if d["id"] == "d0")
    assert [f["name"] for f in d0["fields"]] == ["ext_order_no", "order_no", "user_name"]

    # All edges between closure datasets (including table-level edges) must be returned
    table_edges = [e for e in payload["edges"]
                   if e["from_field"] is None and e["to_field"] is None]
    assert len(table_edges) == 1
    assert table_edges[0]["from_dataset"] == "d0"
    assert table_edges[0]["to_dataset"] == "d1"


def test_graph_payload_shape_matches_contract(client):
    headers = login(client)
    _seed_chain(client, headers)

    payload = _subgraph(client, headers, dataset="d1", hops=1).json()
    for dataset in payload["datasets"]:
        assert set(dataset) == {"id", "name", "fields"}
        for field in dataset["fields"]:
            assert set(field) == {"name", "field_type", "description",
                                  "src_locator", "source_file"}
            assert set(field["src_locator"]) == {"type", "input", "resolved"}
            assert set(field["source_file"]) == {"id", "original_name"}

    for edge in payload["edges"]:
        assert set(edge) == {"id", "from_dataset", "from_field", "to_dataset",
                             "to_field", "transform", "confidence", "source", "note"}
        assert isinstance(edge["id"], int)  # M3: manual edit/delete locates edges by primary key
        assert edge["source"] == "imported"
        assert 0 <= edge["confidence"] <= 1

    sample = next(f for d in payload["datasets"] if d["id"] == "d0"
                  for f in d["fields"] if f["name"] == "order_no")
    assert sample["src_locator"]["type"] == "xlsx"
    assert sample["src_locator"]["input"]["header_path"] == ORDER_XLSX_HEADER_PATH
    assert sample["src_locator"]["resolved"]["column_index"] == 3
    assert sample["source_file"]["original_name"] == "order_details.xlsx"


# ---------- Source preview: csv / xlsx / json ----------

def _seed_preview_sources(client, headers) -> None:
    source_files = _upload_sources(client, headers)
    manifest = {"datasets": [
        {"dataset_id": "src_demo", "dataset_name": "Preview Sample",
         "field_name": "order_no", "field_type": "STRING",
         "src_file": "order_details.xlsx", "src_type": "xlsx",
         "src_locator": {"sheet": "Orders", "header_path": ORDER_XLSX_HEADER_PATH,
                         "header_rows": 2, "row_start": 3},
         "description": "XLSX multi-level header field"},
        {"dataset_id": "src_demo", "dataset_name": "Preview Sample",
         "field_name": "user_name", "field_type": "STRING",
         "src_file": "users.csv", "src_type": "csv",
         "src_locator": {"column": 2}, "description": "CSV field"},
        {"dataset_id": "src_demo", "dataset_name": "Preview Sample",
         "field_name": "ext_order_no", "field_type": "STRING",
         "src_file": "source.json", "src_type": "json",
         "src_locator": {"json_path": "$.data.items[*].order_no"},
         "description": "JSONPath field"},
    ], "lineage": []}
    r = _import_manifest(client, headers, manifest, source_files)
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["rejected"] == 0, r.text


def test_preview_csv(client):
    headers = login(client)
    _seed_preview_sources(client, headers)

    r = client.get("/fields/src_demo/user_name/preview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file"]["original_name"] == "users.csv"
    assert len(body["file"]["sha256"]) == 64  # sha256 content-addressing basis
    assert body["file"]["src_type"] == "csv"
    assert body["verification"]["status"] == "passed"
    assert body["verification"]["version_no"] == 1
    assert body["locator"]["type"] == "csv"
    preview = body["preview"]
    assert preview["header"] == ["user_id", "user_name", "phone"]
    assert preview["column_index"] == 2
    assert preview["rows"] == [["1", "Alice", "138*"], ["2", "Bob", "139*"]]


def test_preview_xlsx_with_merged_multi_header(client):
    headers = login(client)
    _seed_preview_sources(client, headers)

    r = client.get("/fields/src_demo/order_no/preview", headers=headers)
    assert r.status_code == 200, r.text
    preview = r.json()["preview"]
    assert preview["sheet"] == "Orders"
    assert "B1:F1" in preview["merged_ranges"]
    assert preview["column_index"] == 3  # Order No is in column C
    assert preview["row_start"] == 3
    assert len(preview["header_rows"]) == 2
    assert preview["rows"] == [
        [None, "S001", "SO-1001", 2, 9.9, 19.8, 5],
        [None, "S002", "SO-1002", 1, 59.0, 59.0, 0],
    ]


def test_preview_json(client):
    headers = login(client)
    _seed_preview_sources(client, headers)

    r = client.get("/fields/src_demo/ext_order_no/preview", headers=headers)
    assert r.status_code == 200, r.text
    preview = r.json()["preview"]
    assert preview["json_path"] == "$.data.items[*].order_no"
    assert preview["hits"] == 2
    assert preview["samples"] == ["SO-1001", "SO-1002"]


def test_preview_404_and_stale_locator_409(client):
    headers = login(client)
    _seed_preview_sources(client, headers)

    assert client.get("/fields/src_demo/nope/preview",
                      headers=headers).status_code == 404
    assert client.get("/fields/no_such/nope/preview",
                      headers=headers).status_code == 404

    # Simulate a source file revision where the sheet no longer exists (the materialized locator result remains)
    stale = {"type": "xlsx",
             "input": {"sheet": "deleted_sheet", "column": "C"},
             "resolved": {"column_index": 3}}
    conn = sqlite3.connect(db_path())
    conn.execute(
        "UPDATE field SET src_locator=? WHERE dataset_id='src_demo' AND name='order_no'",
        (json.dumps(stale, ensure_ascii=False),))
    conn.commit()
    conn.close()

    r = client.get("/fields/src_demo/order_no/preview", headers=headers)
    assert r.status_code == 409, r.text
    assert "no longer exists" in r.json()["detail"]


def test_preview_stale_row_range_409(client):
    headers = login(client)
    _seed_preview_sources(client, headers)

    def set_locator(locator: dict) -> None:
        conn = sqlite3.connect(db_path())
        conn.execute(
            "UPDATE field SET src_locator=? WHERE dataset_id='src_demo' AND name='order_no'",
            (json.dumps(locator, ensure_ascii=False),))
        conn.commit()
        conn.close()

    # row_start exceeds the worksheet's total row count (fixture: 2 header rows + 2 data rows)
    set_locator({"type": "xlsx",
                 "input": {"sheet": "Orders", "column": "C", "row_start": 99},
                 "resolved": {"column_index": 3, "row_start": 99}})
    r = client.get("/fields/src_demo/order_no/preview", headers=headers)
    assert r.status_code == 409, r.text
    assert "row_start=99" in r.json()["detail"]

    # row_end exceeds the worksheet's total row count
    set_locator({"type": "xlsx",
                 "input": {"sheet": "Orders", "column": "C",
                           "row_start": 3, "row_end": 99},
                 "resolved": {"column_index": 3, "row_start": 3, "row_end": 99}})
    r = client.get("/fields/src_demo/order_no/preview", headers=headers)
    assert r.status_code == 409, r.text
    assert "row_end=99" in r.json()["detail"]


# ---------- Authentication and parameter validation ----------

def test_lineage_and_preview_require_auth(client):
    headers = login(client)
    _seed_chain(client, headers)

    assert client.get("/lineage/subgraph", params={"dataset": "d1"}).status_code == 401
    assert client.get("/fields/d0/order_no/preview").status_code == 401


def test_hops_out_of_range_rejected(client):
    headers = login(client)
    _seed_chain(client, headers)

    assert _subgraph(client, headers, dataset="d1", hops=6).status_code == 422
    assert _subgraph(client, headers, dataset="d1", hops=0).status_code == 422
    assert _subgraph(client, headers, dataset="d1",
                     direction="sideways").status_code == 422


def test_unknown_seed_404(client):
    headers = login(client)
    _seed_chain(client, headers)

    assert _subgraph(client, headers, dataset="nope", hops=1).status_code == 404
    assert _subgraph(client, headers, dataset="d1", field="nope",
                     hops=1).status_code == 404


def test_viewer_can_read_lineage_and_preview(client):
    admin_headers = login(client)
    _seed_chain(client, admin_headers)
    viewer_headers = create_user(client, admin_headers, "viewer_m2", "viewer")

    assert _subgraph(client, viewer_headers, dataset="d1",
                     hops=1).status_code == 200
    assert client.get("/fields/d0/order_no/preview",
                      headers=viewer_headers).status_code == 200
