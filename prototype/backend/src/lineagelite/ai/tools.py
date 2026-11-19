"""LLM read-only toolset (M4/M5): reuse existing query capabilities and return JSON-serializable results.

The tools are read-only and never write the business database; each function accepts a
``sqlite3.Connection`` which ``chat.py`` opens via ``get_db()`` for each tool round. Two
exceptions (neither touches business data):

- ``suggest_lineage``: writes lineage candidates as ``source='ai'`` edges (effective only after
  manual confirmation, business invariant #4);
- ``draft_descriptions``: writes description drafts to the ``description_draft`` workspace table.

- ``search_fields``: fuzzy search over field name/dataset/description/annotation (lightweight implementation of data model §3.2);
- ``get_field_details``: field metadata + source locator + source preview + annotations (reuses preview.py);
- ``trace_lineage``: N-hop lineage subgraph (reuses the GraphPayload from lineage.py);
- ``get_field_history``: field change_log history (reuses changes.py snapshot parsing);
- ``mark_highlight``: declare fields to highlight on the canvas (canvas signal, only verifies existence);
- ``suggest_lineage``: run lineage suggestions for a field (heuristics + semantic layer); candidates persisted for manual confirmation;
- ``analyze_impact``: aggregate the downstream impact surface of a field (downstream fields/source files/recent changes);
- ``draft_descriptions``: generate AI description drafts for fields missing descriptions (stored in the draft table pending confirmation).
"""

from __future__ import annotations

import json
import sqlite3

from ..changes import load_snapshot
from ..lineage import DIRECTIONS, MAX_HOPS, LineageNotFound, lineage_subgraph
from ..preview import PreviewError, field_preview
from .descriptions import MAX_DRAFT_FIELDS
from .llm import LLMError, LLMNotConfigured

MAX_SEARCH_RESULTS = 20
MAX_HISTORY_ROWS = 50
MAX_HIGHLIGHT_FIELDS = 8
MAX_IMPACT_HOPS = 5
MAX_IMPACT_CHANGES = 10

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_fields",
            "description": (
                "Fuzzy-search fields by keyword: matches dataset ID/name, field name, field description"
                " and field annotations; returns at most 20 results. Use it to locate fields in the user's question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string",
                          "description": "Search keyword, e.g. order_no or amount"},
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_details",
            "description": (
                "Get field details: type, description, source-file locator, source preview and annotation history."
                " Use when answering \"which file/column does this field come from\"."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Dataset ID"},
                    "field": {"type": "string", "description": "Field name"},
                },
                "required": ["dataset", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_lineage",
            "description": (
                "Trace upstream/downstream lineage by dataset or field and return the N-hop subgraph"
                " (GraphPayload: datasets/edges). Use when answering \"where does it come from / where does it flow\"."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Seed dataset ID"},
                    "field": {"type": "string",
                              "description": "Seed field name; omit to trace by dataset"},
                    "direction": {
                        "type": "string",
                        "enum": list(DIRECTIONS),
                        "description": "both=bidirectional, up=upstream only, down=downstream only; default both",
                    },
                    "hops": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_HOPS,
                        "description": f"Maximum hops 1~{MAX_HOPS}, default 3",
                    },
                },
                "required": ["dataset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_history",
            "description": (
                "Query a field's change history (change_log descending): who added/modified the"
                " field description, type or source locator and when."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Dataset ID"},
                    "field": {"type": "string", "description": "Field name"},
                },
                "required": ["dataset", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_highlight",
            "description": (
                "Declare fields to highlight as a red trace chain on the canvas (a canvas signal; returns no data)."
                " Call it before the final answer when the user asks to highlight/mark results, or when the"
                " answer revolves around the upstream/downstream of some fields; the fields must exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "description": f"Fields to highlight (at most {MAX_HIGHLIGHT_FIELDS})",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dataset": {"type": "string",
                                            "description": "Dataset ID"},
                                "field": {"type": "string", "description": "Field name"},
                            },
                            "required": ["dataset", "field"],
                        },
                    },
                },
                "required": ["fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_lineage",
            "description": (
                "Run lineage suggestions for a dataset/field (heuristics + semantic similarity); candidate"
                " edges are persisted with source='ai' and appear on the canvas immediately (blue dashed),"
                " and become official lineage only after the user confirms manually in the canvas/detail"
                " panel. Call it when the user asks you to \"supplement/suggest/infer\" missing lineage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Upstream dataset ID"},
                    "field": {"type": "string",
                              "description": "Upstream field name; omit to draft for the whole dataset"},
                },
                "required": ["dataset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_impact",
            "description": (
                "Analyze the downstream impact surface of a field: recursive downstream field list, each"
                " source file and verification status, and recent changes. Use for questions like"
                " \"what is affected if I change this field\"."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Dataset ID"},
                    "field": {"type": "string", "description": "Field name"},
                    "hops": {"type": "integer", "minimum": 1,
                             "maximum": MAX_IMPACT_HOPS,
                             "description": f"Downstream hops 1~{MAX_IMPACT_HOPS}, default 3"},
                },
                "required": ["dataset", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_descriptions",
            "description": (
                "Generate AI description drafts for dataset fields (stored in the draft area; they become"
                " annotations only after user confirmation). When fields is omitted, fields with empty"
                " descriptions are selected automatically. Call it when the user asks to"
                " \"complete/generate field descriptions\"."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Dataset ID"},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of field names (at most 10); omit to automatically select fields missing descriptions",
                    },
                },
                "required": ["dataset"],
            },
        },
    },
]


