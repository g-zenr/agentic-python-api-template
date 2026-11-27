"""Job schemas: the public snapshot returned by the jobs API."""

from datetime import datetime
from typing import Any

from app.core.constants import JobStatus
from app.shared.schemas import ApiModel


class JobOut(ApiModel):
    id: str
    type: str
    status: JobStatus
    progress: int
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
