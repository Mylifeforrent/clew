"""M4/M5 lineage suggestions: AI-suggested edges take effect only after manual confirmation (business invariant #4).

Heuristics (M4, no LLM call, runs offline):
1. **Same-name fields first**: field names are lowercased and underscores removed;
   exact equality → confidence 0.7;
2. **Containment next**: after underscore removal and lowercasing, one contains
   the other (the shorter one at least 3 characters) → confidence 0.6;
3. Exclude existing edges (both directions, to avoid suggesting reverse
   duplicates/cycles);
4. Candidates are persisted with ``source='ai'`` and written to change_log(added);
5. ``confirm`` changes source to manual and writes change_log(updated);
   ``reject`` deletes the candidate edge and writes change_log(deleted).

Semantic layer (M5, evolution plan 07 §3#9): when EMBEDDING_* is configured,
field names + descriptions are vectorized and cross-dataset field pairs with
cosine ≥ SEMANTIC_THRESHOLD are added as candidates (confidence 0.65); when
embeddings are not configured or the call fails, it **silently degrades** to
pure heuristics.

Candidate direction: the dataset/field given in the request is upstream (from),
and similar fields in other datasets are downstream (to).
"""

from __future__ import annotations

import sqlite3

from ..changes import edge_key, edge_snapshot, log_change, now

MAX_SUGGESTIONS = 20
EXACT_CONFIDENCE = 0.7
CONTAINMENT_CONFIDENCE = 0.6
MIN_CONTAINMENT_LENGTH = 3
SEMANTIC_CONFIDENCE = 0.65
SEMANTIC_THRESHOLD = 0.75

_EDGE_COLUMNS = (
    "id, from_dataset, from_field, to_dataset, to_field, transform,"
    " confidence, source, note, created_by, updated_by, created_at, updated_at"
)


def normalize_field_name(name: str) -> str:
    """Contract-defined normalization: lowercase + remove underscores."""
    return name.strip().lower().replace("_", "")


def _focus_fields(conn: sqlite3.Connection, dataset: str,
                  field: str | None) -> list[sqlite3.Row]:
    if conn.execute("SELECT 1 FROM dataset WHERE id=?", (dataset,)).fetchone() is None:
        raise LookupError(f"Dataset \"{dataset}\" does not exist")
    if field is not None:
        rows = conn.execute(
            "SELECT dataset_id, name FROM field WHERE dataset_id=? AND name=?",
            (dataset, field)).fetchall()
        if not rows:
            raise LookupError(f"Field \"{dataset}.{field}\" does not exist")
        return rows
    return conn.execute(
        "SELECT dataset_id, name FROM field WHERE dataset_id=? ORDER BY name",
        (dataset,)).fetchall()


def _target_fields(conn: sqlite3.Connection,
                   source_dataset: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT dataset_id, name FROM field WHERE dataset_id <> ?"
        " ORDER BY dataset_id, name",
        (source_dataset,)).fetchall()


def _existing_edge_keys(conn: sqlite3.Connection) -> set[tuple]:
    """Natural-key set of existing edges (including reverse), used to exclude duplicate suggestions."""
    keys: set[tuple] = set()
    rows = conn.execute(
        "SELECT from_dataset, from_field, to_dataset, to_field FROM edge").fetchall()
    for row in rows:
        key = (row["from_dataset"], row["from_field"],
               row["to_dataset"], row["to_field"])
        keys.add(key)
        keys.add((row["to_dataset"], row["to_field"],
                  row["from_dataset"], row["from_field"]))
    return keys