class ToolError(ValueError):
    """Tool arguments or target are invalid; returned to the LLM so it can self-correct without aborting the conversation."""


def _text(args: dict, key: str, *, required: bool = True) -> str | None:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError(f'Missing argument "{key}"')
        return None
    if not isinstance(value, str):
        raise ToolError(f'Argument "{key}" must be a string')
    text = value.strip()
    if required and not text:
        raise ToolError(f'Argument "{key}" cannot be empty')
    return text or None


def _hops(args: dict) -> int:
    value = args.get("hops", 3)
    if isinstance(value, bool) or not isinstance(value, int):
        # Some models write integers as strings; do one tolerant conversion here
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ToolError(f"hops must be an integer in 1..{MAX_HOPS}") from None
    if not 1 <= value <= MAX_HOPS:
        raise ToolError(f'hops must be an integer in 1..{MAX_HOPS}; got "{value}"')
    return value


def _direction(args: dict) -> str:
    value = args.get("direction", "both")
    if value is None:
        return "both"
    if not isinstance(value, str) or value not in DIRECTIONS:
        raise ToolError(
            f'direction must be one of {" / ".join(DIRECTIONS)}; got "{value}"')
    return value


def search_fields(conn: sqlite3.Connection, args: dict) -> dict:
    query = _text(args, "q")
    pattern = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT f.dataset_id, COALESCE(d.name, '') AS dataset_name,"
        " f.name, f.field_type, f.description"
        " FROM field f JOIN dataset d ON d.id = f.dataset_id"
        " WHERE lower(f.dataset_id) LIKE :pattern"
        "    OR lower(COALESCE(d.name, '')) LIKE :pattern"
        "    OR lower(f.name) LIKE :pattern"
        "    OR lower(COALESCE(f.description, '')) LIKE :pattern"
        "    OR EXISTS ("
        "         SELECT 1 FROM annotation a"
        "         WHERE a.target_kind = 'field'"
        "           AND a.target_id = f.dataset_id || '.' || f.name"
        "           AND lower(a.body) LIKE :pattern)"
        " ORDER BY CASE"
        "            WHEN lower(f.name) = :exact THEN 0"
        "            WHEN lower(f.name) LIKE :prefix THEN 1"
        "            ELSE 2 END,"
        "          f.dataset_id, f.name"
        " LIMIT :limit",
        {"pattern": pattern, "exact": query.lower(),
         "prefix": f"{query.lower()}%", "limit": MAX_SEARCH_RESULTS},
    ).fetchall()
    return {"query": query, "results": [dict(row) for row in rows]}


def get_field_details(conn: sqlite3.Connection, args: dict) -> dict:
    dataset = _text(args, "dataset")
    field = _text(args, "field")

    dataset_row = conn.execute(
        "SELECT id, name, description FROM dataset WHERE id=?",
        (dataset,)).fetchone()
    if dataset_row is None:
        raise ToolError(f'Dataset "{dataset}" does not exist')

    row = conn.execute(
        "SELECT f.name, f.field_type, f.description, f.src_locator,"
        " s.id AS source_file_id, s.original_name, s.src_type, s.sha256"
        " FROM field f JOIN source_file s ON s.id = f.source_file_id"
        " WHERE f.dataset_id=? AND f.name=?",
        (dataset, field)).fetchone()
    if row is None:
        raise ToolError(f'Field "{dataset}.{field}" does not exist')

    try:
        locator = json.loads(row["src_locator"])
    except (TypeError, json.JSONDecodeError):
        locator = {"type": None, "input": None, "resolved": None}

    annotations = conn.execute(
        "SELECT body, author, created_at FROM annotation"
        " WHERE target_kind='field' AND target_id=? ORDER BY id",
        (f"{dataset}.{field}",)).fetchall()

    result = {
        "dataset": dataset,
        "dataset_name": dataset_row["name"],
        "dataset_description": dataset_row["description"],
        "field": row["name"],
        "field_type": row["field_type"],
        "description": row["description"],
        "src_locator": locator,
        "source_file": {
            "id": row["source_file_id"],
            "original_name": row["original_name"],
            "src_type": row["src_type"],
            "sha256": row["sha256"],
        },
        "annotations": [dict(item) for item in annotations],
    }
    # A failed source preview (stale locator/missing source file) does not block field details; turn it into a readable error
    try:
        result["preview"] = field_preview(conn, dataset, field)
    except (LookupError, PreviewError) as exc:
        result["preview"] = {"error": str(exc)}
    return result


