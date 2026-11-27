"""User job handlers: durable account erasure and account data export (both idempotent)."""

from typing import Any

from app.core import audit
from app.core.activity.repository import activity_repo
from app.core.audit.repository import audit_repo
from app.core.constants import AuditAction, AuditResource, JobType
from app.core.jobs import JobContext, job_handler
from app.features.users.repository import users_repo
from app.features.users.schemas import UserOut
from app.shared.helpers.pagination import PageParams


@job_handler(JobType.ACCOUNT_ERASE)
async def account_erase(ctx: JobContext) -> dict[str, Any]:
    """Delete the user (cascades) and scrub PII from logs. Idempotent: a missing user is a no-op."""
    user_id = ctx.user_id
    if user_id is None:
        return {"deleted": False}
    user = await users_repo.get(user_id)
    if user is not None:
        await users_repo.delete(user_id)
    await audit_repo.scrub_pii_for_actor(user_id)  # scrub PII from logs (layering: repo owns SQL)
    await activity_repo.scrub_ip_for_user(user_id)
    await audit.record(AuditAction.ACCOUNT_ERASE, AuditResource.USER, user_id)
    return {"deleted": user is not None}  # scrub still ran; re-runs stay no-ops


@job_handler(JobType.ACCOUNT_EXPORT)
async def account_export(ctx: JobContext) -> dict[str, Any]:
    """Return the user's profile, notes, and up to 1000 of their own audit entries."""
    user_id = ctx.user_id
    if user_id is None:
        return {"profile": None, "notes": [], "audit": []}
    user = await users_repo.get(user_id)
    if user is None:
        return {"profile": None, "notes": [], "audit": []}
    from app.features.notes.repository import notes_repo

    notes, _ = await notes_repo.paginate(PageParams(page=1, size=100), where={"user_id": user_id})
    audit_rows, _ = await audit_repo.paginate(
        PageParams(page=1, size=1000), where={"actor_id": user_id}
    )
    return {
        "profile": UserOut.model_validate(user).model_dump(mode="json"),
        "notes": [n.title for n in notes],
        "audit": [a.action for a in audit_rows],
    }
