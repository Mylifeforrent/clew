"""Version business tag API (M3): create, list, diff between tags, rollback to tag.

- create (editor+): anchor at the current end of change_log; a duplicate name is 409;
- diff (viewer+): net changes in the change_seq interval between two tags;
- rollback (admin): reverse all change_log entries after the tag (including manual edits); audit goes to rollback_record.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import versioning
from ..models import VersionTagCreate
from ..security import require_role

router = APIRouter(tags=["version-tags"])


@router.post("/version-tags", status_code=201)
def create_tag(body: VersionTagCreate,
               user: dict = Depends(require_role("editor"))):
    """Create a business tag; change_seq = current max change_log id."""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Tag name cannot be empty")
    note = body.note.strip() if body.note is not None else None
    try:
        row = versioning.create_tag(name, note, user["username"])
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return {key: row[key] for key in
            ("name", "note", "change_seq", "created_by", "created_at")}


@router.get("/version-tags")
def list_tags(user: dict = Depends(require_role("viewer"))):
    return versioning.list_tags()


@router.get("/version-tags/diff")
def diff_tags(
    from_name: str = Query(..., alias="from", description="Start tag name"),
    to_name: str = Query(..., alias="to", description="End tag name"),
    user: dict = Depends(require_role("viewer")),
):
    """Net changes between two tags (added/updated/deleted)."""
    try:
        return versioning.tag_diff(from_name, to_name)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.post("/version-tags/{name}/rollback")
def rollback_to_tag(name: str,
                    admin: dict = Depends(require_role("admin"))):
    """Roll back to a tag: reverse all changes after change_seq (idempotent, safe to repeat)."""
    try:
        reverted = versioning.rollback_to_tag(name, admin["username"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return {"reverted": reverted}
