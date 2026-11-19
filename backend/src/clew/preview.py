"""Field source preview: open the managed source file via ``field.src_locator``
and return the data needed for highlighting.

The response structure matches the API contract (one of ``csv`` / ``xlsx`` / ``json``):

- csv: first-row header + column number + first 50 data rows;
- xlsx: sheet, header rows, merged ranges, column number, data row range + first
  50 data rows;
- json: JSONPath, total hit count + first 10 hit values.

A stale locator (missing file, non-existent sheet, materialized row/column range
out of bounds, JSONPath with no matches, etc.) uniformly raises
:class:`PreviewError`, which the route layer turns into 409; a missing
dataset/field is turned into 404 by the caller.
"""

import csv
import json
import sqlite3
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from jsonpath_ng import parse as jsonpath_parse
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from .config import resolve_storage

PREVIEW_ROW_LIMIT = 50
PREVIEW_JSON_LIMIT = 10


class PreviewError(ValueError):
    """The locator is stale for the current source file (→ 409)."""


def _cell_value(value):
    """openpyxl cell value → JSON-serializable value."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _envelope(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "")
    except json.JSONDecodeError:
        raise PreviewError(
            "Field locator is not valid JSON; the locator is stale") from None
    if not isinstance(value, dict):
        raise PreviewError(
            "Field locator has an invalid structure; the locator is stale")
    return value


def _preview_csv(path: Path, locator: dict) -> dict:
    resolved = locator.get("resolved") or {}
    user_input = locator.get("input") or {}

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise PreviewError("The CSV source file is empty; cannot preview")
        rows = [row for _, row in zip(range(PREVIEW_ROW_LIMIT), reader, strict=False)]

    column_index = resolved.get("column_index")
    if column_index is None:
        if user_input.get("header") is not None:
            try:
                column_index = header.index(user_input["header"]) + 1
            except ValueError:
                raise PreviewError(
                    f"CSV header \"{user_input['header']}\" not found in the"
                    " source file; the locator is stale") from None
        elif user_input.get("column") is not None:
            column_index = user_input["column"]
    if not isinstance(column_index, int) or not 1 <= column_index <= len(header):
        raise PreviewError(
            f"CSV column locator ({column_index}) exceeds the source file's"
            f" column count ({len(header)}); the locator is stale")

    width = len(header)
    rows = [row + [""] * (width - len(row)) if len(row) < width else row for row in rows]
    return {"header": header, "column_index": column_index, "rows": rows}


def _preview_xlsx(path: Path, locator: dict) -> dict:
    resolved = locator.get("resolved") or {}
    user_input = locator.get("input") or {}
    sheet = user_input.get("sheet")
    if not sheet:
        raise PreviewError("XLSX locator is missing sheet; the locator is stale")

    wb = load_workbook(path, data_only=True, read_only=False)
    try:
        if sheet not in wb.sheetnames:
            raise PreviewError(
                f"Worksheet \"{sheet}\" no longer exists"
                f" (existing: {', '.join(wb.sheetnames)}); the locator is stale")
        ws = wb[sheet]
        max_col = ws.max_column
        max_row = ws.max_row

        column_index = resolved.get("column_index")
        if column_index is None:
            column = user_input.get("column") or resolved.get("column")
            if not column:
                raise PreviewError(
                    "XLSX locator is missing column information; the locator is stale")
            try:
                column_index = column_index_from_string(str(column).upper())
            except ValueError:
                raise PreviewError(
                    f"XLSX column reference \"{column}\" is invalid;"
                    " the locator is stale") from None
        if not isinstance(column_index, int) or not 1 <= column_index <= max_col:
            raise PreviewError(
                f"XLSX column locator ({column_index}) exceeds the worksheet's"
                f" column count ({max_col}); the locator is stale")

        header_count = user_input.get("header_rows")
        if header_count is None and user_input.get("header_path"):
            header_count = len(user_input["header_path"])
        header_count = int(header_count or 0)
        header_count = max(0, min(header_count, max_row))
        header_rows = [
            [_cell_value(ws.cell(r, c).value) for c in range(1, max_col + 1)]
            for r in range(1, header_count + 1)
        ]

        declared_start = resolved.get("row_start")
        if declared_start is None:
            declared_start = user_input.get("row_start")
        if declared_start is None:
            # No materialized row range: default to the first row after the header
            # (an empty data table still returns an empty preview)
            row_start = header_count + 1
        else:
            row_start = int(declared_start)
            if row_start > max_row:
                raise PreviewError(
                    f"Data row start (row_start={row_start}) exceeds the"
                    f" worksheet's row count ({max_row}); the locator is stale")

        declared_end = resolved.get("row_end")
        if declared_end is None:
            declared_end = user_input.get("row_end")
        if declared_end is None:
            row_end = max_row
        else:
            row_end = int(declared_end)
            if row_end > max_row:
                raise PreviewError(
                    f"Data row end (row_end={row_end}) exceeds the"
                    f" worksheet's row count ({max_row}); the locator is stale")
        if row_end < row_start - 1:
            raise PreviewError(
                f"Invalid data row range (row_end={row_end} is less than"
                f" row_start={row_start}); the locator is stale")
        preview_end = min(row_end, row_start + PREVIEW_ROW_LIMIT - 1)
        rows = []
        if preview_end >= row_start:
            rows = [
                [_cell_value(ws.cell(r, c).value) for c in range(1, max_col + 1)]
                for r in range(row_start, preview_end + 1)
            ]

        # Merged ranges: return ranges intersecting "header + this preview's rows"
        # so the frontend can render merged cells
        visible_end = max(header_count, preview_end, 0)
        merged_ranges = [
            str(rng) for rng in sorted(ws.merged_cells.ranges,
                                       key=lambda r: (r.min_row, r.min_col))
            if rng.min_row <= visible_end
        ]
        return {
            "sheet": sheet,
            "header_rows": header_rows,
            "merged_ranges": merged_ranges,
            "column_index": column_index,
            "row_start": row_start,
            "row_end": row_end if row_end >= row_start else row_start - 1,
            "rows": rows,
        }
    finally:
        wb.close()


def _preview_json(path: Path, locator: dict) -> dict:
    user_input = locator.get("input") or {}
    json_path = user_input.get("json_path")
    if not json_path:
        raise PreviewError(
            "JSON locator is missing json_path; the locator is stale")

    try:
        with open(path, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        raise PreviewError(
            f"Failed to parse the source JSON file ({e.msg});"
            " the locator is stale") from None

    try:
        expr = jsonpath_parse(json_path)
    except Exception:
        raise PreviewError(
            f"JSONPath \"{json_path}\" has invalid syntax;"
            " the locator is stale") from None

    matches = expr.find(doc)
    if not matches:
        raise PreviewError(
            f"JSONPath \"{json_path}\" has no matches in the source file;"
            " the locator is stale")
    return {
        "json_path": json_path,
        "hits": len(matches),
        "samples": [m.value for m in matches[:PREVIEW_JSON_LIMIT]],
    }


_PREVIEWERS = {"csv": _preview_csv, "xlsx": _preview_xlsx, "json": _preview_json}


def field_preview(conn: sqlite3.Connection, dataset_id: str,
                  field_name: str) -> dict:
    """Return the field's source preview; missing field/dataset raises LookupError."""
    if conn.execute("SELECT 1 FROM dataset WHERE id=?", (dataset_id,)).fetchone() is None:
        raise LookupError(f"Dataset \"{dataset_id}\" does not exist")
    row = conn.execute(
        "SELECT f.name, f.src_locator, s.id AS source_file_id,"
        " s.original_name, s.storage_path, s.src_type, s.sha256,"
        " s.size_bytes, s.uploaded_by"
        " FROM field f JOIN source_file s ON s.id = f.source_file_id"
        " WHERE f.dataset_id=? AND f.name=?",
        (dataset_id, field_name)).fetchone()
    if row is None:
        raise LookupError(f"Field \"{dataset_id}.{field_name}\" does not exist")

    locator = _envelope(row["src_locator"])
    src_type = locator.get("type") or row["src_type"]
    if src_type != row["src_type"]:
        raise PreviewError(
            f"Field locator type \"{src_type}\" does not match the source file"
            f" type \"{row['src_type']}\"; the locator is stale")
    previewer = _PREVIEWERS.get(src_type)
    if previewer is None:
        raise PreviewError(f"Unsupported source file type \"{src_type}\"")

    path = resolve_storage(row["storage_path"])
    if not path.is_file():
        raise PreviewError(
            f"Source file \"{row['original_name']}\" is not in managed storage;"
            " the locator is stale")
    try:
        preview = previewer(path, locator)
    except PreviewError:
        raise
    except Exception as e:
        # A corrupt csv/xlsx/json may make the parser raise various exceptions;
        # treat them all as "stale locator"
        raise PreviewError(
            f"Failed to parse source file \"{row['original_name']}\" ({e});"
            " the locator is stale") from None

    # Real-file verification record: the import batch of the field's most recent
    # ingestion (added/updated). The importer only writes change_log after
    # passing real-file verification, so this record means "verification passed".
    verified = conn.execute(
        "SELECT b.version_no, cl.actor, cl.created_at"
        " FROM change_log cl JOIN import_batch b ON b.id = cl.batch_id"
        " WHERE cl.entity_kind='field' AND cl.entity_key=?"
        " AND cl.op IN ('added','updated') ORDER BY cl.id DESC LIMIT 1",
        (f"{dataset_id}.{field_name}",)).fetchone()

    return {
        "file": {
            "id": row["source_file_id"],
            "original_name": row["original_name"],
            # Source files are content-addressed and deduplicated by sha256; the
            # frontend shows the managed copy and dedup basis
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "src_type": row["src_type"],
            "uploaded_by": row["uploaded_by"],
        },
        "verification": ({
            "status": "passed",
            "version_no": verified["version_no"],
            "checked_by": verified["actor"],
            "checked_at": verified["created_at"],
        } if verified is not None else None),
        "locator": locator,
        "preview": preview,
    }
