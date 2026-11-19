"""pydantic API models and import record structures. Locator envelope: {type, input, resolved}."""

from typing import Literal

from pydantic import BaseModel, Field


# ---------- Locator input (the input part users fill in) ----------

class CsvLocatorIn(BaseModel):
    column: int | None = Field(default=None, ge=1)
    header: str | None = None


class XlsxLocatorIn(BaseModel):
    sheet: str
    column: str | None = None
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    header_path: list[str] | None = None
    header_rows: int | None = Field(default=None, ge=1)


class JsonLocatorIn(BaseModel):
    json_path: str


# ---------- API request/response ----------

class LoginIn(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6)
    display_name: str | None = None
    role: str = Field(pattern="^(admin|editor|viewer)$")


class UserOut(BaseModel):
    username: str
    display_name: str | None
    role: str


# ---------- M3 editing and annotations ----------

class AnnotationCreate(BaseModel):
    target_kind: Literal["dataset", "field", "edge"]
    target_id: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=4000)


class FieldPatch(BaseModel):
    description: str | None = None
    field_type: str | None = None
    # Locator input (or a complete {type,input,resolved} envelope; resolved is re-materialized)
    src_locator: dict | None = None


class EdgeCreate(BaseModel):
    from_dataset: str = Field(min_length=1)
    from_field: str | None = None
    to_dataset: str = Field(min_length=1)
    to_field: str | None = None
    transform: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    note: str | None = None


class EdgePatch(BaseModel):
    transform: str | None = None
    note: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class VersionTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    note: str | None = None


# ---------- M4 AI chat and lineage suggestions ----------

class AiChatMessage(BaseModel):
    # Only user/assistant are allowed: the system prompt is fixed by the backend so the
    # frontend cannot override tool constraints
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class AiFocus(BaseModel):
    dataset: str = Field(min_length=1, max_length=256)
    field: str | None = Field(default=None, max_length=256)


class AiChatIn(BaseModel):
    messages: list[AiChatMessage] = Field(min_length=1, max_length=50)
    focus: AiFocus | None = None


class AiSuggestIn(BaseModel):
    dataset: str = Field(min_length=1, max_length=256)
    field: str | None = Field(default=None, max_length=256)


class AiEdgeKeyIn(BaseModel):
    """Natural key of an AI candidate edge (shared by confirm / reject)."""

    from_dataset: str = Field(min_length=1, max_length=256)
    from_field: str | None = Field(default=None, max_length=256)
    to_dataset: str = Field(min_length=1, max_length=256)
    to_field: str | None = Field(default=None, max_length=256)


# ---------- Import records (normalized manifest row results) ----------

class DatasetFieldRecord(BaseModel):
    row: int
    dataset_id: str
    dataset_name: str | None = None
    field_name: str
    field_type: str | None = None
    src_file: str
    src_type: str
    src_locator: dict
    description: str | None = None
    parse_error: str | None = None  # Row-level parse error: when non-empty the whole row is rejected (not the whole batch with 400)


class LineageEdgeRecord(BaseModel):
    row: int
    from_dataset: str
    from_field: str | None = None
    to_dataset: str
    to_field: str | None = None
    transform: str | None = None
    confidence: float | None = None
    note: str | None = None
    parse_error: str | None = None  # Row-level parse error: when non-empty the whole row is rejected (not the whole batch with 400)


class ImportReportItem(BaseModel):
    status: str  # ok | merged | rejected
    kind: str  # field | edge
    ref: str
    reason: str | None = None
    source_row: int


class ImportReport(BaseModel):
    summary: dict
    items: list[ImportReportItem]
