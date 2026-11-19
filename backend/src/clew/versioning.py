"""Version management: rollback by import batch/business tag (change_log reversal), change queries and tag diffs.

Rollback rules (data model §7): added→delete, updated→restore before,
deleted→reinsert before, executed in descending log-id order. The reversal
functions are safe both when a row "no longer exists" and when it "already
exists"; tag rollback also skips logs already covered by a previous rollback
(batch already rolled back, or the log falls inside a rollback_record range),
so rolling back to the same tag repeatedly (idempotent) neither changes the
final state nor returns anything but 0.

Audit strategy:
- batch rollback reuses import_batch.rolled_back_at/by;
- tag rollback writes rollback_record (no change_log, to avoid the next
  rollback reversing the rollback log) and also marks the import_batch that
  owns the reversed logs as rolled_back_at/by (tag boundaries never fall
  inside a single batch, so those batches' data was fully reversed);
- tag creation leaves a trail in version_tag.created_by/created_at and the tag
  is retained permanently.
"""

import sqlite3

from .changes import edge_key, load_snapshot, now
from .db import get_db


def _now() -> str:
    return now()


def _edge_created_by(conn, snap: dict, actor: str, log_id: int) -> str:
    """Restore the original creator when restoring a deleted edge.

    The snapshot contains only business columns (``EDGE_SNAPSHOT_KEYS``), not
    audit columns; the original creator is restored from the actor of the most
    recent ``added`` log for this natural key before this ``deleted`` log (when
    the same natural key was deleted and recreated, use the recreator). When the
    log is missing (history was trimmed), fall back to the current rollback
    executor so ``created_by`` is never NULL.
    """
    if snap.get("created_by"):
        return str(snap["created_by"])
    key = edge_key(snap["from_dataset"], snap["from_field"],
                   snap["to_dataset"], snap["to_field"])
    row = conn.execute(
        "SELECT actor FROM change_log WHERE entity_kind='edge'"
        " AND entity_key=? AND op='added' AND id < ? ORDER BY id DESC LIMIT 1",
        (key, log_id)).fetchone()
    return row["actor"] if row is not None else actor


def _restore_row(conn, table: str, snap: dict, actor: str, log_id: int) -> None:
    """Reinsert a row (reversal of deleted).

    Uses an idempotent form: if the target row already exists, update it to the
    snapshot values, keeping repeated rollbacks safe; edge natural keys contain
    NULL and SQLite's partial unique index cannot be an ON CONFLICT target, so
    read before writing.

    Audit columns: ``created_by`` prefers the original creator (see
    ``_edge_created_by``); an existing non-null value is not overwritten and
    NULL is backfilled; ``updated_by`` records the executor of this
    restore/rollback.
    """
    if table == "dataset":
        conn.execute(
            "INSERT INTO dataset(id, name, description, created_at, updated_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " description=excluded.description, updated_at=excluded.updated_at",
            (snap["id"], snap["name"], snap["description"], _now(), _now()))
    elif table == "field":
        conn.execute(
            "INSERT INTO field(dataset_id, name, field_type, source_file_id,"
            " src_locator, description, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(dataset_id, name) DO UPDATE SET"
            " field_type=excluded.field_type,"
            " source_file_id=excluded.source_file_id,"
            " src_locator=excluded.src_locator,"
            " description=excluded.description,"
            " updated_at=excluded.updated_at",
            (snap["dataset_id"], snap["name"], snap["field_type"],
             snap["source_file_id"], snap["src_locator"], snap["description"],
             _now(), _now()))
    elif table == "edge":
        existing = conn.execute(
            "SELECT id FROM edge WHERE from_dataset=? AND from_field IS ? AND"
            " to_dataset=? AND to_field IS ?",
            (snap["from_dataset"], snap["from_field"], snap["to_dataset"],
             snap["to_field"])).fetchone()
        if existing is not None:
            # An existing non-null created_by is not overwritten; a historical NULL is backfilled with the original creator
            conn.execute(
                "UPDATE edge SET transform=?, confidence=?, source=?, note=?,"
                " created_by=COALESCE(created_by, ?), updated_by=?,"
                " updated_at=? WHERE id=?",
                (snap["transform"], snap["confidence"], snap["source"],
                 snap["note"], _edge_created_by(conn, snap, actor, log_id),
                 actor, _now(), existing["id"]))
            return
        conn.execute(
            "INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
            " transform, confidence, source, note, created_by, updated_by,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (snap["from_dataset"], snap["from_field"], snap["to_dataset"],
             snap["to_field"], snap["transform"], snap["confidence"],
             snap["source"], snap["note"],
             _edge_created_by(conn, snap, actor, log_id),
             actor, _now(), _now()))


