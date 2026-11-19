"""Field source preview API: after clicking a locator card, highlight the corresponding region of the source file (design §3.6)."""

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..preview import PreviewError, field_preview
from ..security import require_role

router = APIRouter(tags=["preview"])


@router.get("/fields/{dataset_id}/{field_name}/preview")
def preview_field(dataset_id: str, field_name: str,
                  user: dict = Depends(require_role("viewer"))):
    """Return a structured csv/xlsx/json preview for the field's locator; a stale locator returns 409."""
    with get_db() as conn:
        try:
            return field_preview(conn, dataset_id, field_name)
        except LookupError as e:
            raise HTTPException(404, str(e)) from None
        except PreviewError as e:
            raise HTTPException(409, str(e)) from None
