"""Scheduled maintenance handlers: log retention, finished-job cleanup, expired-token purge.

All handlers are idempotent and safe on any number of workers (the scheduler dedupes per bucket).
"""

from datetime import timedelta

from app.core import audit
from app.core.activity.repository import activity_repo
from app.core.audit.repository import audit_repo
from app.core.config import settings
from app.core.constants import AuditAction, AuditResource, JobType, Schedule
from app.core.jobs import JobContext, job_handler
from app.core.jobs.store import get_store
from app.features.auth.repository import one_time_repo, refresh_repo
from app.shared.helpers.idempotency import purge_expired
from app.shared.utils.time import utcnow


@job_handler(JobType.PURGE_LOGS, schedule_every=Schedule.HOURLY)
async def purge_logs(ctx: JobContext) -> dict:
    """Delete activity/audit logs past their retention windows, then record the purge itself."""
    activity_deleted = await activity_repo.purge_before(
        utcnow() - timedelta(days=settings.activity_retention_days)
    )
    audit_deleted = 0
    if settings.audit_retention_days > 0:
        audit_deleted = await audit_repo.purge_before(
            utcnow() - timedelta(days=settings.audit_retention_days)
        )
    await audit.record(
        AuditAction.RETENTION_PURGE,
        AuditResource.LOG,
        metadata={"activity_deleted": activity_deleted, "audit_deleted": audit_deleted},
    )
    return {"activity_deleted": activity_deleted, "audit_deleted": audit_deleted}


@job_handler(JobType.PURGE_JOBS, schedule_every=Schedule.DAILY)
async def purge_jobs(ctx: JobContext) -> dict:
    """Delete finished jobs older than the retention window."""
    cutoff = utcnow() - timedelta(days=settings.job_retention_days)
    deleted = await get_store().purge_finished_before(cutoff)
    return {"deleted": deleted}


@job_handler(JobType.PURGE_EXPIRED, schedule_every=Schedule.DAILY)
async def purge_expired_tokens(ctx: JobContext) -> dict:
    """Delete expired refresh/one-time tokens and expired idempotency records."""
    now = utcnow()
    refresh = await refresh_repo.purge(now)
    one_time = await one_time_repo.purge(now)
    idem = await purge_expired()
    return {"refresh": refresh, "one_time": one_time, "idempotency": idem}
