"""Note schemas: create, update, and output models. All fields documented."""

from datetime import datetime

from pydantic import Field

from app.core.constants import Limits
from app.shared.schemas import ApiModel


class NoteCreate(ApiModel):
    title: str = Field(max_length=Limits.TITLE_MAX, description="Short human-readable title.")
    body: str = Field(default="", max_length=Limits.BODY_MAX, description="Note body text.")


class NoteUpdate(ApiModel):
    title: str | None = Field(default=None, max_length=Limits.TITLE_MAX)
    body: str | None = Field(default=None, max_length=Limits.BODY_MAX)


class NoteOut(ApiModel):
    id: str
    title: str
    body: str
    version: int
    created_at: datetime
    updated_at: datetime
