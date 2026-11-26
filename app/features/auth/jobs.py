"""Auth job handlers: deliver verification/reset emails (the raw token never sits in the jobs table)."""  # noqa: E501

from datetime import timedelta

from app.core.config import settings
from app.core.constants import JobType, TokenPurpose
from app.core.email import get_sender
from app.core.i18n import t
from app.core.jobs import JobContext, job_handler
from app.core.messages import Msg
from app.core.security import new_opaque_token
from app.features.auth.repository import one_time_repo
from app.features.auth.schemas import SendTokenEmailPayload
from app.features.users.repository import users_repo
from app.shared.utils.time import utcnow


@job_handler(JobType.AUTH_SEND_TOKEN_EMAIL, payload=SendTokenEmailPayload)
async def send_token_email(ctx: JobContext, payload: SendTokenEmailPayload) -> dict | None:
    """Create a one-time token and email the localized link. Idempotent: a duplicate replaces the token."""  # noqa: E501
    user = await users_repo.get(payload.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    raw, token_hash = new_opaque_token()
    ttl = (
        timedelta(hours=settings.verification_token_ttl_hours)
        if payload.purpose == TokenPurpose.VERIFY_EMAIL
        else timedelta(minutes=settings.reset_token_ttl_minutes)
    )
    await one_time_repo.invalidate_unused(user.id, payload.purpose.value)
    await one_time_repo.create(
        data={
            "user_id": user.id,
            "purpose": payload.purpose.value,
            "token_hash": token_hash,
            "expires_at": utcnow() + ttl,
        }
    )
    path = "verify-email" if payload.purpose == TokenPurpose.VERIFY_EMAIL else "reset-password"
    link = f"{settings.app_base_url}/{path}?token={raw}"
    if payload.purpose == TokenPurpose.VERIFY_EMAIL:
        subject, body = (
            t(Msg.EMAIL_VERIFY_SUBJECT, user.locale),
            t(Msg.EMAIL_VERIFY_BODY, user.locale, name=user.name, link=link),
        )
    else:
        subject, body = (
            t(Msg.EMAIL_RESET_SUBJECT, user.locale),
            t(Msg.EMAIL_RESET_BODY, user.locale, name=user.name, link=link),
        )
    await get_sender().send(user.email, subject, body)
    return {"sent": True}
