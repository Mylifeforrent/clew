"""Locator real-file verification (design §3.2 / §3.5-2).

On import, open the managed first-hand file and mechanically verify the locator,
materializing the parse result:
- csv: column number/header resolved to column_index
- xlsx: sheet existence, simple column lookup, multi-level header_path expansion, merged-cell anchor normalization
- json: JSONPath hit count
"""

import csv
import io
import json

from jsonpath_ng import parse as jsonpath_parse
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from .models import CsvLocatorIn, JsonLocatorIn, XlsxLocatorIn


class LocatorError(ValueError):
    """Locator verification failed (structure validation or real-file verification)."""


def check_csv(path: str, loc: CsvLocatorIn) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    width = len(header)
    if loc.header is not None:
        for i, name in enumerate(header, start=1):
            if name and name.strip() == loc.header:
                return {"column_index": i, "header": loc.header}
        raise LocatorError(f'CSV header "{loc.header}" was not found in the first row of the source file ({width} columns)')
    if loc.column is None:
        raise LocatorError("CSV locator must provide either column or header")
    if loc.column > width:
        raise LocatorError(f"CSV column {loc.column} exceeds the source file column count ({width})")
    return {"column_index": loc.column,
            "header": header[loc.column - 1] if loc.column <= width else None}


def _merged_anchor(ws, row_idx: int, col_idx: int) -> dict | None:
    """If (row, col) falls inside a merged range, return anchor info (top-left + range)."""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row_idx <= rng.max_row and rng.min_col <= col_idx <= rng.max_col:
            return {
                "value": ws.cell(rng.min_row, rng.min_col).value,
                "anchor": f"{get_column_letter(rng.min_col)}{rng.min_row}",
                "range": rng.coord,
            }
    return None


def check_xlsx(path: str, loc: XlsxLocatorIn) -> dict:
    wb = load_workbook(path, data_only=True, read_only=False)
    try:
        if loc.sheet not in wb.sheetnames:
            raise LocatorError(
                f'XLSX sheet "{loc.sheet}" does not exist (available: {", ".join(wb.sheetnames)})')
        ws = wb[loc.sheet]

        if loc.header_path:
            header_rows = loc.header_rows or len(loc.header_path)
            resolved, candidates, anchors = None, None, []
            for level, want in enumerate(loc.header_path, start=1):
                if level > header_rows:
                    raise LocatorError(f"Header path level {level} exceeds header_rows={header_rows}")
                hit_col = None
                for col in range(1, ws.max_column + 1):
                    if candidates and col not in candidates:
                        continue
                    v = ws.cell(level, col).value
                    if v is not None and str(v).strip() == want:
                        hit_col = col
                        break
                if hit_col is None:
                    scope = f"columns {get_column_letter(min(candidates))}-{get_column_letter(max(candidates))}" \
                        if candidates else f"row {level} across the sheet"
                    raise LocatorError(
                        f'Header path level {level} value "{want}" was not found (searched within {scope})')
                anchor = _merged_anchor(ws, level, hit_col)
                if anchor:
                    anchors.append(anchor)
                    rng = next(r for r in ws.merged_cells.ranges if r.coord == anchor["range"])
                    candidates = set(range(rng.min_col, rng.max_col + 1))
                else:
                    candidates = {hit_col}
                resolved = hit_col
            row_start = loc.row_start or (header_rows + 1)
            return {
                "column_index": resolved,
                "column": get_column_letter(resolved),
                "row_start": row_start,
                "row_end": loc.row_end,
                "merged_anchors": anchors,
            }

        if not loc.column:
            raise LocatorError("XLSX locator must provide either column or header_path")
        try:
            col_idx = column_index_from_string(loc.column.upper())
        except ValueError:
            raise LocatorError(f'XLSX column identifier "{loc.column}" is invalid') from None
        if loc.row_start and loc.row_end and loc.row_end < loc.row_start:
            raise LocatorError("row_end cannot be less than row_start")
        return {"column_index": col_idx, "column": loc.column.upper(),
                "row_start": loc.row_start, "row_end": loc.row_end, "merged_anchors": []}
    finally:
        wb.close()


def check_json(path: str, loc: JsonLocatorIn) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        try:
            doc = json.load(f)
        except json.JSONDecodeError as e:
            raise LocatorError(f"Failed to parse the source JSON file ({e.msg})") from None
    try:
        expr = jsonpath_parse(loc.json_path)
    except Exception:
        raise LocatorError(f'JSONPath "{loc.json_path}" has invalid syntax') from None
    hits = len(expr.find(doc))
    if hits == 0:
        raise LocatorError(f'JSONPath "{loc.json_path}" has no match in the source file')
    return {"hits": hits}


# src_type → structure model / real-file verifier; shared by import and M3 field-locator editing
CHECKERS = {"csv": check_csv, "xlsx": check_xlsx, "json": check_json}
LOCATOR_MODELS = {"csv": CsvLocatorIn, "xlsx": XlsxLocatorIn,
                  "json": JsonLocatorIn}
