"""Acceptance: import v2 then roll back by batch → restores the v1 state; repeated rollback is rejected."""

import json

from tests.conftest import csv_bytes, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes


def _seed_and_import_v1(client, headers) -> int:
    upload(client, headers, [
        ("orders.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])
    ds_rows = [
        ["dataset_id", "dataset_name", "field_name", "field_type", "src_file",
         "src_type", "src_locator", "description"],
        ["ods_raw", "Order Details", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                     "header_rows": 2, "row_start": 3}), "Order number"],
        ["dwd_order", "Order Wide Table", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "column": "C", "row_start": 3}), "Wide-table order number"],
        ["dwd_order", "Order Wide Table", "user_name", "STRING", "users.csv", "csv",
         json.dumps({"column": 2}), "User name"],
    ]
    edge_rows = [
        ["from_dataset", "from_field", "to_dataset", "to_field", "transform",
         "confidence", "note"],
        ["ods_raw", "order_no", "dwd_order", "order_no", "trim/cast", "1.0", ""],
    ]
    r = client.post("/import", headers=headers,
                    data={"format": "csv", "source_file_ids": "1,2,3"},
                    files={
                        "manifest_datasets": ("datasets.csv", csv_bytes(ds_rows), "text/csv"),
                        "manifest_lineage": ("lineage.csv", csv_bytes(edge_rows), "text/csv"),
                    })
    assert r.status_code == 201, r.text
    return r.json()["batch_id"]


def _import_v2(client, headers) -> int:
    manifest = {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
            {"dataset_id": "dwd_order", "field_name": "order_no", "field_type": "STRING",
             "src_file": "orders.xlsx", "src_type": "xlsx",
             "src_locator": {"sheet": "Orders", "column": "C", "row_start": 3},
             "description": "v2 corrected description"},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_name",
             "to_dataset": "dwd_order", "to_field": "user_name", "transform": "join"},
        ],
    }
    r = client.post("/import", headers=headers,
                    data={"format": "json", "source_file_ids": "1,2,3"},
                    files={"manifest": ("manifest.json",
                                        json.dumps(manifest, ensure_ascii=False).encode(),
                                        "application/json")})
    assert r.status_code == 201, r.text
    return r.json()["batch_id"]


def test_rollback_v2_restores_v1(client):
    headers = login(client)
    batch1 = _seed_and_import_v1(client, headers)
    snap_v1 = client.get("/lineage/snapshot", headers=headers).json()

    batch2 = _import_v2(client, headers)
    snap_v2 = client.get("/lineage/snapshot", headers=headers).json()
    assert len(snap_v2["fields"]) == len(snap_v1["fields"]) + 2  # ods_user +2 fields
    dwd = client.get("/datasets/dwd_order", headers=headers).json()
    assert next(f for f in dwd["fields"]
                if f["name"] == "order_no")["description"] == "v2 corrected description"

    r = client.post(f"/import/batches/{batch2}/rollback", headers=headers)
    assert r.status_code == 200, r.text
    snap_restored = client.get("/lineage/snapshot", headers=headers).json()
    assert snap_restored == snap_v1

    # Repeated rollback is rejected
    assert client.post(f"/import/batches/{batch2}/rollback",
                       headers=headers).status_code == 409
    # v1 is unaffected and can still be operated on
    assert client.get(f"/import/batches/{batch1}",
                      headers=headers).json()["rolled_back_at"] is None


def test_rollback_unknown_batch_404(client):
    headers = login(client)
    assert client.post("/import/batches/999/rollback", headers=headers).status_code == 404


def test_tag_rollback_repeat_is_noop_and_reports_zero(client):
    """Repeated rollback to the same tag: no side effects and reverted=0 (API contract §12.4)."""
    headers = login(client)
    _seed_and_import_v1(client, headers)

    # Baseline tag: anchors the state after importing v1
    r = client.post("/version-tags", headers=headers,
                    json={"name": "base", "note": "baseline"})
    assert r.status_code == 201, r.text

    # Write two kinds of reversible change: add a manual edge + delete an imported edge
    r = client.post("/edges", headers=headers,
                    json={"from_dataset": "ods_raw", "from_field": "order_no",
                          "to_dataset": "dwd_order", "to_field": "user_name",
                          "transform": "join", "confidence": 0.9})
    assert r.status_code == 201, r.text
    sub = client.get("/lineage/subgraph?dataset=ods_raw&hops=1",
                     headers=headers).json()
    imported_edge_id = next(
        e["id"] for e in sub["edges"]
        if e["source"] == "imported"
        and e["from_dataset"] == "ods_raw" and e["to_dataset"] == "dwd_order")
    assert client.delete(f"/edges/{imported_edge_id}",
                         headers=headers).status_code == 204

    # First rollback: both logs are reversed
    r = client.post("/version-tags/base/rollback", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["reverted"] == 2
    snap_base = client.get("/lineage/snapshot", headers=headers).json()

    # Repeated rollback: all logs are already covered, reverted=0 and state unchanged
    r = client.post("/version-tags/base/rollback", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["reverted"] == 0
    assert client.get("/lineage/snapshot", headers=headers).json() == snap_base

    # Delete the baseline edge again after rollback; rolling back again reverses
    # only the new log (the delete-then-rollback cycle is repeatable)
    sub = client.get("/lineage/subgraph?dataset=ods_raw&hops=1",
                     headers=headers).json()
    edge_id = next(e["id"] for e in sub["edges"]
                   if e["from_dataset"] == "ods_raw")
    assert client.delete(f"/edges/{edge_id}", headers=headers).status_code == 204
    r = client.post("/version-tags/base/rollback", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["reverted"] == 1
    assert client.get("/lineage/snapshot", headers=headers).json() == snap_base
    assert client.post("/version-tags/base/rollback",
                       headers=headers).json()["reverted"] == 0
