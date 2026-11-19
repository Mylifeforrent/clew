"""Lineage graph query API (design §4.3 / §5.1)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..lineage import LineageNotFound, lineage_subgraph
from ..security import require_role

router = APIRouter(tags=["lineage"])


@router.get("/lineage/subgraph")
def subgraph(
    dataset: str = Query(..., description="Seed dataset ID"),
    field: str | None = Query(None, description="Seed field name (optional)"),
    hops: int = Query(3, ge=1, le=5, description="Maximum hops, 1-5"),
    direction: Literal["both", "up", "down"] = Query("both"),
    user: dict = Depends(require_role("viewer")),
):
    """Fetch the N-hop lineage subgraph of a dataset/field (GraphPayload)."""
    with get_db() as conn:
        try:
            return lineage_subgraph(conn, dataset, field, hops, direction)
        except LineageNotFound as e:
            raise HTTPException(404, str(e)) from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