def _delete_row(conn, table: str, snap: dict) -> None:
    if table == "dataset":
        conn.execute("DELETE FROM dataset WHERE id=?", (snap["id"],))
    elif table == "field":
        conn.execute("DELETE FROM field WHERE dataset_id=? AND name=?",
                     (snap["dataset_id"], snap["name"]))
    elif table == "edge":
        conn.execute(
            "DELETE FROM edge WHERE from_dataset=? AND from_field IS ? AND"
            " to_dataset=? AND to_field IS ?",
            (snap["from_dataset"], snap["from_field"], snap["to_dataset"],
             snap["to_field"]))


def _restore_update(conn, table: str, snap: dict) -> None:
    if table == "dataset":
        conn.execute("UPDATE dataset SET name=?, description=? WHERE id=?",
                     (snap["name"], snap["description"], snap["id"]))
    elif table == "field":
        conn.execute(
            "UPDATE field SET field_type=?, source_file_id=?, src_locator=?,"
            " description=? WHERE dataset_id=? AND name=?",
            (snap["field_type"], snap["source_file_id"], snap["src_locator"],
             snap["description"], snap["dataset_id"], snap["name"]))
    elif table == "edge":
        conn.execute(
            "UPDATE edge SET transform=?, confidence=?, source=?, note=?"
            " WHERE from_dataset=? AND from_field IS ? AND to_dataset=? AND to_field IS ?",
            (snap["transform"], snap["confidence"], snap["source"], snap["note"],
             snap["from_dataset"], snap["from_field"], snap["to_dataset"],
             snap["to_field"]))


def _reverse_log(conn, log, actor: str) -> None:
    """Reverse one change_log entry; shared by batch rollback and tag rollback."""
    kind, op = log["entity_kind"], log["op"]
    before = load_snapshot(log["before"])
    after = load_snapshot(log["after"])
    if op == "added":
        _delete_row(conn, kind, after)
    elif op == "updated":
        _restore_update(conn, kind, before)
    elif op == "deleted":
        _restore_row(conn, kind, before, actor, log["id"])


def _reverse_logs(conn, logs, conflict_message: str, actor: str) -> None:
    try:
        for log in logs:
            _reverse_log(conn, log, actor)
    except sqlite3.IntegrityError as e:
        # Foreign-key/unique-constraint conflict: raise ValueError so the route
        # layer turns it into 409 (get_db rolls back the whole transaction)
        raise ValueError(conflict_message) from e


def rollback_batch(batch_id: int, actor: str) -> int:
    """Reverse all changes of one import batch and return the number of reversed logs."""
    with get_db() as conn:
        batch = conn.execute("SELECT * FROM import_batch WHERE id=?",
                             (batch_id,)).fetchone()
        if batch is None:
            raise LookupError(f"Import batch {batch_id} does not exist")
        if batch["rolled_back_at"]:
            raise ValueError(
                f"Batch v{batch['version_no']} was already rolled back at"
                f" {batch['rolled_back_at']}")

        logs = conn.execute(
            "SELECT * FROM change_log WHERE batch_id=? ORDER BY id DESC",
            (batch_id,)).fetchall()
        _reverse_logs(
            conn, logs,
            "Edges from a later batch reference fields in this batch;"
            " roll back the later batches first", actor)

        conn.execute(
            "UPDATE import_batch SET rolled_back_at=?, rolled_back_by=? WHERE id=?",
            (_now(), actor, batch_id))
        return len(logs)


# ---------- Version tags ----------

def _tag_row(conn, name: str):
    return conn.execute("SELECT * FROM version_tag WHERE name=?",
                        (name,)).fetchone()


def create_tag(name: str, note: str | None, actor: str) -> dict:
    """Place a business tag at the current end of change_log."""
    with get_db() as conn:
        if _tag_row(conn, name) is not None:
            raise ValueError(f"Version tag \"{name}\" already exists")
        change_seq = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS n FROM change_log").fetchone()["n"]
        # batch_id is informational only (rollback does not depend on it): take
        # the most recent import batch
        batch_id = conn.execute(
            "SELECT MAX(id) AS n FROM import_batch").fetchone()["n"]
        conn.execute(
            "INSERT INTO version_tag(name, note, batch_id, change_seq,"
            " created_by, created_at) VALUES (?,?,?,?,?,?)",
            (name, note, batch_id, change_seq, actor, _now()))
        return dict(_tag_row(conn, name))


def list_tags() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, note, batch_id, change_seq, created_by, created_at"
            " FROM version_tag ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _already_reversed(conn: sqlite3.Connection, log: sqlite3.Row) -> bool:
    """Whether this log was already reversed by an earlier rollback (skip it on repeated rollback).

    Two audit trails cover the same decision: batch logs look at
    ``import_batch.rolled_back_at``; manual logs look at the reversed range
    ``(from_change_seq, to_change_seq]`` in ``rollback_record``.
    """
    if log["batch_id"] is not None:
        row = conn.execute(
            "SELECT 1 FROM import_batch WHERE id=? AND rolled_back_at IS NOT NULL",
            (log["batch_id"],)).fetchone()
        if row is not None:
            return True
    row = conn.execute(
        "SELECT 1 FROM rollback_record WHERE ? > from_change_seq"
        " AND ? <= to_change_seq LIMIT 1",
        (log["id"], log["id"])).fetchone()
    return row is not None


