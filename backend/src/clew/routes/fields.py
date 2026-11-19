"""Field editing API (M3): manual corrections to description, type and source locator (editor+).

``src_locator`` is the **only** field that requires real-file verification:
- accepts locator input (e.g. ``{"column": 3}``) or a full envelope ``{"type","input","resolved"}``;
- structural validation (pydantic) → open the managed source file for real-file
  verification → re-materialize ``resolved``;
- any step fails returns 409 with the reason, and the field keeps its previous
  value (transaction rollback);
- a successful edit writes change_log (batch_id=NULL, actor=current user) and
  can be reversed by a tag rollback.
"""

import json

from fastapi import APIRouter, Depends, HTTPException

from ..changes import field_snapshot, log_change, now
from ..config import resolve_storage
from ..db import get_db
from ..locator import CHECKERS, LOCATOR_MODELS
from ..models import FieldPatch
from ..security import require_role

router = APIRouter(tags=["fields"])


def _field_out(row) -> dict:
    out = dict(row)
    out["src_locator"] = json.loads(out["src_locator"])
    return out


def _locator_input(payload: dict, src_type: str) -> dict:
    """Support both request forms: locator input, or a full locator envelope."""
    envelope_keys = {"type", "input", "resolved"}
    if envelope_keys & payload.keys():
        declared = payload.get("type") or src_type
        if declared != src_type:
            raise ValueError(
                f"Locator type \"{declared}\" does not match the source file type \"{src_type}\"")
        user_input = payload.get("input")
        if not isinstance(user_input, dict):
            raise ValueError("src_locator.input must be a JSON object")
        return user_input
    return payload


@router.patch("/fields/{dataset_id}/{field_name}")
def patch_field(dataset_id: str, field_name: str, body: FieldPatch,
                user: dict = Depends(require_role("editor"))):
    """Manually correct a field's description/type/source locator; src_locator is re-verified against the real file and materialized."""
    provided = body.model_fields_set
    if not provided:
        raise HTTPException(
            400, "Provide at least one editable field"
                 " (description / field_type / src_locator)")
    if "src_locator" in provided and body.src_locator is None:
        raise HTTPException(
            400, "src_locator cannot be empty (a field must always be traceable to its source)")

    with get_db() as conn:
        row = conn.execute(
            "SELECT f.dataset_id, f.name, f.field_type, f.source_file_id,"
            " f.src_locator, f.description, f.updated_at, s.storage_path,"
            " s.original_name, s.src_type"
            " FROM field f JOIN source_file s ON s.id = f.source_file_id"
            " WHERE f.dataset_id=? AND f.name=?",
            (dataset_id, field_name)).fetchone()
        if row is None:
            raise HTTPException(404, f"Field \"{dataset_id}.{field_name}\" does not exist")

        new_description = (body.description if "description" in provided
                           else row["description"])
        new_field_type = (body.field_type if "field_type" in provided
                          else row["field_type"])
        new_locator = row["src_locator"]

        if "src_locator" in provided:
            src_type = row["src_type"]
            try:
                locator_input = _locator_input(body.src_locator or {}, src_type)
                model_cls = LOCATOR_MODELS.get(src_type)
                if model_cls is None:
                    raise ValueError(f"Unsupported source file type \"{src_type}\"")
                try:
                    locator_model = model_cls(**locator_input)
                except Exception as e:  # pydantic ValidationError
                    raise ValueError(f"locator structural validation failed: {e}") from None
                path = resolve_storage(row["storage_path"])
                if not path.is_file():
                    raise ValueError(
                        f"Source file \"{row['original_name']}\" is not in managed"
                        " storage; cannot run real-file verification")
                try:
                    resolved = CHECKERS[src_type](str(path), locator_model)
                except ValueError as e:
                    raise ValueError(f"real-file verification failed: {e}") from None
            except ValueError as e:
                # Structural errors/verification failures uniformly return 409;
                # get_db has not written anything yet, so the field keeps its old value
                raise HTTPException(409, str(e)) from None
            new_locator = json.dumps(
                {"type": src_type,
                 "input": locator_model.model_dump(exclude_none=True),
                 "resolved": resolved},
                ensure_ascii=False)

        before = field_snapshot(row)
        after = {"dataset_id": row["dataset_id"], "name": row["name"],
                 "field_type": new_field_type,
                 "source_file_id": row["source_file_id"],
                 "src_locator": new_locator,
                 "description": new_description}
        if before == after:
            return _field_out(row)

        updated_at = now()
        conn.execute(
            "UPDATE field SET field_type=?, src_locator=?, description=?,"
            " updated_at=? WHERE dataset_id=? AND name=?",
            (new_field_type, new_locator, new_description, updated_at,
             dataset_id, field_name))
        log_change(
            conn, entity_kind="field", entity_key=f"{dataset_id}.{field_name}",
            op="updated", before=before, after=after, actor=user["username"])
        saved = conn.execute(
            "SELECT dataset_id, name, field_type, source_file_id, src_locator,"
            " description, updated_at FROM field WHERE dataset_id=? AND name=?",
            (dataset_id, field_name)).fetchone()
    return _field_out(saved)
