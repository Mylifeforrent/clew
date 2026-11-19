"""AI auto-description: draft → manual confirmation → annotation (M5, evolution plan 07 §4.5).

Drafts live in the ``description_draft`` workspace table and **never touch** ``field.description``
(the original imported value; business invariant: imported originals and manual insights are
separated); accepting writes an annotation (append-only business note), while rejecting marks it
rejected so the field is not regenerated.

Generation input: field name/type/current description + upstream/downstream edges + same-named
fields in other datasets—all from existing read-only queries, with no extra data fetched from the
network; generation goes through the unified LLM access layer (llm.complete).
"""

from __future__ import annotations

import sqlite3

from ..changes import now
from . import llm
from .llm import LLMError, LLMNotConfigured

MAX_DRAFT_FIELDS = 10
DRAFT_MAX_CHARS = 200

_DRAFT_PROMPT = """You are a documentation assistant for a data catalog. Write a one-sentence English description (at most 60 characters) for the data field below, explaining what it is and where it comes from (if upstream information is given). Output only the description itself, with no prefix, quotes, or explanation.

Field: {dataset}.{name} (type {field_type})
Current description: {description}
Upstream/downstream lineage: {lineage}
Same-named fields in other datasets: {siblings}
"""


class DescriptionError(RuntimeError):
    """Business error in draft generation/transition (the route layer maps it to 400/404)."""


# ---------- Generation ----------


def _field_context(conn: sqlite3.Connection, dataset: str, name: str) -> dict:
    row = conn.execute(
        "SELECT name, field_type, COALESCE(description, '') AS description"
        " FROM field WHERE dataset_id=? AND name=?", (dataset, name)).fetchone()
    if row is None:
        raise LookupError(f'Field "{dataset}.{name}" does not exist')
    edges = conn.execute(
        "SELECT from_dataset, from_field, to_dataset, to_field, transform,"
        " confidence FROM edge"
        " WHERE (from_dataset=? AND from_field=?) OR (to_dataset=? AND to_field=?)"
        " ORDER BY id LIMIT 8", (dataset, name, dataset, name)).fetchall()
    lineage = "; ".join(
        f"{e['from_dataset']}.{e['from_field']} → {e['to_dataset']}.{e['to_field']}"
        f" ({e['transform'] or 'not set'}, confidence {e['confidence']})" for e in edges
    ) or "none"
    siblings = conn.execute(
        "SELECT dataset_id || '.' || name AS ref FROM field"
        " WHERE name=? AND dataset_id<>? ORDER BY dataset_id LIMIT 5",
        (name, dataset)).fetchall()
    return {
        "dataset": dataset,
        "name": name,
        "field_type": row["field_type"] or "unknown",
        "description": row["description"] or "(empty)",
        "lineage": lineage,
        "siblings": ", ".join(s["ref"] for s in siblings) or "none",
    }