def rollback_to_tag(name: str, actor: str) -> int:
    """Reverse all change_log entries after the tag's change_seq (including manual edits) and return the count.

    Reversal does not write change_log; logs already reversed by a previous
    rollback are skipped (``_already_reversed``), so a repeated rollback has no
    side effects and returns 0 — consistent with API contract §12.4. Each call
    appends one rollback_record audit row. The import batches owning the
    reversed logs also get ``rolled_back_at/by`` so the version drawer's batch
    status matches the current data.
    """
    with get_db() as conn:
        tag = _tag_row(conn, name)
        if tag is None:
            raise LookupError(f"Version tag \"{name}\" does not exist")
        to_seq = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS n FROM change_log").fetchone()["n"]
        logs = conn.execute(
            "SELECT * FROM change_log WHERE id > ? ORDER BY id DESC",
            (tag["change_seq"],)).fetchall()
        pending = [log for log in logs if not _already_reversed(conn, log)]
        _reverse_logs(
            conn, pending,
            "Rollback hit a referential-integrity conflict: first delete lineage"
            " edges created after this tag that reference fields about to be deleted",
            actor)
        # The batches owning the reversed logs have effectively returned to the
        # tag point, so mark their status too, preventing the version drawer from
        # still showing stale batches as "active". Repeated rollbacks keep the
        # first timestamp.
        batch_ids = sorted({log["batch_id"] for log in pending
                            if log["batch_id"] is not None})
        if batch_ids:
            placeholders = ", ".join("?" for _ in batch_ids)
            conn.execute(
                f"UPDATE import_batch SET"
                f" rolled_back_at=COALESCE(rolled_back_at, ?),"
                f" rolled_back_by=COALESCE(rolled_back_by, ?)"
                f" WHERE id IN ({placeholders})",
                (_now(), actor, *batch_ids))
        conn.execute(
            "INSERT INTO rollback_record(tag_name, from_change_seq, to_change_seq,"
            " reverted, actor, created_at) VALUES (?,?,?,?,?,?)",
            (name, tag["change_seq"], to_seq, len(pending), actor, _now()))
        return len(pending)


def tag_diff(from_name: str, to_name: str) -> dict:
    """Net changes between two business tags (change_log range merged by entity_key).

    - The first before in the range is the range-start state; the last after is
      the end state;
    - both start and end empty (added then deleted inside the range) means no
      net change;
    - net additions/deletions/value changes count as added/deleted/updated.
    """
    with get_db() as conn:
        from_tag = _tag_row(conn, from_name)
        to_tag = _tag_row(conn, to_name)
    if from_tag is None:
        raise LookupError(f"Version tag \"{from_name}\" does not exist")
    if to_tag is None:
        raise LookupError(f"Version tag \"{to_name}\" does not exist")
    if from_tag["change_seq"] > to_tag["change_seq"]:
        raise ValueError(
            f"Start tag \"{from_name}\" is later than end tag \"{to_name}\";"
            " cannot compute the diff")

    with get_db() as conn:
        logs = conn.execute(
            "SELECT * FROM change_log WHERE id > ? AND id <= ? ORDER BY id",
            (from_tag["change_seq"], to_tag["change_seq"])).fetchall()

    states: dict[tuple[str, str], dict] = {}
    for log in logs:
        key = (log["entity_kind"], log["entity_key"])
        entry = states.get(key)
        if entry is None:
            # The first log's before represents the range-start state
            entry = {"before": load_snapshot(log["before"]), "after": None}
            states[key] = entry
        entry["after"] = load_snapshot(log["after"])

    items = []
    summary = {"added": 0, "updated": 0, "deleted": 0}
    for (entity_kind, entity_key), entry in sorted(states.items()):
        before, after = entry["before"], entry["after"]
        if before is None and after is None:
            continue
        if before is None:
            op = "added"
        elif after is None:
            op = "deleted"
        elif before != after:
            op = "updated"
        else:
            continue
        summary[op] += 1
        items.append({
            "entity_kind": entity_kind,
            "entity_key": entity_key,
            "op": op,
            "before": before,
            "after": after,
        })
    return {
        "summary": summary,
        "items": items,
    }


def get_snapshot() -> dict:
    """Current lineage state snapshot (for rollback verification and basic browsing)."""
    with get_db() as conn:
        datasets = [dict(r) for r in conn.execute("SELECT id, name FROM dataset ORDER BY id")]
        fields = [dict(r) for r in conn.execute(
            "SELECT dataset_id, name, field_type, source_file_id, description"
            " FROM field ORDER BY dataset_id, name")]
        edges = [dict(r) for r in conn.execute(
            "SELECT from_dataset, from_field, to_dataset, to_field, transform,"
            " confidence, source, note FROM edge"
            " ORDER BY from_dataset, from_field, to_dataset, to_field")]
    return {"datasets": datasets, "fields": fields, "edges": edges}
