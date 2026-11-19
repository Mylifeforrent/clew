"""Acceptance: roll back a v2 import by batch → restore the v1 state; repeated rollback is rejected."""

import json

from tests.conftest import csv_bytes, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes


def _seed_and_import_v1(client, headers) -> int:
    upload(client, headers, [
        ("order_details.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])
    ds_rows = [
        ["dataset_id", "dataset_name", "field_name", "field_type", "src_file",
         "src_type", "src_locator", "description"],
        ["ods_raw", "Order Details", "order_no", "STRING", "order_details.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                     "header_rows": 2, "row_start": 3}), "Order No"],
        ["dwd_order", "Order Wide Table", "order_no", "STRING", "order_details.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "column": "C", "row_start": 3}), "Wide table order number"],
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
             "src_file": "order_details.xlsx", "src_type": "xlsx",
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
    # v1 is unaffected and can continue to be used
    assert client.get(f"/import/batches/{batch1}",
                      headers=headers).json()["rolled_back_at"] is None


def test_rollback_unknown_batch_404(client):
    headers = login(client)
    assert client.post("/import/batches/999/rollback", headers=headers).status_code == 404