def draft_descriptions(conn: sqlite3.Connection, dataset: str,
                       fields: list[str], actor: str) -> list[dict]:
    """Generate description drafts for a set of fields and persist them as pending; return the confirmable draft list.

    - When ``fields`` is empty, automatically select fields in the dataset with empty descriptions (up to MAX_DRAFT_FIELDS);
    - Fields that already have a pending draft are skipped; rejected fields are also skipped (not regenerated);
    - A per-field generation failure does not block the remaining fields.
    """
    if conn.execute("SELECT 1 FROM dataset WHERE id=?", (dataset,)).fetchone() is None:
        raise LookupError(f'Dataset "{dataset}" does not exist')

    if fields:
        placeholders = ",".join("?" for _ in fields[:MAX_DRAFT_FIELDS])
        rows = conn.execute(
            f"SELECT name FROM field WHERE dataset_id=? AND name IN ({placeholders})"
            " ORDER BY name", (dataset, *fields[:MAX_DRAFT_FIELDS])).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM field WHERE dataset_id=?"
            " AND (description IS NULL OR description='')"
            " ORDER BY name LIMIT ?", (dataset, MAX_DRAFT_FIELDS)).fetchall()
    if not rows:
        raise LookupError("No fields to draft (fields do not exist, or all descriptions are filled and no fields were specified)")

    blocked = {
        r["field_name"] for r in conn.execute(
            "SELECT field_name FROM description_draft WHERE dataset_id=?"
            " AND status IN ('pending','accepted','rejected')", (dataset,)).fetchall()
    }
    targets = [r["name"] for r in rows if r["name"] not in blocked][:MAX_DRAFT_FIELDS]
    if not targets:
        raise LookupError(
            "All selected fields already have drafts (pending/accepted/rejected); handle them in the drafts area first")

    timestamp = now()
    settings_model = "unknown"
    try:
        settings_model = llm.get_chat_model().model_name or "unknown"
    except Exception:  # The model name is audit-only; failure must not block
        pass

    drafts: list[dict] = []
    for name in targets:
        context = _field_context(conn, dataset, name)
        try:
            response = llm.complete(
                [{"role": "user",
                  "content": _DRAFT_PROMPT.format(**context)}])
            content = response["choices"][0]["message"]["content"]
            draft = (content or "").strip().splitlines()[0][:DRAFT_MAX_CHARS]
        except (LLMError, LLMNotConfigured, KeyError, IndexError):
            continue  # A single-field failure must not block
        if not draft:
            continue
        cur = conn.execute(
            "INSERT INTO description_draft(dataset_id, field_name, draft,"
            " model, status, created_at) VALUES (?,?,?,?,'pending',?)",
            (dataset, name, draft, settings_model, timestamp))
        row = conn.execute(
            "SELECT id, dataset_id, field_name, draft, model, status, created_at"
            " FROM description_draft WHERE id=?", (cur.lastrowid,)).fetchone()
        drafts.append(dict(row))
    if not drafts:
        raise DescriptionError("Failed to generate description drafts: the LLM returned no valid content; try again later")
    return drafts


# ---------- Confirmation flow ----------


def list_drafts(conn: sqlite3.Connection, dataset: str | None,
                status: str | None) -> list[dict]:
    sql = ("SELECT id, dataset_id, field_name, draft, model, status, created_at,"
           " decided_at FROM description_draft WHERE 1=1")
    params: list[str] = []
    if dataset:
        sql += " AND dataset_id=?"
        params.append(dataset)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 100"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _pending_draft(conn: sqlite3.Connection, draft_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, dataset_id, field_name, draft, status FROM description_draft"
        " WHERE id=?", (draft_id,)).fetchone()
    if row is None:
        raise LookupError(f"Description draft #{draft_id} does not exist")
    if row["status"] != "pending":
        raise DescriptionError(f'Draft #{draft_id} has already been handled ({row["status"]})')
    return row


def accept_draft(conn: sqlite3.Connection, draft_id: int, actor: str) -> dict:
    """Accept a draft: write an annotation (append-only business note) + mark accepted."""
    row = _pending_draft(conn, draft_id)
    conn.execute(
        "INSERT INTO annotation(target_kind, target_id, body, author, created_at)"
        " VALUES ('field', ?, ?, ?, ?)",
        (f"{row['dataset_id']}.{row['field_name']}",
         f"[AI description accepted | model={conn.execute('SELECT model FROM description_draft WHERE id=?', (draft_id,)).fetchone()['model']}] {row['draft']}",
         actor, now()))
    conn.execute(
        "UPDATE description_draft SET status='accepted', decided_at=? WHERE id=?",
        (now(), draft_id))
    return dict(conn.execute(
        "SELECT id, dataset_id, field_name, draft, model, status, created_at,"
        " decided_at FROM description_draft WHERE id=?", (draft_id,)).fetchone())


def reject_draft(conn: sqlite3.Connection, draft_id: int, actor: str) -> None:
    """Reject a draft: mark rejected (the field is not regenerated)."""
    row = _pending_draft(conn, draft_id)
    conn.execute(
        "UPDATE description_draft SET status='rejected', decided_at=? WHERE id=?",
        (now(), draft_id))
