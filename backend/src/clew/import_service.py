"""Import orchestration: validate → persist → change_log → import report (design §3.5 / §4.2).

Write-path order: datasets/fields first (satisfies the edge table's composite
foreign keys), then lineage. Every change writes change_log (op + before/after
snapshots); batch rollback reverses them accordingly.
"""

import json
from datetime import UTC, datetime

from .changes import edge_snapshot
from .config import resolve_storage
from .db import get_db
from .locator import CHECKERS, LOCATOR_MODELS, LocatorError
from .models import (DatasetFieldRecord, ImportReport,
                     ImportReportItem, LineageEdgeRecord)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _snap(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def _log(conn, batch_id: int, kind: str, key: str, op: str,
         before: dict | None, after: dict | None, actor: str) -> None:
    conn.execute(
        "INSERT INTO change_log(batch_id, entity_kind, entity_key, op, before, after, actor, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (batch_id, kind, key, op,
         _snap(before) if before else None, _snap(after) if after else None,
         actor, _now()))


def _resolve_source_file(conn, ref: str, bound: list) -> tuple[int, str] | None:
    """Resolve a src_file reference: a source-file library ID or an original file name within this batch's bound file set."""
    if ref.isdigit():
        for f in bound:
            if f["id"] == int(ref):
                return f["id"], f["src_type"]
        return None
    matches = [f for f in bound if f["original_name"] == ref]
    if len(matches) == 1:
        return matches[0]["id"], matches[0]["src_type"]
    if len(matches) > 1:
        raise ValueError(f"src_file \"{ref}\" is not unique within this batch's file set")
    return None


def _upsert_field(conn, rec: DatasetFieldRecord, sf_id: int,
                  locator_envelope: str, actor: str, batch_id: int,
                  items: list[ImportReportItem]) -> None:
    ref = f"{rec.dataset_id}.{rec.field_name}"
    payload = {"dataset_id": rec.dataset_id, "name": rec.field_name,
               "field_type": rec.field_type, "source_file_id": sf_id,
               "src_locator": locator_envelope, "description": rec.description}
    existing = conn.execute("SELECT * FROM field WHERE dataset_id=? AND name=?",
                            (rec.dataset_id, rec.field_name)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO field(dataset_id, name, field_type, source_file_id,"
            " src_locator, description, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (payload["dataset_id"], payload["name"], payload["field_type"],
             payload["source_file_id"], payload["src_locator"],
             payload["description"], _now(), _now()))
        _log(conn, batch_id, "field", ref, "added", None, payload, actor)
        items.append(ImportReportItem(status="ok", kind="field", ref=ref,
                                      source_row=rec.row))
        return
    before = {"dataset_id": existing["dataset_id"], "name": existing["name"],
              "field_type": existing["field_type"],
              "source_file_id": existing["source_file_id"],
              "src_locator": existing["src_locator"],
              "description": existing["description"]}
    if all(before[k] == payload[k] for k in payload):
        items.append(ImportReportItem(status="ok", kind="field", ref=ref,
                                      reason="unchanged", source_row=rec.row))
        return
    conn.execute(
        "UPDATE field SET field_type=?, source_file_id=?, src_locator=?,"
        " description=?, updated_at=? WHERE dataset_id=? AND name=?",
        (payload["field_type"], payload["source_file_id"], payload["src_locator"],
         payload["description"], _now(), rec.dataset_id, rec.field_name))
    _log(conn, batch_id, "field", ref, "updated", before, payload, actor)
    items.append(ImportReportItem(status="ok", kind="field", ref=ref,
                                  source_row=rec.row))


def _ensure_dataset(conn, rec: DatasetFieldRecord, actor: str, batch_id: int) -> None:
    if conn.execute("SELECT 1 FROM dataset WHERE id=?",
                    (rec.dataset_id,)).fetchone():
        return
    conn.execute(
        "INSERT INTO dataset(id, name, description, created_at, updated_at)"
        " VALUES (?,?,?,?,?)",
        (rec.dataset_id, rec.dataset_name, None, _now(), _now()))
    _log(conn, batch_id, "dataset", rec.dataset_id, "added", None,
         {"id": rec.dataset_id, "name": rec.dataset_name}, actor)