def trace_lineage(conn: sqlite3.Connection, args: dict) -> dict:
    dataset = _text(args, "dataset")
    field = _text(args, "field", required=False)
    direction = _direction(args)
    hops = _hops(args)
    try:
        graph = lineage_subgraph(conn, dataset, field, hops, direction)
    except LineageNotFound as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {
        "dataset": dataset,
        "field": field,
        "direction": direction,
        "hops": hops,
        "graph": graph,
    }


def get_field_history(conn: sqlite3.Connection, args: dict) -> dict:
    dataset = _text(args, "dataset")
    field = _text(args, "field")
    if conn.execute("SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                    (dataset, field)).fetchone() is None:
        raise ToolError(f'Field "{dataset}.{field}" does not exist')

    rows = conn.execute(
        "SELECT id, op, actor, created_at, before, after FROM change_log"
        " WHERE entity_kind='field' AND entity_key=?"
        " ORDER BY id DESC LIMIT ?",
        (f"{dataset}.{field}", MAX_HISTORY_ROWS)).fetchall()
    history = [{
        "id": row["id"],
        "op": row["op"],
        "actor": row["actor"],
        "created_at": row["created_at"],
        "before": load_snapshot(row["before"]),
        "after": load_snapshot(row["after"]),
    } for row in rows]
    return {"dataset": dataset, "field": field, "history": history}


def mark_highlight(conn: sqlite3.Connection, args: dict) -> dict:
    """Canvas signal: declare fields to highlight in the frontend.

    Only verifies field existence (SELECT) and returns no business data; non-existent items go
    into ``ignored`` and are returned to the model, while an all-invalid list raises
    :class:`ToolError` so the model can correct itself.
    """
    raw = args.get("fields")
    if not isinstance(raw, list) or not raw:
        raise ToolError("fields must be a non-empty array")

    fields: list[dict] = []
    ignored: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if len(fields) >= MAX_HIGHLIGHT_FIELDS:
            break
        if not isinstance(item, dict):
            ignored.append(str(item))
            continue
        dataset = item.get("dataset")
        field = item.get("field")
        if (not isinstance(dataset, str) or not dataset.strip()
                or not isinstance(field, str) or not field.strip()):
            ignored.append(f"{dataset}.{field}")
            continue
        dataset, field = dataset.strip(), field.strip()
        if (dataset, field) in seen:
            continue
        if conn.execute("SELECT 1 FROM field WHERE dataset_id=? AND name=?",
                        (dataset, field)).fetchone() is None:
            ignored.append(f"{dataset}.{field}")
            continue
        seen.add((dataset, field))
        fields.append({"dataset": dataset, "field": field})

    if not fields:
        raise ToolError("No fields to highlight: none of the dataset/field pairs in fields exist")
    return {"fields": fields, "ignored": ignored}


TOOL_FUNCS = {
    "search_fields": search_fields,
    "get_field_details": get_field_details,
    "trace_lineage": trace_lineage,
    "get_field_history": get_field_history,
    "mark_highlight": mark_highlight,
}


def suggest_lineage(conn: sqlite3.Connection, args: dict, actor: str) -> dict:
    """In-conversation lineage suggestions: candidates persist as source='ai' and require manual confirmation (invariant #4)."""
    dataset = _text(args, "dataset")
    field = _text(args, "field", required=False)
    from . import suggest

    try:
        candidates = suggest.suggest_edges(conn, dataset, field, actor=actor)
    except LookupError as exc:
        raise ToolError(str(exc)) from None
    return {"dataset": dataset, "field": field,
            "candidates": candidates, "count": len(candidates)}


def analyze_impact(conn: sqlite3.Connection, args: dict) -> dict:
    """Downstream impact aggregation: field-level downstream chain + source files + recent changes."""
    dataset = _text(args, "dataset")
    field = _text(args, "field")
    value = args.get("hops", 3)
    try:
        hops = int(value) if not isinstance(value, bool) else 0
    except (TypeError, ValueError):
        raise ToolError(f"hops must be an integer in 1..{MAX_IMPACT_HOPS}") from None
    if not 1 <= hops <= MAX_IMPACT_HOPS:
        raise ToolError(f"hops must be an integer in 1..{MAX_IMPACT_HOPS}")

    try:
        graph = lineage_subgraph(conn, dataset, field, hops, "down")
    except (LineageNotFound, ValueError) as exc:
        raise ToolError(str(exc)) from None

    # BFS downstream from the start point along field-level edges, collecting affected fields (excluding the start)
    adjacency: dict[tuple, list[tuple]] = {}
    for edge in graph["edges"]:
        if edge["from_field"] is None or edge["to_field"] is None:
            continue
        adjacency.setdefault((edge["from_dataset"], edge["from_field"]), [])\
            .append((edge["to_dataset"], edge["to_field"]))
    impacted: list[dict] = []
    visited = {(dataset, field)}
    queue = [(dataset, field)]
    while queue:
        current = queue.pop(0)
        for target in adjacency.get(current, []):
            if target in visited:
                continue
            visited.add(target)
            queue.append(target)
            row = conn.execute(
                "SELECT f.field_type, COALESCE(f.description, '') AS description,"
                " s.original_name AS source_file, s.src_type"
                " FROM field f JOIN source_file s ON s.id=f.source_file_id"
                " WHERE f.dataset_id=? AND f.name=?", target).fetchone()
            impacted.append({
                "dataset": target[0],
                "field": target[1],
                "field_type": row["field_type"] if row else None,
                "source_file": row["source_file"] if row else None,
                "src_type": row["src_type"] if row else None,
            })
    impacted.sort(key=lambda item: (item["dataset"], item["field"]))

    # Recent changes (change_log) of affected fields, newest one per field
    changes: list[dict] = []
    if impacted:
        keys = [f"{item['dataset']}.{item['field']}" for item in impacted]
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT entity_key, op, actor, created_at FROM change_log"
            f" WHERE entity_kind='field' AND entity_key IN ({placeholders})"
            f" ORDER BY id DESC LIMIT {MAX_IMPACT_CHANGES * 4}",
            keys).fetchall()
        latest: dict[str, dict] = {}
        for row in rows:
            latest.setdefault(row["entity_key"], {
                "entity_key": row["entity_key"], "op": row["op"],
                "actor": row["actor"], "created_at": row["created_at"]})
        changes = sorted(latest.values(),
                         key=lambda item: item["created_at"],
                         reverse=True)[:MAX_IMPACT_CHANGES]

    return {
        "focus": {"dataset": dataset, "field": field},
        "hops": hops,
        "impacted_fields": impacted,
        "impacted_count": len(impacted),
        "recent_changes": changes,
        "datasets": [d["id"] for d in graph["datasets"]],
    }


