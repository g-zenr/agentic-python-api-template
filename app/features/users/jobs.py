"""User job handlers: durable account erasure and account data export (both idempotent)."""

from typing import Any

from app.core import audit
from app.core.activity.repository import activity_repo
from app.core.audit.repository import audit_repo
from app.core.constants import AuditAction, AuditResource, JobType
from app.core.jobs import JobContext, job_handler
from app.core.uow import transaction
from app.features.notes.schemas import NoteOut
from app.features.users.repository import users_repo
from app.features.users.schemas import AccountErasePayload, UserOut
from app.shared.helpers.pagination import PageParams


@job_handler(JobType.ACCOUNT_ERASE, payload=AccountErasePayload)
async def account_erase(ctx: JobContext, payload: AccountErasePayload) -> dict[str, Any]:
    """Delete the user (cascades) and scrub PII from logs. Idempotent: a missing user is a no-op."""
    user_id = payload.user_id
    async with transaction():
        user = await users_repo.get(user_id)
        if user is not None:
            if user.deleted_at is None or user.is_active:
                return {"deleted": False}
            await users_repo.delete(user_id)
        await audit_repo.scrub_pii_for_actor(user_id)
        await activity_repo.scrub_ip_for_user(user_id)
        await audit.record(AuditAction.ACCOUNT_ERASE, AuditResource.USER, user_id)
    return {"deleted": user is not None}  # scrub still ran; re-runs stay no-ops


@job_handler(JobType.ACCOUNT_EXPORT)
async def account_export(ctx: JobContext) -> dict[str, Any]:
    """Return the user's profile, notes, and own audit entries."""
    user_id = ctx.user_id
    if user_id is None:
        return {"profile": None, "notes": [], "audit": []}
    user = await users_repo.get(user_id)
    if user is None:
        return {"profile": None, "notes": [], "audit": []}
    from app.features.notes.repository import notes_repo

    notes: list[Any] = []
    audit_rows: list[Any] = []
    for repo, where, output in (
        (notes_repo, {"user_id": user_id}, notes),
        (audit_repo, {"actor_id": user_id}, audit_rows),
    ):
        page = 1
        while True:
            await ctx.raise_if_cancelled()
            rows, total = await repo.paginate(PageParams(page=page, size=100), where=where)
            output.extend(rows)
            if not rows or page * 100 >= total:
                break
            page += 1
    return {
        "profile": UserOut.model_validate(user).model_dump(mode="json"),
        "notes": [NoteOut.model_validate(n).model_dump(mode="json") for n in notes],
        "audit": [a.model_dump(mode="json") for a in audit_rows],
    }
