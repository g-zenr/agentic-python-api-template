"""Job engine types: record snapshot, context passed to handlers, control-flow exceptions."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from app.core.exceptions import AppError

if TYPE_CHECKING:
    from app.core.jobs.store import JobStore


@dataclass(slots=True)
class JobRecord:
    id: str
    type: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    progress: int
    attempts: int
    max_attempts: int
    user_id: str | None
    request_id: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | Any) -> "JobRecord":
        """Build from a raw-SQL dict or a Prisma model; decode JSON string columns."""
        get = row.get if isinstance(row, Mapping) else lambda k: getattr(row, k)

        def decode(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (ValueError, TypeError):
                    return None
            return value

        return cls(
            id=cast(str, get("id")),
            type=cast(str, get("type")),
            status=str(get("status")),
            payload=decode(get("payload")) or {},
            result=decode(get("result")),
            error=get("error"),
            progress=cast(int, get("progress")),
            attempts=cast(int, get("attempts")),
            max_attempts=cast(int, get("max_attempts")),
            user_id=get("user_id"),
            request_id=get("request_id"),
            cancel_requested=cast(bool, get("cancel_requested")),
            created_at=cast(datetime, get("created_at")),
            updated_at=cast(datetime, get("updated_at")),
            started_at=get("started_at"),
            finished_at=get("finished_at"),
        )


class PermanentError(AppError):
    """Raise from a handler for failures that must NOT be retried (carries a Msg key)."""


class JobCancelled(Exception):
    """Raised inside a handler when a cancellation was requested."""


class JobContext:
    def __init__(self, job: JobRecord, store: "JobStore"):
        self.job = job
        self.store = store

    @property
    def user_id(self) -> str | None:
        """The user who submitted the job (None for system jobs)."""
        return self.job.user_id

    async def progress(self, percent: int) -> None:
        """Report progress, clamped to 0..100."""
        await self.store.set_progress(self.job.id, max(0, min(100, percent)))

    async def raise_if_cancelled(self) -> None:
        """Raise JobCancelled when a cancel was requested for this job."""
        if await self.store.is_cancel_requested(self.job.id):
            raise JobCancelled