def draft_descriptions_tool(conn: sqlite3.Connection, args: dict,
                            actor: str) -> dict:
    """In-conversation description drafts: generate → description_draft(pending) → frontend confirmation card."""
    dataset = _text(args, "dataset")
    raw_fields = args.get("fields")
    if raw_fields is None:
        fields: list[str] = []
    elif isinstance(raw_fields, list) and all(isinstance(f, str) for f in raw_fields):
        fields = [f.strip() for f in raw_fields if f.strip()][:MAX_DRAFT_FIELDS]
    else:
        raise ToolError("fields must be an array of field-name strings")
    try:
        from . import descriptions

        items = descriptions.draft_descriptions(conn, dataset, fields, actor)
    except LookupError as exc:
        raise ToolError(str(exc)) from None
    except LLMNotConfigured as exc:
        raise ToolError(str(exc)) from None
    except LLMError as exc:
        raise ToolError(str(exc)) from None
    return {"dataset": dataset, "items": items, "count": len(items)}


def run_tool(conn: sqlite3.Connection, name: str, args: dict | None,
             actor: str = "system") -> dict:
    """Execute a tool by name; an unknown tool or invalid arguments raises :class:`ToolError`.

    ``actor`` is used only by the two tools that write candidates/drafts (change_log / created_by
    need a real user; internal system calls default to "system").
    """
    if name == "suggest_lineage":
        if args is None:
            args = {}
        return suggest_lineage(conn, args, actor)
    if name == "draft_descriptions":
        if args is None:
            args = {}
        return draft_descriptions_tool(conn, args, actor)

    func = TOOL_FUNCS.get(name)
    if func is None:
        raise ToolError(f'Unknown tool "{name}"; available tools: '
                        f'{", ".join([*TOOL_FUNCS, "suggest_lineage", "draft_descriptions"])}')
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be a JSON object")
    return func(conn, args)
