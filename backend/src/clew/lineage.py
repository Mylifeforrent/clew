"""Lineage graph queries: fetch an N-hop subgraph in one pass via a recursive CTE (design §4.3).

Two seed semantics:

- **Dataset seed** (``field_name is None``): expand N hops bidirectionally or
  unidirectionally along all connected edges (field-level + table-level) to
  obtain the dataset closure;
- **Field seed**: expand precisely along field-level edges; a table-level edge
  (both ``from_field`` / ``to_field`` NULL) is treated as fully connecting the
  fields of the datasets on both sides, i.e. any field on one side reaches all
  fields on the other side.

The response contract's ``GraphPayload``: **all fields** of the datasets in the
closure (with locator envelopes and source files) plus **all edges** between
datasets in the closure. The recursive CTE is written to stay compatible with
SQLite / PostgreSQL (only standard CTE syntax supported by both).
"""

import json
import sqlite3

DIRECTIONS = ("both", "up", "down")
MAX_HOPS = 5


class LineageNotFound(LookupError):
    """The seed dataset or field does not exist."""


def _direction_arms(table_alias: str, direction: str) -> list[str]:
    """Return the predicate fragments for which direction this hop may follow."""
    arms: list[str] = []
    if direction in ("both", "down"):
        arms.append(f"e.from_dataset = {table_alias}.dataset_id")
    if direction in ("both", "up"):
        arms.append(f"e.to_dataset = {table_alias}.dataset_id")
    return arms


def _dataset_closure(conn: sqlite3.Connection, dataset_id: str, hops: int,
                     direction: str) -> list[str]:
    """N-hop closure for a dataset seed (depth 0 is the starting point)."""
    arms = _direction_arms("reach", direction)
    sql = f"""
WITH RECURSIVE reach(dataset_id, hop) AS (
  SELECT ?, 0
  UNION
  SELECT CASE WHEN e.from_dataset = reach.dataset_id
              THEN e.to_dataset ELSE e.from_dataset END,
         reach.hop + 1
  FROM reach
  JOIN edge e ON {' OR '.join(arms)}
  WHERE reach.hop < ?
)
SELECT DISTINCT dataset_id FROM reach ORDER BY dataset_id
"""
    rows = conn.execute(sql, (dataset_id, hops)).fetchall()
    return [r["dataset_id"] for r in rows]


def _field_closure(conn: sqlite3.Connection, dataset_id: str, field_name: str,
                   hops: int, direction: str) -> list[str]:
    """N-hop closure for a field seed, returning the IDs of the datasets hit.

    In the recursive term, table-level edges are expanded via
    ``COALESCE(e.xxx_field, nf.name)`` into **all fields of the destination-side
    dataset**; field-level edges still only connect ``from_field`` /
    ``to_field``. Only one ``field`` alias is joined, avoiding a row product
    from LEFT JOINing both the from/to sides.
    """
    down = direction in ("both", "down")
    up = direction in ("both", "up")
    arms: list[str] = []
    if down:
        arms.append(
            "((reach.field_name = e.from_field OR e.from_field IS NULL)"
            " AND e.from_dataset = reach.dataset_id)")
    if up:
        arms.append(
            "((reach.field_name = e.to_field OR e.to_field IS NULL)"
            " AND e.to_dataset = reach.dataset_id)")
    sql = f"""
WITH RECURSIVE reach(dataset_id, field_name, hop) AS (
  SELECT ?, ?, 0
  UNION
  SELECT CASE WHEN e.from_dataset = reach.dataset_id
              THEN e.to_dataset ELSE e.from_dataset END,
         CASE WHEN e.from_dataset = reach.dataset_id
              THEN COALESCE(e.to_field, nf.name)
              ELSE COALESCE(e.from_field, nf.name) END,
         reach.hop + 1
  FROM reach
  JOIN edge e ON {' OR '.join(arms)}
  -- Join the destination-side fields only when this hop follows a table-level
  -- edge (single-sided JOIN, no row product)
  LEFT JOIN field nf
         ON nf.dataset_id = CASE WHEN e.from_dataset = reach.dataset_id
                                 THEN e.to_dataset ELSE e.from_dataset END
        AND (CASE WHEN e.from_dataset = reach.dataset_id
                  THEN e.to_field ELSE e.from_field END) IS NULL
  WHERE reach.hop < ?
)
SELECT DISTINCT dataset_id FROM reach ORDER BY dataset_id
"""
    rows = conn.execute(sql, (dataset_id, field_name, hops)).fetchall()
    return [r["dataset_id"] for r in rows]