def run_import(actor: str, fmt: str, bound_files: list[dict],
               ds_recs: list[DatasetFieldRecord],
               edge_recs: list[LineageEdgeRecord]) -> tuple[int, int, ImportReport]:
    """Run one import and return (batch_id, version_no, report)."""
    items: list[ImportReportItem] = []

    with get_db() as conn:
        version_no = (conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM import_batch"
        ).fetchone()["n"])
        cur = conn.execute(
            "INSERT INTO import_batch(version_no, file_names, format, created_by, created_at)"
            " VALUES (?,?,?,?,?)",
            (version_no,
             json.dumps([f["original_name"] for f in bound_files], ensure_ascii=False),
             fmt, actor, _now()))
        batch_id = cur.lastrowid

        # ---------- Phase one: datasets / fields ----------
        for rec in ds_recs:
            ref = f"{rec.dataset_id}.{rec.field_name}"
            try:
                # Manifest row-level parse error: reject the whole row (reason is
                # the in-row error description)
                if rec.parse_error:
                    raise ValueError(rec.parse_error)
                if not rec.dataset_id or not rec.field_name:
                    raise ValueError("dataset_id / field_name are required")
                if rec.src_type not in CHECKERS:
                    raise ValueError(
                        f"src_type must be csv/xlsx/json, got \"{rec.src_type}\"")
                sf = _resolve_source_file(conn, rec.src_file, bound_files)
                if sf is None:
                    raise ValueError(
                        f"src_file \"{rec.src_file}\" cannot be uniquely resolved"
                        " within this batch's file set")
                sf_id, sf_type = sf
                if sf_type != rec.src_type:
                    raise ValueError(
                        f"src_type \"{rec.src_type}\" does not match the source"
                        f" file's actual type \"{sf_type}\"")
            except ValueError as e:
                items.append(ImportReportItem(status="rejected", kind="field", ref=ref,
                                              reason=str(e), source_row=rec.row))
                continue

            src_path = str(resolve_storage(conn.execute(
                "SELECT storage_path FROM source_file WHERE id=?",
                (sf_id,)).fetchone()["storage_path"]))
            try:
                loc_in = LOCATOR_MODELS[rec.src_type](**rec.src_locator)
            except Exception as e:
                items.append(ImportReportItem(
                    status="rejected", kind="field", ref=ref,
                    reason=f"locator structural validation failed: {e}",
                    source_row=rec.row))
                continue
            try:
                resolved = CHECKERS[rec.src_type](src_path, loc_in)
            except LocatorError as e:
                items.append(ImportReportItem(
                    status="rejected", kind="field", ref=ref,
                    reason=f"real-file verification failed: {e}",
                    source_row=rec.row))
                continue

            locator_envelope = json.dumps(
                {"type": rec.src_type,
                 "input": loc_in.model_dump(exclude_none=True),
                 "resolved": resolved},
                ensure_ascii=False)
            _ensure_dataset(conn, rec, actor, batch_id)
            _upsert_field(conn, rec, sf_id, locator_envelope, actor, batch_id, items)

        # ---------- Phase two: lineage ----------
        seen_edges: dict[tuple, int] = {}  # natural key -> items index
        for rec in edge_recs:
            ref = (f"{rec.from_dataset}.{rec.from_field or '*'}-->"
                   f"{rec.to_dataset}.{rec.to_field or '*'}")
            try:
                # Manifest row-level parse error: reject the whole row (reason is
                # the in-row error description)
                if rec.parse_error:
                    raise ValueError(rec.parse_error)
                if not rec.from_dataset or not rec.to_dataset:
                    raise ValueError("from_dataset / to_dataset are required")
                # Mixed-field edges (one side empty, one non-empty) are semantically
                # invalid: it must be either table-level or field-level
                if bool(rec.from_field) != bool(rec.to_field):
                    raise ValueError(
                        "Lineage edges must provide both upstream and downstream"
                        " fields (field-level) or neither (table-level)")
                if rec.from_field and not conn.execute(
                        "SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                        (rec.from_dataset, rec.from_field)).fetchone():
                    raise ValueError(
                        f"Upstream field {rec.from_dataset}.{rec.from_field}"
                        " does not exist")
                if rec.to_field and not conn.execute(
                        "SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                        (rec.to_dataset, rec.to_field)).fetchone():
                    raise ValueError(
                        f"Downstream field {rec.to_dataset}.{rec.to_field}"
                        " does not exist")
                if not conn.execute("SELECT 1 FROM dataset WHERE id=?",
                                    (rec.from_dataset,)).fetchone() or \
                   not conn.execute("SELECT 1 FROM dataset WHERE id=?",
                                    (rec.to_dataset,)).fetchone():
                    raise ValueError(
                        "A dataset referenced by the edge does not exist")
                confidence = rec.confidence if rec.confidence is not None else 1.0
                if not 0 <= confidence <= 1:
                    raise ValueError("confidence must be between 0 and 1")
            except ValueError as e:
                items.append(ImportReportItem(status="rejected", kind="edge", ref=ref,
                                              reason=str(e), source_row=rec.row))
                continue

            payload = {"from_dataset": rec.from_dataset, "from_field": rec.from_field,
                       "to_dataset": rec.to_dataset, "to_field": rec.to_field,
                       "transform": rec.transform, "confidence": confidence,
                       "source": "imported", "note": rec.note}
            key = (rec.from_dataset, rec.from_field, rec.to_dataset, rec.to_field)

            if key in seen_edges:  # duplicate within the batch: later row overrides transform/note (design §3.5-4)
                idx = seen_edges[key]
                first = items[idx]
                conn.execute(
                    "UPDATE edge SET transform=?, confidence=?, note=?, updated_by=?,"
                    " updated_at=? WHERE from_dataset=? AND from_field IS ? AND"
                    " to_dataset=? AND to_field IS ?",
                    (payload["transform"], payload["confidence"], payload["note"],
                     actor, _now(), *key))
                first.status = "merged"
                first.reason = (
                    f"duplicate upstream/downstream pair, overwritten by manifest"
                    f" row {rec.row}")
                continue

            existing = conn.execute(
                "SELECT * FROM edge WHERE from_dataset=? AND from_field IS ? AND"
                " to_dataset=? AND to_field IS ?", key).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
                    " transform, confidence, source, note, created_by, updated_by,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*key, payload["transform"], payload["confidence"],
                     payload["source"], payload["note"], actor, actor, _now(), _now()))
                _log(conn, batch_id, "edge", ref, "added", None, payload, actor)
            else:
                # Take only EDGE_SNAPSHOT_KEYS business columns, consistent with
                # manual edits/added snapshots (no id/timestamps and no
                # created_by/updated_by audit columns).
                before = edge_snapshot(existing)
                if all(before[k] == payload[k] for k in payload):
                    items.append(ImportReportItem(status="ok", kind="edge", ref=ref,
                                                  reason="unchanged", source_row=rec.row))
                    seen_edges[key] = len(items) - 1
                    continue
                conn.execute(
                    "UPDATE edge SET transform=?, confidence=?, source=?, note=?,"
                    " updated_by=?, updated_at=? WHERE from_dataset=? AND from_field IS ?"
                    " AND to_dataset=? AND to_field IS ?",
                    (payload["transform"], payload["confidence"], payload["source"],
                     payload["note"], actor, _now(), *key))
                _log(conn, batch_id, "edge", ref, "updated", before, payload, actor)
            items.append(ImportReportItem(status="ok", kind="edge", ref=ref,
                                          source_row=rec.row))
            seen_edges[key] = len(items) - 1

        summary = {"total": len(items),
                   "ok": sum(1 for i in items if i.status == "ok"),
                   "merged": sum(1 for i in items if i.status == "merged"),
                   "rejected": sum(1 for i in items if i.status == "rejected")}
        report = ImportReport(summary=summary, items=items)
        conn.execute("UPDATE import_batch SET report=? WHERE id=?",
                     (report.model_dump_json(), batch_id))

    return batch_id, version_no, report
