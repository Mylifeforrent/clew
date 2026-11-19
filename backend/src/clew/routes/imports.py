"""Import and versions: three-step import API, batch/report queries, rollback by batch."""

import json

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from .. import versioning
from ..db import get_db
from ..import_service import run_import
from ..manifest import read_csv_manifest, read_json_manifest, read_xlsx_manifest
from ..security import require_role

router = APIRouter(tags=["import"])


@router.post("/import", status_code=201)
async def import_data(
    format: str = Form(...),  # noqa: A002 — same name as the manifest format; external API semantics
    source_file_ids: str = Form(...),
    user: dict = Depends(require_role("editor")),
    manifest: UploadFile | None = None,          # xlsx / json single-file manifest
    manifest_datasets: UploadFile | None = None,  # csv: datasets.csv
    manifest_lineage: UploadFile | None = None,   # csv: lineage.csv
):
    fmt = format.lower()
    try:
        ids = [int(x) for x in source_file_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "source_file_ids must be comma-separated file IDs") from None
    if not ids:
        raise HTTPException(400, "Bind at least one source file")

    with get_db() as conn:
        bound = []
        for fid in ids:
            row = conn.execute(
                "SELECT id, original_name, src_type FROM source_file WHERE id=?",
                (fid,)).fetchone()
            if row is None:
                raise HTTPException(404, f"Source file {fid} does not exist")
            bound.append(dict(row))

    try:
        if fmt == "csv":
            if manifest_datasets is None or manifest_lineage is None:
                raise HTTPException(
                    400, "csv format requires both manifest_datasets and manifest_lineage files")
            ds_recs, edge_recs = read_csv_manifest(
                await manifest_datasets.read(), await manifest_lineage.read())
        elif fmt == "xlsx":
            if manifest is None:
                raise HTTPException(
                    400, "xlsx format requires a manifest file with datasets/lineage sheets")
            ds_recs, edge_recs = read_xlsx_manifest(await manifest.read())
        elif fmt == "json":
            if manifest is None:
                raise HTTPException(
                    400, "json format requires a {datasets:[], lineage:[]} manifest file")
            ds_recs, edge_recs = read_json_manifest(await manifest.read())
        else:
            raise HTTPException(400, f"format must be csv/xlsx/json, got \"{fmt}\"")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

    if not ds_recs and not edge_recs:
        raise HTTPException(400, "The manifest is empty")

    batch_id, version_no, report = run_import(user["username"], fmt, bound,
                                              ds_recs, edge_recs)
    return {"batch_id": batch_id, "version_no": version_no, "report": report}


@router.get("/import/batches")
def list_batches(user: dict = Depends(require_role("viewer"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, version_no, file_names, format, created_by, created_at,"
            " rolled_back_at FROM import_batch ORDER BY version_no DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["file_names"] = json.loads(d["file_names"]) if d["file_names"] else []
        out.append(d)
    return out


@router.get("/import/batches/{batch_id}")
def get_batch(batch_id: int, user: dict = Depends(require_role("viewer"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM import_batch WHERE id=?", (batch_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Import batch {batch_id} does not exist")
    d = dict(row)
    d["file_names"] = json.loads(d["file_names"]) if d["file_names"] else []
    d["report"] = json.loads(d["report"]) if d["report"] else None
    return d


@router.post("/import/batches/{batch_id}/rollback")
def rollback(batch_id: int, admin: dict = Depends(require_role("admin"))):
    try:
        reverted = versioning.rollback_batch(batch_id, admin["username"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return {"batch_id": batch_id, "reverted": reverted}


@router.get("/lineage/snapshot")
def snapshot(user: dict = Depends(require_role("viewer"))):
    """Current lineage state (used by M1 verification; M2 replaces it with the recursive CTE subgraph query)."""
    return versioning.get_snapshot()
