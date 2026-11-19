"""Acceptance: import in all three formats + locator real-file verification (including XLSX merged cells/multi-level headers)."""

import io
import json

from openpyxl import Workbook

from tests.conftest import csv_bytes, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes


def _seed_sources(client, headers) -> None:
    upload(client, headers, [
        ("orders.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])


def _import_csv(client, headers, ds_rows, edge_rows):
    return client.post("/import", headers=headers,
                       data={"format": "csv", "source_file_ids": "1,2,3"},
                       files={
                           "manifest_datasets": ("datasets.csv", csv_bytes(ds_rows), "text/csv"),
                           "manifest_lineage": ("lineage.csv", csv_bytes(edge_rows), "text/csv"),
                       })


def test_csv_import_with_multiheader_xlsx_and_bad_locator(client):
    headers = login(client)
    _seed_sources(client, headers)

    ds_rows = [
        ["dataset_id", "dataset_name", "field_name", "field_type", "src_file",
         "src_type", "src_locator", "description"],
        ["ods_raw", "Order Details", "order_id", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Product ID"],
                     "header_rows": 2, "row_start": 3}), "Product ID"],
        ["ods_raw", "Order Details", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                     "header_rows": 2, "row_start": 3}), "Order number"],
        ["ods_raw", "Order Details", "amount", "DECIMAL", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Amount"],
                     "header_rows": 2, "row_start": 3}), "Amount"],
        ["ods_raw", "Order Details", "bad_field", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Missing"], "header_rows": 2}),
         "Bad locator"],
        ["dwd_order", "Order Wide Table", "order_no", "STRING", "orders.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "column": "C", "row_start": 3}), "Wide-table order number"],
        ["dwd_order", "Order Wide Table", "user_name", "STRING", "users.csv", "csv",
         json.dumps({"column": 2}), "User name"],
    ]
    edge_rows = [
        ["from_dataset", "from_field", "to_dataset", "to_field", "transform",
         "confidence", "note"],
        ["ods_raw", "order_id", "dwd_order", "order_no", "trim/cast", "1.0", "Same-source transform"],
        ["ods_raw", "", "dwd_order", "", "", "", ""],
    ]
    r = _import_csv(client, headers, ds_rows, edge_rows)
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    assert report["summary"] == {"total": 8, "ok": 7, "merged": 0, "rejected": 1}
    rejected = [i for i in report["items"] if i["status"] == "rejected"]
    assert rejected[0]["ref"] == "ods_raw.bad_field"
    assert "real-file verification failed" in rejected[0]["reason"]

    # The field with the bad locator is not persisted; correct fields carry the materialized parse result
    ods = client.get("/datasets/ods_raw", headers=headers).json()
    assert [f["name"] for f in ods["fields"]] == ["amount", "order_id", "order_no"]
    order_no = next(f for f in ods["fields"] if f["name"] == "order_no")
    resolved = order_no["src_locator"]["resolved"]
    assert resolved["column_index"] == 3  # order number is in column C
    assert resolved["merged_anchors"] == [
        {"value": "Product Info", "anchor": "B1", "range": "B1:F1"}]

    dwd = client.get("/datasets/dwd_order", headers=headers).json()
    simple = next(f for f in dwd["fields"] if f["name"] == "order_no")
    assert simple["src_locator"]["input"] == {"sheet": "Orders", "column": "C", "row_start": 3}
    assert simple["src_locator"]["resolved"]["column_index"] == 3


def test_xlsx_manifest_import(client):
    headers = login(client)
    _seed_sources(client, headers)

    wb = Workbook()
    ds = wb.active
    ds.title = "datasets"
    ds.append(["dataset_id", "dataset_name", "field_name", "field_type",
               "src_file", "src_type", "src_locator", "description"])
    ds.append(["ods_raw", "Order Details", "order_no", "STRING", "orders.xlsx", "xlsx",
               json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                           "header_rows": 2, "row_start": 3}), "Order number"])
    ds.append(["ods_raw", "Order Details", "qty", "INTEGER", "orders.xlsx", "xlsx",
               json.dumps({"sheet": "Orders", "column": "D", "row_start": 3}), "Quantity"])
    ds.append(["ods_raw", "Order Details", "broken", "STRING", "orders.xlsx", "xlsx",
               json.dumps({"sheet": "Missing Sheet", "column": "A"}), "Wrong sheet"])
    lineage = wb.create_sheet("lineage")
    lineage.append(["from_dataset", "from_field", "to_dataset", "to_field",
                    "transform", "confidence", "note"])
    lineage.append(["ods_raw", "order_no", "ods_raw", "qty", "derive", "1.0", ""])
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post("/import", headers=headers,
                    data={"format": "xlsx", "source_file_ids": "1,2,3"},
                    files={"manifest": ("manifest.xlsx", buf.getvalue(),
                                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    assert report["summary"] == {"total": 4, "ok": 3, "merged": 0, "rejected": 1}

    ods = client.get("/datasets/ods_raw", headers=headers).json()
    assert [f["name"] for f in ods["fields"]] == ["order_no", "qty"]
    assert ods["fields"][1]["src_locator"]["resolved"]["column_index"] == 4


def test_json_manifest_import(client):
    headers = login(client)
    _seed_sources(client, headers)

    manifest = {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "ext_order_no",
             "field_type": "STRING", "src_file": "source.json", "src_type": "json",
             "src_locator": {"json_path": "$.data.items[*].order_no"}},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name", "transform": "lookup"},
        ],
    }
    r = client.post("/import", headers=headers,
                    data={"format": "json", "source_file_ids": "1,2,3"},
                    files={"manifest": ("manifest.json", json.dumps(manifest, ensure_ascii=False).encode(),
                                        "application/json")})
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    assert report["summary"] == {"total": 4, "ok": 4, "merged": 0, "rejected": 0}

    ods = client.get("/datasets/ods_user", headers=headers).json()
    ext = next(f for f in ods["fields"] if f["name"] == "ext_order_no")
    assert ext["src_locator"]["resolved"]["hits"] == 2  # JSONPath hit count


def test_manifest_missing_sheet_rejected(client):
    headers = login(client)
    _seed_sources(client, headers)
    wb = Workbook()
    wb.active.title = "wrong"
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/import", headers=headers,
                    data={"format": "xlsx", "source_file_ids": "1"},
                    files={"manifest": ("m.xlsx", buf.getvalue(),
                                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 400
    assert "datasets" in r.json()["detail"]
