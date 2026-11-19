"""M2 demo data: 5 datasets and a 4-hop lineage chain (design §9 M2 acceptance sample).

Run with::

    cd backend && uv run python -m clew.seed_demo

Generates csv / xlsx (with merged-cell multi-level headers) / json source files
on the fly, registers them through the upload service (sha256 dedup), then
imports them through the real path ``read_json_manifest`` + ``run_import``.
Re-running detects complete demo data and skips, keeping it idempotent.
"""

import csv as csvmod
import io
import json
import sys
from datetime import UTC, datetime

from openpyxl import Workbook

from .config import get_settings
from .db import get_db, init_db
from .import_service import run_import
from .manifest import read_json_manifest
from .routes.files import store_upload
from .security import hash_password

DEMO_DATASET_IDS = ("d0", "d1", "d2", "d3", "d4")

# (dataset_id, dataset_name, [(field_name, field_type, src_file, src_type,
#                              src_locator, description)])
DEMO_DATASETS = [
    ("d0", "Raw Orders", [
        ("order_id", "STRING", "d0_orders.csv", "csv", {"header": "order_id"}, "Order number"),
        ("amount", "DECIMAL", "d0_orders.csv", "csv", {"header": "amount"}, "Order amount"),
        ("region", "STRING", "d0_orders.csv", "csv", {"header": "region"}, "Sales region"),
    ]),
    ("d1", "Cleaned Orders", [
        ("order_id", "STRING", "d1_orders.xlsx", "xlsx",
         {"sheet": "Orders", "header_path": ["Order Info", "Order No"],
          "header_rows": 2, "row_start": 3}, "Cleaned order number"),
        ("amount", "DECIMAL", "d1_orders.xlsx", "xlsx",
         {"sheet": "Orders", "header_path": ["Order Info", "Amount"],
          "header_rows": 2, "row_start": 3}, "Cleaned amount"),
        ("region", "STRING", "d1_orders.xlsx", "xlsx",
         {"sheet": "Orders", "header_path": ["Order Info", "Region"],
          "header_rows": 2, "row_start": 3}, "Normalized region"),
    ]),
    ("d2", "Order Details", [
        ("order_id", "STRING", "d2_orders.json", "json",
         {"json_path": "$.data.orders[*].order_id"}, "Detail order number"),
        ("amount", "DECIMAL", "d2_orders.json", "json",
         {"json_path": "$.data.orders[*].amount"}, "Detail amount"),
        ("region", "STRING", "d2_orders.json", "json",
         {"json_path": "$.data.orders[*].region"}, "Detail region"),
    ]),
    ("d3", "Daily Summary", [
        ("order_id", "STRING", "d3_daily.csv", "csv", {"header": "order_id"}, "Summary order number"),
        ("amount", "DECIMAL", "d3_daily.csv", "csv", {"header": "amount"}, "Daily summary amount"),
        ("region", "STRING", "d3_daily.csv", "csv", {"header": "region"}, "Summary region"),
    ]),
    ("d4", "Reports", [
        ("order_id", "STRING", "d4_report.json", "json",
         {"json_path": "$.report.rows[*].order_id"}, "Report order number"),
        ("amount", "DECIMAL", "d4_report.json", "json",
         {"json_path": "$.report.rows[*].amount"}, "Report amount"),
        ("region", "STRING", "d4_report.json", "json",
         {"json_path": "$.report.rows[*].region"}, "Report region"),
    ]),
]

_ROWS = [
    ("SO-1001", 19.8, "East China"),
    ("SO-1002", 59.0, "North China"),
    ("SO-1003", 12.5, "South China"),
]


def _csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    csvmod.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _d0_csv() -> bytes:
    return _csv_bytes([["order_id", "amount", "region"], *[list(r) for r in _ROWS]])


def _d3_csv() -> bytes:
    # Different content from d0 (daily totals), so sha256 dedup cannot prevent
    # binding by file name
    rows = [[order_id, round(amount * 2, 2), region]
            for order_id, amount, region in _ROWS]
    return _csv_bytes([["order_id", "amount", "region"], *rows])


def _d1_xlsx() -> bytes:
    """cleaned orders.xlsx: B1:F1 merged into the multi-level header "Order Info"."""
    wb = Workbook()
    # Fix document timestamps so repeated generation keeps the bytes as stable as
    # possible (an idempotence aid; the main safeguard is the completion check)
    wb.properties.created = datetime(2026, 1, 1)
    wb.properties.modified = datetime(2026, 1, 1)
    ws = wb.active
    ws.title = "Orders"
    ws["B1"] = "Order Info"
    ws.merge_cells("B1:F1")
    for col, name in zip("BCDEF", ["Order No", "Amount", "Region", "Remark", "Source"],
                         strict=True):
        ws[f"{col}2"] = name
    for row_idx, (order_id, amount, region) in enumerate(_ROWS, start=3):
        ws.cell(row_idx, 2, order_id)
        ws.cell(row_idx, 3, amount)
        ws.cell(row_idx, 4, region)
        ws.cell(row_idx, 5, "demo")
        ws.cell(row_idx, 6, "seed_demo")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _d2_json() -> bytes:
    return json.dumps(
        {"data": {"orders": [
            {"order_id": order_id, "amount": amount, "region": region}
            for order_id, amount, region in _ROWS]}},
        ensure_ascii=False).encode("utf-8")


