"""Change-log writes and row snapshot helpers (shared by M3 manual editing).

``change_log`` is the sole basis for version reconstruction (data model §7):
- the import path writes ``batch_id=<batch>`` from ``import_service``;
- the manual-edit path (fields/edges, excluding tag rollbacks) writes
  ``batch_id=NULL`` and uses the current logged-in user as actor;
- annotations are append-only, never modified, **do not write change_log**, and
  are not deleted by rollbacks;
- version tag creation leaves a trail in ``version_tag.created_by/created_at``
  and also does not write change_log; otherwise "roll back to tag" would treat
  the tag itself as reversible data and delete it, violating the semantics of
  permanently retained tags.

Snapshots contain only business columns (no id / timestamps); fields and edges
each have a fixed key set so the before/after of the same entity can be used
directly for version diffs and reversal.
"""

import json
from datetime import UTC, datetime

# Keep consistent with the snapshot keys written by the import path
# (import_service._upsert_field / lineage edge snapshots)
FIELD_SNAPSHOT_KEYS = (
    "dataset_id", "name", "field_type", "source_file_id",
    "src_locator", "description",
)
EDGE_SNAPSHOT_KEYS = (
    "from_dataset", "from_field", "to_dataset", "to_field",
    "transform", "confidence", "source", "note",
)


def now() -> str:
    """Uniform time format: ISO8601 UTC (second precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def snapshot(row, keys: tuple[str, ...]) -> dict:
    """Extract a business snapshot from a sqlite3.Row / dict."""
    return {key: row[key] for key in keys}


def field_snapshot(row) -> dict:
    return snapshot(row, FIELD_SNAPSHOT_KEYS)


def edge_snapshot(row) -> dict:
    return snapshot(row, EDGE_SNAPSHOT_KEYS)


def edge_key(from_dataset: str, from_field: str | None,
             to_dataset: str, to_field: str | None) -> str:
    """Polymorphic/log key rule for edges (data model §5.2): use ``*`` for empty fields."""
    return f"{from_dataset}.{from_field or '*'}-->{to_dataset}.{to_field or '*'}"


def log_change(conn, *, entity_kind: str, entity_key: str, op: str,
               before: dict | None, after: dict | None, actor: str,
               batch_id: int | None = None) -> None:
    """Append a change_log row; the caller must be in the same transaction."""
    conn.execute(
        "INSERT INTO change_log(batch_id, entity_kind, entity_key, op,"
        " before, after, actor, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (batch_id, entity_kind, entity_key, op,
         json.dumps(before, ensure_ascii=False, sort_keys=True) if before else None,
         json.dumps(after, ensure_ascii=False, sort_keys=True) if after else None,
         actor, now()))


def load_snapshot(raw: str | None) -> dict | None:
    """change_log.before/after (TEXT) → dict; empty value returns None."""
    return json.loads(raw) if raw else None
