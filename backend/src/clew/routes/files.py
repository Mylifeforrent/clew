"""Source file hosting: upload (sha256 dedup), list, download (design §3.6)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import files_dir, get_settings, resolve_storage
from ..db import get_db
from ..security import require_role

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_TYPES = {"csv", "xlsx", "json"}


def _src_type_of(filename: str) -> str:
    suffix = Path(filename).suffix.lstrip(".").lower()
    if suffix not in ALLOWED_TYPES:
        raise HTTPException(
            400, f"Only {', '.join(sorted(ALLOWED_TYPES))} files are supported,"
                 f" got \"{filename}\"")
    return suffix


def store_upload(filename: str, data: bytes, username: str) -> dict:
    """Host and register one source file: reuse an existing record with the same sha256 (dedup).

    The upload route and ``seed_demo`` share this service path; the caller is
    responsible for empty-file / size-limit validation.
    """
    src_type = _src_type_of(filename)
    sha = hashlib.sha256(data).hexdigest()
    # Keep the original file extension: parsers such as openpyxl detect the format by extension
    rel_path = f"files/{sha[:2]}/{sha}.{src_type}"
    abs_path = files_dir() / sha[:2] / f"{sha}.{src_type}"
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM source_file WHERE sha256=?",
                                (sha,)).fetchone()
        if existing is not None:
            return {**dict(existing), "deduped": True}
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)
        cur = conn.execute(
            "INSERT INTO source_file(original_name, storage_path, sha256,"
            " size_bytes, src_type, uploaded_by, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (filename, rel_path, sha, len(data), src_type,
             username, datetime.now(UTC).isoformat(timespec="seconds")))
        row = conn.execute("SELECT * FROM source_file WHERE id=?",
                           (cur.lastrowid,)).fetchone()
        return {**dict(row), "deduped": False}


@router.post("", status_code=201)
async def upload(files: list[UploadFile] | None = None,
                 user: dict = Depends(require_role("editor"))):
    """Batch-upload first-party source files; identical content (same sha256) reuses the existing record."""
    if not files:
        raise HTTPException(400, "Upload at least one file")
    max_upload_mb = get_settings().max_upload_mb
    max_bytes = max_upload_mb * 1024 * 1024
    out = []
    for f in files:
        _src_type_of(f.filename or "")
        data = await f.read()
        if not data:
            raise HTTPException(400, f"File \"{f.filename}\" is empty")
        if len(data) > max_bytes:
            raise HTTPException(
                413, f"File \"{f.filename}\" exceeds the {max_upload_mb}MB per-file size limit")
        out.append(store_upload(f.filename or "", data, user["username"]))
    return out


@router.get("")
def list_files(user: dict = Depends(require_role("viewer"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, original_name, sha256, size_bytes, src_type, uploaded_by,"
            " created_at FROM source_file ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@router.get("/{file_id}/download")
def download(file_id: int, user: dict = Depends(require_role("viewer"))):
    """Controlled download: the storage path is never exposed (business rule #8)."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM source_file WHERE id=?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Source file {file_id} does not exist")
    abs_path = resolve_storage(row["storage_path"])
    return FileResponse(abs_path, filename=row["original_name"])