def _parse_locator(raw: str | None) -> dict:
    """Parse the locator envelope; corrupt data degrades to an empty neutral envelope to avoid a 500 on the whole graph."""
    if not raw:
        return {"type": None, "input": None, "resolved": None}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": None, "input": None, "resolved": None}
    if not isinstance(value, dict):
        return {"type": None, "input": None, "resolved": None}
    return value


def _payload(conn: sqlite3.Connection, dataset_ids: list[str]) -> dict:
    """Load all fields of the closure datasets and all edges inside the closure."""
    if not dataset_ids:
        return {"datasets": [], "edges": []}
    marks = ",".join("?" for _ in dataset_ids)

    dataset_rows = conn.execute(
        f"SELECT id, name FROM dataset WHERE id IN ({marks}) ORDER BY id",
        dataset_ids).fetchall()
    field_rows = conn.execute(
        f"SELECT f.dataset_id, f.name, f.field_type, f.description,"
        f" f.src_locator, s.id AS source_file_id, s.original_name"
        f" FROM field f JOIN source_file s ON s.id = f.source_file_id"
        f" WHERE f.dataset_id IN ({marks}) ORDER BY f.dataset_id, f.name",
        dataset_ids).fetchall()

    fields_by_dataset: dict[str, list[dict]] = {ds_id: [] for ds_id in dataset_ids}
    for row in field_rows:
        fields_by_dataset[row["dataset_id"]].append({
            "name": row["name"],
            "field_type": row["field_type"],
            "description": row["description"],
            "src_locator": _parse_locator(row["src_locator"]),
            "source_file": {"id": row["source_file_id"],
                            "original_name": row["original_name"]},
        })

    datasets = [{"id": row["id"], "name": row["name"],
                 "fields": fields_by_dataset.get(row["id"], [])}
                for row in dataset_rows]

    edge_rows = conn.execute(
        f"SELECT id, from_dataset, from_field, to_dataset, to_field, transform,"
        f" confidence, source, note FROM edge"
        f" WHERE from_dataset IN ({marks}) AND to_dataset IN ({marks})"
        f" ORDER BY from_dataset, COALESCE(from_field, ''),"
        f" to_dataset, COALESCE(to_field, '')",
        [*dataset_ids, *dataset_ids]).fetchall()
    edges = [{
        "id": row["id"],
        "from_dataset": row["from_dataset"],
        "from_field": row["from_field"],
        "to_dataset": row["to_dataset"],
        "to_field": row["to_field"],
        "transform": row["transform"],
        "confidence": row["confidence"],
        "source": row["source"],
        "note": row["note"],
    } for row in edge_rows]
    return {"datasets": datasets, "edges": edges}


def lineage_subgraph(conn: sqlite3.Connection, dataset_id: str,
                     field_name: str | None = None, hops: int = 3,
                     direction: str = "both") -> dict:
    """Return the N-hop lineage subgraph seeded by a dataset or field (GraphPayload)."""
    if direction not in DIRECTIONS:
        raise ValueError(
            f"direction must be one of {'/'.join(DIRECTIONS)}, got \"{direction}\"")
    if not isinstance(hops, int) or isinstance(hops, bool) or not 1 <= hops <= MAX_HOPS:
        raise ValueError(
            f"hops must be an integer between 1 and {MAX_HOPS}, got \"{hops}\"")

    dataset = conn.execute("SELECT id, name FROM dataset WHERE id=?",
                           (dataset_id,)).fetchone()
    if dataset is None:
        raise LineageNotFound(f"Dataset \"{dataset_id}\" does not exist")

    if field_name is None:
        closure = _dataset_closure(conn, dataset_id, hops, direction)
    else:
        field = conn.execute(
            "SELECT 1 FROM field WHERE dataset_id=? AND name=?",
            (dataset_id, field_name)).fetchone()
        if field is None:
            raise LineageNotFound(f"Field \"{dataset_id}.{field_name}\" does not exist")
        closure = _field_closure(conn, dataset_id, field_name, hops, direction)

    return _payload(conn, closure)