def _match(focus_name: str, target_name: str) -> tuple[float, str] | None:
    left = normalize_field_name(focus_name)
    right = normalize_field_name(target_name)
    if not left or not right:
        return None
    if left == right:
        return (EXACT_CONFIDENCE,
                f"same-name field (ignoring case and underscores):"
                f" {focus_name} and {target_name}")
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= MIN_CONTAINMENT_LENGTH and shorter in longer:
        return (CONTAINMENT_CONFIDENCE,
                "field names are highly similar (containment after ignoring case"
                " and underscores): "
                f"{focus_name} and {target_name}")
    return None


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(x * y for x, y in zip(left, right))
    norm_left = sum(x * x for x in left) ** 0.5
    norm_right = sum(y * y for y in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


def _augment_semantic(
    conn: sqlite3.Connection,
    dataset: str,
    field: str | None,
    existing: set[tuple],
    seen: set[tuple],
    candidates: list[dict],
) -> list[dict]:
    """Semantic layer (M5): when embeddings are available, add candidates that the same-name rule misses.

    Any failure (not configured / network / dimension mismatch) degrades
    silently — semantics are best-effort and must not break pure-heuristic
    availability.
    """
    from . import llm  # Lazy import to avoid circular dependencies with test stubs

    try:
        embeddings = llm.get_embeddings()
        if embeddings is None:
            return candidates
        focus_rows = conn.execute(
            "SELECT dataset_id, name, COALESCE(description, '') AS description"
            " FROM field WHERE dataset_id=?"
            + (" AND name=?" if field else "") + " ORDER BY name",
            (dataset, field) if field else (dataset,),
        ).fetchall()
        target_rows = conn.execute(
            "SELECT dataset_id, name, COALESCE(description, '') AS description"
            " FROM field WHERE dataset_id <> ? ORDER BY dataset_id, name",
            (dataset,)).fetchall()
        rows = [*focus_rows, *target_rows]
        if not rows:
            return candidates
        vectors = llm.embed_texts(
            [f"{row['name']} {row['description']}".strip() for row in rows])
        if len(vectors) != len(rows):
            return candidates
        vectors = vectors[:len(focus_rows)], vectors[len(focus_rows):]
        focus_vectors, target_vectors = vectors

        semantic: list[dict] = []
        for focus_row, focus_vec in zip(focus_rows, focus_vectors):
            for target_row, target_vec in zip(target_rows, target_vectors):
                key = (focus_row["dataset_id"], focus_row["name"],
                       target_row["dataset_id"], target_row["name"])
                if key in existing or key in seen:
                    continue
                score = _cosine(focus_vec, target_vec)
                if score < SEMANTIC_THRESHOLD:
                    continue
                seen.add(key)
                semantic.append({
                    "from_dataset": focus_row["dataset_id"],
                    "from_field": focus_row["name"],
                    "to_dataset": target_row["dataset_id"],
                    "to_field": target_row["name"],
                    "confidence": SEMANTIC_CONFIDENCE,
                    "reason": f"semantically similar (embedding cosine {score:.2f}): "
                              f"{focus_row['name']} and {target_row['name']}",
                })
        return candidates + semantic
    except Exception:  # noqa: BLE001 — any semantic-layer exception degrades to pure heuristics
        return candidates


def suggest_edges(conn: sqlite3.Connection, dataset: str, field: str | None,
                  actor: str) -> list[dict]:
    """Generate and persist AI candidate edges, returning the candidates newly added by this call.

    The return value strictly matches the API contract:
    ``[{from_dataset, from_field, to_dataset, to_field, confidence, reason}]``.
    An edge that already exists for the same natural key is skipped, so repeated
    calls do not duplicate persistence.
    """
    focus_rows = _focus_fields(conn, dataset, field)
    target_rows = _target_fields(conn, dataset)
    existing = _existing_edge_keys(conn)

    candidates: list[dict] = []
    seen: set[tuple] = set()
    for focus in focus_rows:
        for target in target_rows:
            key = (focus["dataset_id"], focus["name"],
                   target["dataset_id"], target["name"])
            if key in existing or key in seen:
                continue
            match = _match(focus["name"], target["name"])
            if match is None:
                continue
            confidence, reason = match
            seen.add(key)
            candidates.append({
                "from_dataset": focus["dataset_id"],
                "from_field": focus["name"],
                "to_dataset": target["dataset_id"],
                "to_field": target["name"],
                "confidence": confidence,
                "reason": reason,
            })

    # M5 semantic layer: when embeddings are fully configured, add semantically
    # similar candidates (failures degrade silently)
    candidates = _augment_semantic(
        conn, dataset, field, existing, seen, candidates)

    # Same-name (0.7) ranks above semantic/containment (0.65/0.6); ties are stably
    # ordered by target field
    candidates.sort(key=lambda item: (
        -item["confidence"], item["to_dataset"], item["to_field"],
        item["from_dataset"], item["from_field"]))
    candidates = candidates[:MAX_SUGGESTIONS]

    timestamp = now()
    for candidate in candidates:
        cur = conn.execute(
            "INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
            " transform, confidence, source, note, created_by, updated_by,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (candidate["from_dataset"], candidate["from_field"],
             candidate["to_dataset"], candidate["to_field"],
             None, candidate["confidence"], "ai", candidate["reason"],
             actor, actor, timestamp, timestamp))
        row = conn.execute(
            f"SELECT {_EDGE_COLUMNS} FROM edge WHERE id=?",
            (cur.lastrowid,)).fetchone()
        log_change(
            conn, entity_kind="edge",
            entity_key=edge_key(candidate["from_dataset"],
                                candidate["from_field"],
                                candidate["to_dataset"],
                                candidate["to_field"]),
            op="added", before=None, after=edge_snapshot(row), actor=actor)
    return candidates


def _ai_edge(conn: sqlite3.Connection, from_dataset: str,
             from_field: str | None, to_dataset: str,
             to_field: str | None) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT {_EDGE_COLUMNS} FROM edge"
        " WHERE from_dataset=? AND from_field IS ?"
        " AND to_dataset=? AND to_field IS ? AND source='ai'",
        (from_dataset, from_field, to_dataset, to_field)).fetchone()
    if row is None:
        raise LookupError(
            "AI suggested edge does not exist or has already been processed"
            " (only source='ai' candidates can be confirmed/rejected)")
    return row


def confirm_suggestion(conn: sqlite3.Connection, from_dataset: str,
                       from_field: str | None, to_dataset: str,
                       to_field: str | None, actor: str) -> dict:
    """Turn an AI candidate edge into a manual edge (source='manual') and write change_log(updated)."""
    row = _ai_edge(conn, from_dataset, from_field, to_dataset, to_field)
    before = edge_snapshot(row)
    conn.execute(
        "UPDATE edge SET source='manual', updated_by=?, updated_at=? WHERE id=?",
        (actor, now(), row["id"]))
    after = {**before, "source": "manual"}
    log_change(
        conn, entity_kind="edge",
        entity_key=edge_key(from_dataset, from_field, to_dataset, to_field),
        op="updated", before=before, after=after, actor=actor)
    saved = conn.execute(
        f"SELECT {_EDGE_COLUMNS} FROM edge WHERE id=?", (row["id"],)).fetchone()
    return dict(saved)


def reject_suggestion(conn: sqlite3.Connection, from_dataset: str,
                      from_field: str | None, to_dataset: str,
                      to_field: str | None, actor: str) -> None:
    """Delete an AI candidate edge and write change_log(deleted)."""
    row = _ai_edge(conn, from_dataset, from_field, to_dataset, to_field)
    before = edge_snapshot(row)
    conn.execute("DELETE FROM edge WHERE id=?", (row["id"],))
    log_change(
        conn, entity_kind="edge",
        entity_key=edge_key(from_dataset, from_field, to_dataset, to_field),
        op="deleted", before=before, after=None, actor=actor)
