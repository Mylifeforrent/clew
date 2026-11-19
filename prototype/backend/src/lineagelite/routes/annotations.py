"""Annotation API (business model §5.4 / invariant #5).

Annotations are append-only business notes: they are never updated in place, do not write
change_log, and are not deleted by version rollback.
``target_kind`` + ``target_id`` is a polymorphic association (data model §5.2):

- dataset: ``<dataset_id>``
- field: ``<dataset_id>.<field_name>``
- edge: ``<from>--><to>``, field-level is ``ds.field-->ds.field``,
  table-level edges are ``ds.*-->ds.*`` (the shorthand ``ds-->ds`` without ``.*`` is also accepted)

A missing target returns 404; an invalid format returns 400.
"""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..changes import now
from ..db import get_db
from ..models import AnnotationCreate
from ..security import require_role

router = APIRouter(tags=["annotations"])


class TargetFormatError(ValueError):
    """target_id format is invalid (→ 400)."""


def _parse_edge_side(raw: str) -> tuple[str, str | None]:
    if not raw:
        raise TargetFormatError("Both sides of the lineage edge target_id are required")
    if raw.endswith(".*"):
        dataset = raw[:-2]
        if not dataset:
            raise TargetFormatError("The dataset in the lineage edge target_id cannot be empty")
        return dataset, None
    if "." not in raw:
        # Table-level edge shorthand: ds-->ds
        return raw, None
    dataset, field = raw.rsplit(".", 1)
    if not dataset or not field:
        raise TargetFormatError(
            "Lineage edge target_id must be <dataset>.<field>-->... or <dataset>.*-->...")
    return dataset, field


def _parse_edge_target(target_id: str) -> tuple[str, str | None, str, str | None]:
    if "-->" not in target_id:
        raise TargetFormatError("Lineage edge target_id must be <from>--><to>")
    left, right = target_id.split("-->", 1)
    from_dataset, from_field = _parse_edge_side(left)
    to_dataset, to_field = _parse_edge_side(right)
    return from_dataset, from_field, to_dataset, to_field


def _resolve_field_target(conn: sqlite3.Connection, target_id: str) -> None:
    """Parse the field target_id and verify existence; dataset IDs / field names may contain dots, so take the unique hit."""
    if "." not in target_id:
        raise TargetFormatError("Field target_id must be <dataset_id>.<field_name>")
    matches = []
    start = 0
    while True:
        idx = target_id.find(".", start)
        if idx < 0:
            break
        dataset_id, field_name = target_id[:idx], target_id[idx + 1:]
        if dataset_id and field_name and conn.execute(
                "SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                (dataset_id, field_name)).fetchone() is not None:
            matches.append((dataset_id, field_name))
        start = idx + 1
    if len(matches) > 1:
        raise TargetFormatError(f'Field target_id "{target_id}" is ambiguous; check the dataset/field naming')
    if not matches:
        raise LookupError(f'Field "{target_id}" does not exist')


def _validate_target(conn: sqlite3.Connection, kind: str, target_id: str) -> None:
    """Validate target existence: missing raises LookupError (→404), invalid format raises TargetFormatError (→400)."""
    if kind == "dataset":
        if conn.execute("SELECT 1 FROM dataset WHERE id=?",
                        (target_id,)).fetchone() is None:
            raise LookupError(f'Dataset "{target_id}" does not exist')
        return
    if kind == "field":
        _resolve_field_target(conn, target_id)
        return
    from_dataset, from_field, to_dataset, to_field = _parse_edge_target(target_id)
    if conn.execute(
            "SELECT 1 FROM edge WHERE from_dataset=? AND from_field IS ?"
            " AND to_dataset=? AND to_field IS ?",
            (from_dataset, from_field, to_dataset, to_field)).fetchone() is None:
        raise LookupError(f'Lineage edge "{target_id}" does not exist')


@router.post("/annotations", status_code=201)
def create_annotation(body: AnnotationCreate,
                      user: dict = Depends(require_role("editor"))):
    """Append an annotation (editor+). Annotations are not updated/deleted and do not write change_log."""
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Annotation body cannot be empty")
    with get_db() as conn:
        try:
            _validate_target(conn, body.target_kind, body.target_id)
        except TargetFormatError as e:
            raise HTTPException(400, str(e)) from None
        except LookupError as e:
            raise HTTPException(404, str(e)) from None
        cur = conn.execute(
            "INSERT INTO annotation(target_kind, target_id, body, author, created_at)"
            " VALUES (?,?,?,?,?)",
            (body.target_kind, body.target_id, text, user["username"], now()))
        row = conn.execute("SELECT * FROM annotation WHERE id=?",
                           (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/annotations")
def list_annotations(
    target_kind: Literal["dataset", "field", "edge"] | None = Query(None),
    target_id: str | None = Query(None),
    user: dict = Depends(require_role("viewer")),
):
    """Filter annotations by target (viewer+), returned in append order (ascending id)."""
    clauses, args = [], []
    if target_kind is not None:
        clauses.append("target_kind=?")
        args.append(target_kind)
    if target_id is not None:
        clauses.append("target_id=?")
        args.append(target_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT id, target_kind, target_id, body, author, created_at"
            f" FROM annotation{where} ORDER BY id", args).fetchall()
    return [dict(r) for r in rows]
