"""Lineage edge manual editing API (M3, editor+).

- ``POST /edges``: create an edge manually (source='manual'); a duplicate natural key is 409, a mixed field edge is 400;
- ``PATCH /edges/{id}``: change transform/note/confidence;
- ``DELETE /edges/{id}``: delete a wrong edge.

All three write operations write change_log (batch_id=NULL, actor=current user) so history
viewing and tag rollback can reverse them.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from ..changes import edge_key, edge_snapshot, log_change, now
from ..db import get_db
from ..models import EdgeCreate, EdgePatch
from ..security import require_role

router = APIRouter(tags=["edges"])


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _edge_row(conn, edge_id: int):
    return conn.execute(
        "SELECT id, from_dataset, from_field, to_dataset, to_field, transform,"
        " confidence, source, note, created_by, updated_by, created_at, updated_at"
        " FROM edge WHERE id=?", (edge_id,)).fetchone()


def _ensure_refs(conn, from_dataset: str, from_field: str | None,
                 to_dataset: str, to_field: str | None) -> None:
    for dataset_id in dict.fromkeys((from_dataset, to_dataset)):
        if conn.execute("SELECT 1 FROM dataset WHERE id=?",
                        (dataset_id,)).fetchone() is None:
            raise HTTPException(404, f'Dataset "{dataset_id}" does not exist')
    for dataset_id, field_name in ((from_dataset, from_field),
                                   (to_dataset, to_field)):
        if field_name is not None and conn.execute(
                "SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                (dataset_id, field_name)).fetchone() is None:
            raise HTTPException(404, f'Field "{dataset_id}.{field_name}" does not exist')


@router.post("/edges", status_code=201)
def create_edge(body: EdgeCreate, user: dict = Depends(require_role("editor"))):
    """Create a lineage edge manually; the natural key is unique and field-level/table-level are mutually exclusive."""
    from_dataset = _clean(body.from_dataset)
    to_dataset = _clean(body.to_dataset)
    if not from_dataset or not to_dataset:
        raise HTTPException(400, "from_dataset / to_dataset are required")
    from_field = _clean(body.from_field)
    to_field = _clean(body.to_field)
    if bool(from_field) != bool(to_field):
        raise HTTPException(
            400, "An edge must provide both upstream and downstream fields (field-level) or neither (table-level)")
    transform = _clean(body.transform)
    note = _clean(body.note)

    with get_db() as conn:
        _ensure_refs(conn, from_dataset, from_field, to_dataset, to_field)
        existing = conn.execute(
            "SELECT id FROM edge WHERE from_dataset=? AND from_field IS ?"
            " AND to_dataset=? AND to_field IS ?",
            (from_dataset, from_field, to_dataset, to_field)).fetchone()
        if existing is not None:
            raise HTTPException(
                409, "A lineage edge with the same upstream/downstream natural key already exists (edges are unique, invariant #3)")
        timestamp = now()
        try:
            cur = conn.execute(
                "INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
                " transform, confidence, source, note, created_by, updated_by,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (from_dataset, from_field, to_dataset, to_field, transform,
                 body.confidence, "manual", note, user["username"],
                 user["username"], timestamp, timestamp))
        except sqlite3.IntegrityError:
            # The unique index catches races / bypassed pre-checks
            raise HTTPException(
                409, "A lineage edge with the same upstream/downstream natural key already exists (edges are unique, invariant #3)") from None
        row = _edge_row(conn, cur.lastrowid)
        log_change(
            conn, entity_kind="edge",
            entity_key=edge_key(from_dataset, from_field, to_dataset, to_field),
            op="added", before=None, after=edge_snapshot(row),
            actor=user["username"])
    return dict(row)


@router.patch("/edges/{edge_id}")
def patch_edge(edge_id: int, body: EdgePatch,
               user: dict = Depends(require_role("editor"))):
    """Change an edge's transform description/note/confidence (endpoints and source are immutable)."""
    provided = body.model_fields_set
    if not provided:
        raise HTTPException(
            400, "Provide at least one editable field (transform / note / confidence)")
    if "confidence" in provided and body.confidence is None:
        raise HTTPException(400, "confidence cannot be empty (0~1)")

    with get_db() as conn:
        row = _edge_row(conn, edge_id)
        if row is None:
            raise HTTPException(404, f"Lineage edge {edge_id} does not exist")
        new_transform = (_clean(body.transform) if "transform" in provided
                         else row["transform"])
        new_note = _clean(body.note) if "note" in provided else row["note"]
        new_confidence = (body.confidence if "confidence" in provided
                          else row["confidence"])
        before = edge_snapshot(row)
        after = {**before, "transform": new_transform, "note": new_note,
                 "confidence": new_confidence}
        if before == after:
            return dict(row)

        conn.execute(
            "UPDATE edge SET transform=?, note=?, confidence=?, updated_by=?,"
            " updated_at=? WHERE id=?",
            (new_transform, new_note, new_confidence, user["username"],
             now(), edge_id))
        log_change(
            conn, entity_kind="edge",
            entity_key=edge_key(row["from_dataset"], row["from_field"],
                                row["to_dataset"], row["to_field"]),
            op="updated", before=before, after=after, actor=user["username"])
        saved = _edge_row(conn, edge_id)
    return dict(saved)


@router.delete("/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: int, user: dict = Depends(require_role("editor"))):
    """Delete a wrong edge; the before snapshot is written to change_log so tag rollback can restore it."""
    with get_db() as conn:
        row = _edge_row(conn, edge_id)
        if row is None:
            raise HTTPException(404, f"Lineage edge {edge_id} does not exist")
        before = edge_snapshot(row)
        conn.execute("DELETE FROM edge WHERE id=?", (edge_id,))
        log_change(
            conn, entity_kind="edge",
            entity_key=edge_key(row["from_dataset"], row["from_field"],
                                row["to_dataset"], row["to_field"]),
            op="deleted", before=before, after=None, actor=user["username"])
    return Response(status_code=204)
