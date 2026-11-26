"""Base schema and response envelope shared by every feature."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.constants import ErrorCode


class ApiModel(BaseModel):
    """Base for ALL request/response schemas: camelCase JSON, ORM-friendly."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class Meta(ApiModel):
    page: int
    size: int
    total: int
    pages: int


class CursorMeta(ApiModel):
    next_cursor: str | None
    size: int
    has_more: bool


class ApiResponse[T](ApiModel):
    """Every endpoint returns this envelope (success and error)."""

    success: bool = True
    message: str
    code: ErrorCode | None = None
    data: T | None = None
    meta: Meta | None = None
    cursor: CursorMeta | None = None
