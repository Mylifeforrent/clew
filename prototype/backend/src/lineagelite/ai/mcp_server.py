"""LineageLite MCP server (M5, evolution plan 07 §4.6).

Exposes lineage query capabilities to external AI clients (Claude Desktop / Cursor, etc.)
over the Model Context Protocol (stdio transport), reusing the same read-only query
functions as the REST API and the same SQLite database.

**Read-only boundary**: only query tools are exposed; capabilities that write candidates or
drafts, such as suggest/mark_highlight/description drafts, are never exposed—external agents
cannot trigger any database write (an extension of business invariant #4).

Run with::

    cd prototype/backend && uv run python -m lineagelite.ai.mcp_server

Client setup examples are in the AI module evolution plan (docs/03_dev, §4.6).
"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from ..db import get_db
from .tools import get_field_details, get_field_history, search_fields, trace_lineage

mcp = MCPServer("lineagelite")


@mcp.tool()
def lineage_search_fields(q: str) -> str:
    """Fuzzy-search fields by keyword (matches dataset ID/name, field name, field description and annotations)."""
    with get_db() as conn:
        result = search_fields(conn, {"q": q})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def lineage_field_details(dataset: str, field: str) -> str:
    """Field details: type, description, source-file locator, source preview and annotation history."""
    with get_db() as conn:
        result = get_field_details(conn, {"dataset": dataset, "field": field})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def lineage_trace(dataset: str, field: str | None = None,
                  direction: str = "both", hops: int = 3) -> str:
    """Trace the upstream/downstream N-hop lineage subgraph by dataset/field (GraphPayload: datasets/edges)."""
    with get_db() as conn:
        result = trace_lineage(conn, {"dataset": dataset, "field": field,
                                      "direction": direction, "hops": hops})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def lineage_field_history(dataset: str, field: str) -> str:
    """Field change history (change_log descending, most recent 50 entries)."""
    with get_db() as conn:
        result = get_field_history(conn, {"dataset": dataset, "field": field})
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def lineage_overview() -> str:
    """Data asset overview: dataset list (with field counts) and lineage edge statistics."""
    with get_db() as conn:
        datasets = [dict(row) for row in conn.execute(
            "SELECT d.id, COALESCE(d.name, '') AS name,"
            " (SELECT COUNT(*) FROM field f WHERE f.dataset_id=d.id) AS field_count"
            " FROM dataset d ORDER BY d.id").fetchall()]
        edges = conn.execute(
            "SELECT source, COUNT(*) AS count FROM edge GROUP BY source").fetchall()
    return json.dumps({
        "datasets": datasets,
        "edges_by_source": {row["source"]: row["count"] for row in edges},
    }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
