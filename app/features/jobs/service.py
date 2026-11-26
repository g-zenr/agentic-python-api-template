"""Job service: ownership checks, submission, and cancellation over the core job store."""

from prisma.models import User

from app.core import audit
from app.core.constants import (
    TERMINAL_JOB_STATUSES,
    AuditAction,
    AuditResource,
    JobStatus,
    JobType,
    Permission,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.i18n import t
from app.core.jobs import JobRecord, enqueue, get_store
from app.core.messages import Msg
from app.core.permissions import has_permission
from app.core.uow import transaction
from app.features.jobs.schemas import JobOut
from app.shared.helpers.pagination import PageParams


def to_out(rec: JobRecord) -> JobOut:
    """Convert a JobRecord to the public JobOut, translating the stored error Msg key."""
    return JobOut(
        id=rec.id,
        type=rec.type,
        status=JobStatus(rec.status),
        progress=rec.progress,
        attempts=rec.attempts,
        max_attempts=rec.max_attempts,
        result=rec.result,
        error=t(rec.error) if rec.error else None,
        created_at=rec.created_at,
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        updated_at=rec.updated_at,
    )


async def _owned(user: User, job_id: str, *, write: bool = False) -> JobRecord:
    """Fetch a job the user may see (own, or any with the read/manage permission) or 404."""
    job = await get_store().get(job_id)
    perm = Permission.JOBS_MANAGE_ALL if write else Permission.JOBS_READ_ALL
    if job is None or (job.user_id != user.id and not has_permission(user.role, perm)):
        raise NotFoundError(Msg.JOB_NOT_FOUND)
    return job


async def submit(
    user: User,
    job_type: JobType,
    payload=None,
    *,
    idempotency_key: str | None = None,
) -> JobOut:
    job, _ = await enqueue(job_type, payload, user_id=user.id, idempotency_key=idempotency_key)
    return to_out(job)


async def get(user: User, job_id: str) -> JobOut:
    return to_out(await _owned(user, job_id))


async def list_jobs(
    user: User, params: PageParams, status: JobStatus | None
) -> tuple[list[JobRecord], int]:
    return await get_store().list_for_user(user.id, params, status)


async def cancel(user: User, job_id: str) -> tuple[JobOut, Msg]:
    """Cancel (or request cancellation of) a job. Terminal jobs raise ConflictError."""
    store = get_store()
    job = await _owned(user, job_id, write=True)
    before = to_out(job)
    if job.status in {s.value for s in TERMINAL_JOB_STATUSES}:
        raise ConflictError(Msg.JOB_NOT_CANCELLABLE)

    async with transaction():
        if job.status == JobStatus.QUEUED.value:
            if await store.cancel_queued(job_id):
                msg = Msg.JOB_CANCELLED
            else:
                await store.request_cancel(job_id)
                msg = Msg.JOB_CANCEL_REQUESTED
        else:  # RUNNING
            await store.request_cancel(job_id)
            msg = Msg.JOB_CANCEL_REQUESTED

        updated = await store.get(job_id)
        await audit.record(
            AuditAction.JOB_CANCEL,
            AuditResource.JOB,
            job_id,
            before=before,
            after=to_out(updated) if updated else None,
        )
    return to_out(updated) if updated else before, msg
