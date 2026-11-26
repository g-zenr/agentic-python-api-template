"""Job engine public facade: registration, enqueueing, the worker, and the store seam.

Features submit work with `enqueue(...)`; handlers live in `features/<x>/jobs.py`; the worker
runs them. `get_store`/`set_store` let tests swap the data layer.
"""

from datetime import timedelta

from pydantic import BaseModel

from app.core.constants import JobPolicy, JobType
from app.core.context import current
from app.core.jobs import registry
from app.core.jobs.registry import Handler, get_handler, handlers, job_handler
from app.core.jobs.store import JobStore, get_store, set_store
from app.core.jobs.types import JobContext, JobRecord, PermanentError
from app.core.jobs.worker import Worker, execute
from app.shared.utils.time import utcnow

__all__ = [
    "Handler",
    "JobContext",
    "JobRecord",
    "JobStore",
    "PermanentError",
    "Worker",
    "enqueue",
    "execute",
    "get_handler",
    "get_store",
    "handlers",
    "job_handler",
    "set_store",
]


async def enqueue(
    job_type: JobType,
    payload: BaseModel | None = None,
    *,
    user_id: str | None,
    idempotency_key: str | None = None,
    delay_seconds: int = 0,
    priority: int = 0,
) -> tuple[JobRecord, bool]:
    """Enqueue a job for `job_type`. Returns (job, created); created=False on dedupe hit."""
    handler = registry.get_handler(job_type)
    if (
        payload is not None
        and handler.payload_model is not None
        and not isinstance(payload, handler.payload_model)
    ):
        raise TypeError(f"payload must be {handler.payload_model.__name__}")
    dedupe = f"{user_id or JobPolicy.SYSTEM_SCOPE}:{idempotency_key}" if idempotency_key else None
    return await get_store().enqueue(
        type=job_type.value,
        payload=payload.model_dump(mode="json") if payload else {},
        user_id=user_id,
        request_id=current().request_id,
        max_attempts=handler.max_attempts,
        run_at=utcnow() + timedelta(seconds=delay_seconds),
        dedupe_key=dedupe,
        priority=priority,
    )