def _d4_json() -> bytes:
    return json.dumps(
        {"report": {"rows": [
            {"order_id": order_id, "amount": amount, "region": region}
            for order_id, amount, region in _ROWS]}},
        ensure_ascii=False).encode("utf-8")


def _demo_files() -> dict[str, bytes]:
    return {
        "d0_orders.csv": _d0_csv(),
        "d1_orders.xlsx": _d1_xlsx(),
        "d2_orders.json": _d2_json(),
        "d3_daily.csv": _d3_csv(),
        "d4_report.json": _d4_json(),
    }


def _manifest(file_ids: dict[str, int]) -> dict:
    datasets = []
    for dataset_id, dataset_name, fields in DEMO_DATASETS:
        for field_name, field_type, src_file, src_type, locator, description in fields:
            datasets.append({
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "field_name": field_name,
                "field_type": field_type,
                "src_file": str(file_ids[src_file]),
                "src_type": src_type,
                "src_locator": locator,
                "description": description,
            })
    lineage = []
    for i in range(len(DEMO_DATASET_IDS) - 1):
        src, dst = DEMO_DATASET_IDS[i], DEMO_DATASET_IDS[i + 1]
        lineage.append({
            "from_dataset": src, "from_field": "order_id",
            "to_dataset": dst, "to_field": "order_id",
            "transform": "trim + cast + normalize",
            "confidence": 1.0, "note": "M2 demo: field-level lineage",
        })
        lineage.append({
            "from_dataset": src, "from_field": None,
            "to_dataset": dst, "to_field": None,
            "transform": "table projection",
            "confidence": 1.0, "note": "M2 demo: table-level lineage",
        })
    return {"datasets": datasets, "lineage": lineage}


def _already_seeded(conn) -> bool:
    """Considered complete when all demo datasets, fields and edges already exist."""
    marks = ",".join("?" for _ in DEMO_DATASET_IDS)
    dataset_ids = {r["id"] for r in conn.execute(
        f"SELECT id FROM dataset WHERE id IN ({marks})", DEMO_DATASET_IDS)}
    if dataset_ids != set(DEMO_DATASET_IDS):
        return False

    expected_fields = {
        (dataset_id, field[0])
        for dataset_id, _, fields in DEMO_DATASETS
        for field in fields
    }
    actual_fields = {
        (r["dataset_id"], r["name"]) for r in conn.execute(
            f"SELECT dataset_id, name FROM field WHERE dataset_id IN ({marks})",
            DEMO_DATASET_IDS)
    }
    if not expected_fields <= actual_fields:
        return False

    expected_edges = set()
    for i in range(len(DEMO_DATASET_IDS) - 1):
        src, dst = DEMO_DATASET_IDS[i], DEMO_DATASET_IDS[i + 1]
        expected_edges.add((src, "order_id", dst, "order_id"))
        expected_edges.add((src, None, dst, None))
    actual_edges = {
        (r["from_dataset"], r["from_field"], r["to_dataset"], r["to_field"])
        for r in conn.execute(
            f"SELECT from_dataset, from_field, to_dataset, to_field FROM edge"
            f" WHERE from_dataset IN ({marks}) AND to_dataset IN ({marks})",
            [*DEMO_DATASET_IDS, *DEMO_DATASET_IDS])
    }
    return expected_edges <= actual_edges


def _ensure_admin() -> str:
    """Demo data needs a valid actor (source_file.uploaded_by foreign key)."""
    settings = get_settings()
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM user WHERE username=?",
                              (settings.admin_username,)).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO user(username, password_hash, display_name, role, created_at)"
                " VALUES (?,?,?,?,?)",
                (settings.admin_username, hash_password(settings.admin_password),
                 "Initial admin", "admin",
                 datetime.now(UTC).isoformat(timespec="seconds")))
    return settings.admin_username


def seed_demo() -> dict:
    """Build the demo data; returns a summary of this run (skipped=True when already present)."""
    init_db()
    actor = _ensure_admin()

    with get_db() as conn:
        if _already_seeded(conn):
            print("Demo data already exists in full; skipping (idempotent)",
                  file=sys.stderr)
            return {"skipped": True, "batch_id": None, "version_no": None,
                    "summary": None}

    bound, file_ids = [], {}
    for name, data in _demo_files().items():
        rec = store_upload(name, data, actor)
        bound.append(rec)
        file_ids[name] = rec["id"]
    manifest_bytes = json.dumps(_manifest(file_ids), ensure_ascii=False).encode()
    ds_recs, edge_recs = read_json_manifest(manifest_bytes)
    batch_id, version_no, report = run_import(actor, "json", bound,
                                              ds_recs, edge_recs)
    print(f"Demo data import complete: batch v{version_no},"
          f" datasets {'→'.join(DEMO_DATASET_IDS)}, report {report.summary}",
          file=sys.stderr)
    return {"skipped": False, "batch_id": batch_id, "version_no": version_no,
            "summary": report.summary}


if __name__ == "__main__":
    seed_demo()
