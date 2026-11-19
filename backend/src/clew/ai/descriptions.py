"""AI auto-descriptions: draft → manual confirmation → annotation (M5, evolution plan 07 §4.5).

Drafts live in the ``description_draft`` workspace table and **never touch**
``field.description`` (the original imported value; business invariant: keep
original imports separate from human insight); on acceptance an annotation
(append-only business note) is written, and rejection marks the draft rejected
so no further drafts are generated for that field.

Generation input: field name/type/current description + upstream/downstream
edges + same-named fields in other datasets — all from existing read-only
queries, no extra data fetched from the network; generation calls go through
the unified LLM access layer (llm.complete).
"""

from __future__ import annotations

import sqlite3

from ..changes import now
from . import llm
from .llm import LLMError, LLMNotConfigured

MAX_DRAFT_FIELDS = 10
DRAFT_MAX_CHARS = 200

# Description draft language (doc 08 R12): parameterize the prompt by language,
# so English conversations do not produce Chinese drafts
_DRAFT_PROMPTS = {
    "zh": """You are a documentation assistant for a data catalog. Write one Chinese \
sentence (at most 60 characters) describing the data field below — what it is and how it \
is derived (from upstream info, if given). Output only the description itself: no prefix, \
quotes, or explanations.

Field: {dataset}.{name} (type {field_type})
Current description: {description}
Upstream/downstream lineage: {lineage}
Same-named fields in other datasets: {siblings}
""",
    "en": """You are a data catalog writer. Write one sentence in English (at most 25 words) \
describing the data field below — what it is and how it is derived (from upstream info, \
if given). Output only the description itself: no prefix, quotes, or explanations.

Field: {dataset}.{name} (type {field_type})
Current description: {description}
Upstream/downstream lineage: {lineage}
Same-named fields in other datasets: {siblings}
""",
}


class DescriptionError(RuntimeError):
    """Business error in draft generation/transitions (route layer turns it into 400/404)."""


# ---------- Generation ----------


def _field_context(conn: sqlite3.Connection, dataset: str, name: str) -> dict:
    row = conn.execute(
        "SELECT name, field_type, COALESCE(description, '') AS description"
        " FROM field WHERE dataset_id=? AND name=?", (dataset, name)).fetchone()
    if row is None:
        raise LookupError(f"Field \"{dataset}.{name}\" does not exist")
    edges = conn.execute(
        "SELECT from_dataset, from_field, to_dataset, to_field, transform,"
        " confidence FROM edge"
        " WHERE (from_dataset=? AND from_field=?) OR (to_dataset=? AND to_field=?)"
        " ORDER BY id LIMIT 8", (dataset, name, dataset, name)).fetchall()
    lineage = "; ".join(
        f"{e['from_dataset']}.{e['from_field']} → {e['to_dataset']}.{e['to_field']}"
        f" ({e['transform'] or 'not provided'}, confidence {e['confidence']})" for e in edges
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
                       fields: list[str], actor: str,
                       lang: str = "zh") -> list[dict]:
    """Generate description drafts for a group of fields as pending; return the confirmable draft list.

    - When ``fields`` is empty, automatically pick fields in the dataset whose
      description is empty (up to MAX_DRAFT_FIELDS);
    - fields that already have a pending draft are skipped; rejected fields are
      also skipped (not generated again);
    - a single-field failure does not block the remaining fields;
    - ``lang`` controls the draft language (zh/en, doc 08 R12); unknown values
      are treated as zh.
    """
    prompt_template = _DRAFT_PROMPTS.get(lang, _DRAFT_PROMPTS["zh"])
    if conn.execute("SELECT 1 FROM dataset WHERE id=?", (dataset,)).fetchone() is None:
        raise LookupError(f"Dataset \"{dataset}\" does not exist")

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
        raise LookupError(
            "No fields available for drafting (the fields do not exist, or all"
            " descriptions are filled and no fields were specified)")

    blocked = {
        r["field_name"] for r in conn.execute(
            "SELECT field_name FROM description_draft WHERE dataset_id=?"
            " AND status IN ('pending','accepted','rejected')", (dataset,)).fetchall()
    }
    targets = [r["name"] for r in rows if r["name"] not in blocked][:MAX_DRAFT_FIELDS]
    if not targets:
        raise LookupError(
            "All selected fields already have drafts (pending/accepted/rejected);"
            " process them in the drafts area first")

    timestamp = now()
    settings_model = "unknown"
    try:
        settings_model = llm.get_chat_model().model_name or "unknown"
    except Exception:  # The model name is for auditing only; failure does not block
        pass

    drafts: list[dict] = []
    for name in targets:
        context = _field_context(conn, dataset, name)
        try:
            response = llm.complete(
                [{"role": "user",
                  "content": prompt_template.format(**context)}])
            content = response["choices"][0]["message"]["content"]
            draft = (content or "").strip().splitlines()[0][:DRAFT_MAX_CHARS]
        except (LLMError, LLMNotConfigured, KeyError, IndexError):
            continue  # A single-field failure does not block the rest
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
        raise DescriptionError(
            "Description draft generation failed: the LLM returned no valid"
            " content; please retry later")
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
        raise DescriptionError(
            f"Draft #{draft_id} has already been processed ({row['status']})")
    return row


def accept_draft(conn: sqlite3.Connection, draft_id: int, actor: str) -> dict:
    """Accept a draft: write an annotation (append-only business note) + set accepted."""
    row = _pending_draft(conn, draft_id)
    conn.execute(
        "INSERT INTO annotation(target_kind, target_id, body, author, created_at)"
        " VALUES ('field', ?, ?, ?, ?)",
        (f"{row['dataset_id']}.{row['field_name']}",
         f"[AI description accepted | model={conn.execute('SELECT model FROM description_draft WHERE id=?', (draft_id,)).fetchone()['model']}]{row['draft']}",
         actor, now()))
    conn.execute(
        "UPDATE description_draft SET status='accepted', decided_at=? WHERE id=?",
        (now(), draft_id))
    return dict(conn.execute(
        "SELECT id, dataset_id, field_name, draft, model, status, created_at,"
        " decided_at FROM description_draft WHERE id=?", (draft_id,)).fetchone())


def reject_draft(conn: sqlite3.Connection, draft_id: int, actor: str) -> None:
    """Reject a draft: set rejected (no further drafts for that field)."""
    row = _pending_draft(conn, draft_id)
    conn.execute(
        "UPDATE description_draft SET status='rejected', decided_at=? WHERE id=?",
        (now(), draft_id))
