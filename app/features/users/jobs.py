"""User job handlers: durable account erasure and account data export (both idempotent)."""

from app.core import audit
from app.core.audit.repository import audit_repo
from app.core.constants import AuditAction, AuditResource, JobType
from app.core.jobs import JobContext, job_handler
from app.core.uow import current_db
from app.features.users.repository import users_repo
from app.features.users.schemas import UserOut
from app.shared.helpers.pagination import PageParams


@job_handler(JobType.ACCOUNT_ERASE)
async def account_erase(ctx: JobContext) -> dict:
    """Delete the user (cascades) and scrub PII from logs. Idempotent: a missing user is a no-op."""
    user_id = ctx.user_id
    if user_id is None:
        return {"deleted": False}
    user = await users_repo.get(user_id)
    if user is not None:
        await users_repo.delete(user_id)
    client = current_db()
    await client.execute_raw(
        "UPDATE audit_logs SET ip = NULL, user_agent = NULL WHERE actor_id = $1;", user_id
    )
    await client.execute_raw("UPDATE activity_logs SET ip = NULL WHERE user_id = $1;", user_id)
    await audit.record(AuditAction.ACCOUNT_ERASE, AuditResource.USER, user_id)
    return {"deleted": True}


@job_handler(JobType.ACCOUNT_EXPORT)
async def account_export(ctx: JobContext) -> dict:
    """Return the user's profile, notes, and up to 1000 of their own audit entries."""
    user_id = ctx.user_id
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
