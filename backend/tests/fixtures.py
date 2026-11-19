"""Source files: build first-party XLSX (multi-level headers + merged cells), CSV and JSON files."""

import io
import json

from openpyxl import Workbook


def order_xlsx_bytes() -> bytes:
    """orders.xlsx: row 1 has B1:F1 merged as "Product Info" and G1 "Shipping Info";
    row 2 has multi-level headers; rows 3-4 are data."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws["B1"] = "Product Info"
    ws.merge_cells("B1:F1")
    ws["G1"] = "Shipping Info"
    for col, name in zip("BCDEFG", ["Product ID", "Order No", "Quantity", "Unit Price",
                                    "Amount", "Shipping Fee"],
                         strict=True):
        ws[f"{col}2"] = name
    rows = [("S001", "SO-1001", 2, 9.9, 19.8, 5),
            ("S002", "SO-1002", 1, 59.0, 59.0, 0)]
    for i, row in enumerate(rows, start=3):
        for j, v in enumerate(row, start=2):
            ws.cell(i, j, v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def user_csv_bytes() -> bytes:
    return ("user_id,user_name,phone\n"
            "1,Alice,138*\n"
            "2,Bob,139*\n").encode("utf-8")


def source_json_bytes() -> bytes:
    return json.dumps({"data": {"items": [{"order_no": "SO-1001"},
                                          {"order_no": "SO-1002"}]}},
                      ensure_ascii=False).encode("utf-8")
