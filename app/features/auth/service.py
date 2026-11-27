"""Auth service: registration, login, token rotation, logout, and account-recovery flows.

Business rules only; raises typed errors. Mutations run in a transaction with the audit write.
Failed logins are rate-limited per account (keyed by email hash) so unknown emails behave the same.
"""

import uuid
from datetime import timedelta

from prisma.models import User

from app.core import audit
from app.core.config import settings
from app.core.constants import (
    AuditAction,
    AuditOutcome,
    AuditReason,
    AuditResource,
    JobType,
    RateBucket,
    TokenPurpose,
)
from app.core.context import current, locale_var
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.jobs import enqueue
from app.core.messages import Msg
from app.core.ratelimit import email_identity, enforce, peek, reset
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.core.uow import after_commit, transaction
from app.features.auth.repository import one_time_repo, refresh_repo
from app.features.auth.schemas import (
    ChangePasswordIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    SendTokenEmailPayload,
    TokenOut,
)
from app.features.users.repository import users_repo
from app.features.users.schemas import UserOut
from app.shared.utils.time import utcnow


def _issue_pair(user: User, family_id: str | None = None) -> tuple[TokenOut, str, str]:
    """Create a refresh token row and return an access+refresh pair (caller wraps in a tx)."""
    raw, token_hash = new_opaque_token()
    return (
        TokenOut(
            access_token=create_access_token(user.id, user.token_version),
            refresh_token=raw,
            expires_in=settings.access_token_ttl_minutes * 60,
        ),
        token_hash,
        family_id or uuid.uuid4().hex,
    )


async def _store_refresh(user: User, token_hash: str, family_id: str) -> None:
    ctx = current()
    await refresh_repo.create(
        data={
            "user_id": user.id,
            "family_id": family_id,
            "token_hash": token_hash,
            "expires_at": utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            "ip": ctx.ip,
            "user_agent": ctx.user_agent,
        }
    )


async def _logout_all_steps(user: User) -> None:
    await users_repo.update(user.id, {"token_version": user.token_version + 1})
    await refresh_repo.revoke_all_for_user(user.id)


async def register(payload: RegisterIn) -> TokenOut:
    email = payload.email.lower()
    async with transaction():
        if await users_repo.find_by_email(email) is not None:
            raise ConflictError(Msg.USER_EMAIL_TAKEN)
        user = await users_repo.create(
            data={
                "email": email,
                "password_hash": hash_password(payload.password),
                "name": payload.name,
                "locale": locale_var.get(),
            }
        )
        await audit.record(
            AuditAction.AUTH_REGISTER,
            AuditResource.USER,
            user.id,
            actor_id=user.id,
            after=UserOut.model_validate(user),
        )
        token, token_hash, family = _issue_pair(user)
        await _store_refresh(user, token_hash, family)
        await enqueue(
            JobType.AUTH_SEND_TOKEN_EMAIL,
            SendTokenEmailPayload(user_id=user.id, purpose=TokenPurpose.VERIFY_EMAIL),
            user_id=user.id,
        )
    return token


async def login(payload: LoginIn) -> TokenOut:
    email = payload.email.lower()
    account = email_identity(email)
    if await peek(RateBucket.LOGIN_ACCOUNT, account) >= 5:
        raise UnauthorizedError(Msg.AUTH_INVALID_CREDENTIALS)
    user = await users_repo.find_by_email(email)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or not verify_password(payload.password, user.password_hash)
    ):
        reason = AuditReason.UNKNOWN_EMAIL if user is None else AuditReason.BAD_PASSWORD
        await audit.record(
            AuditAction.AUTH_LOGIN_FAILED,
            AuditResource.USER,
            user.id if user else None,
            outcome=AuditOutcome.FAILURE,
            metadata={"email_hash": email_identity(email), "reason": reason},
        )
        await enforce(RateBucket.LOGIN_ACCOUNT, account)
        raise UnauthorizedError(Msg.AUTH_INVALID_CREDENTIALS)
    await reset(RateBucket.LOGIN_ACCOUNT, account)
    async with transaction():
        token, token_hash, family = _issue_pair(user)
        await _store_refresh(user, token_hash, family)
        await audit.record(AuditAction.AUTH_LOGIN, AuditResource.USER, user.id, actor_id=user.id)
    return token


async def _revoke_on_reuse(token_id: str, family_id: str) -> None:
    """Reuse of a consumed token => revoke the whole family + audit, in one committed tx."""
    async with transaction():
        await refresh_repo.revoke_family(family_id)
        await audit.record(
            AuditAction.AUTH_REFRESH_REUSE_DETECTED,
            AuditResource.TOKEN,
            token_id,
            outcome=AuditOutcome.FAILURE,
        )


async def refresh(raw: str) -> TokenOut:
    token_hash = hash_token(raw)
    record = await refresh_repo.find_by_hash(token_hash)
    if record is None or record.expires_at <= utcnow():
        raise UnauthorizedError(Msg.AUTH_REFRESH_INVALID)
    if record.revoked_at is not None:  # reuse of an already-consumed token
        await _revoke_on_reuse(record.id, record.family_id)
        raise UnauthorizedError(Msg.AUTH_REFRESH_INVALID)
    user = await users_service_get(record.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise UnauthorizedError(Msg.AUTH_REFRESH_INVALID)

    token: TokenOut | None = None
    reuse = False
    async with transaction():
        if not await refresh_repo.revoke_if_active(record.id):  # lost the race => reuse
            reuse = True
        else:
            token, new_hash, _ = _issue_pair(user, record.family_id)
            await _store_refresh(user, new_hash, record.family_id)
            await refresh_repo.mark_replaced(record.id, new_hash)  # link replacement
            await audit.record(AuditAction.AUTH_REFRESH, AuditResource.TOKEN, record.id)
    if reuse:  # revocation must COMMIT, so it runs in its own tx before we reject
        await _revoke_on_reuse(record.id, record.family_id)
        raise UnauthorizedError(Msg.AUTH_REFRESH_INVALID)
    assert token is not None
    return token


async def users_service_get(user_id: str) -> User | None:
    from typing import cast

    from app.features.users import service as users_service

    return cast("User | None", await users_service.find(user_id))


async def logout(raw: str) -> None:
    record = await refresh_repo.find_by_hash(hash_token(raw))
    if record is not None:
        async with transaction():
            await refresh_repo.revoke_family(record.family_id)
            await audit.record(AuditAction.AUTH_LOGOUT, AuditResource.TOKEN, record.id)
    else:
        await audit.record(AuditAction.AUTH_LOGOUT, AuditResource.TOKEN)


async def logout_all(user: User) -> None:
    async with transaction():
        await _logout_all_steps(user)
        await audit.record(AuditAction.AUTH_LOGOUT_ALL, AuditResource.USER, user.id)
    from app.features.users import service as users_service

    await after_commit(lambda: users_service.find.invalidate(user.id))


async def change_password(user: User, payload: ChangePasswordIn) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise UnauthorizedError(Msg.AUTH_PASSWORD_INCORRECT)
    async with transaction():
        await users_repo.update(
            user.id,
            {
                "password_hash": hash_password(payload.new_password),
                "token_version": user.token_version + 1,
            },
        )
        await refresh_repo.revoke_all_for_user(user.id)
        await audit.record(AuditAction.AUTH_PASSWORD_CHANGE, AuditResource.USER, user.id)
    from app.features.users import service as users_service

    await after_commit(lambda: users_service.find.invalidate(user.id))


async def verify_email(raw: str) -> None:
    record = await one_time_repo.find_by_hash(hash_token(raw))
    if (
        record is None
        or record.purpose != TokenPurpose.VERIFY_EMAIL
        or record.expires_at <= utcnow()
    ):
        raise UnauthorizedError(Msg.AUTH_ONE_TIME_TOKEN_INVALID)
    async with transaction():
        if not await one_time_repo.consume(record.id):
            raise UnauthorizedError(Msg.AUTH_ONE_TIME_TOKEN_INVALID)
        await users_repo.update(record.user_id, {"email_verified_at": utcnow()})
        await audit.record(AuditAction.AUTH_EMAIL_VERIFY, AuditResource.USER, record.user_id)


async def resend_verification(user: User) -> None:
    # audit-exempt: queues an email only, no state change
    await enforce(RateBucket.RESEND_USER, user.id)  # per-user cap on email sends
    await enqueue(
        JobType.AUTH_SEND_TOKEN_EMAIL,
        SendTokenEmailPayload(user_id=user.id, purpose=TokenPurpose.VERIFY_EMAIL),
        user_id=user.id,
    )


async def forgot_password(email: str) -> None:
    # per-account cap (in addition to per-IP at the router); no enumeration leak
    await enforce(RateBucket.FORGOT_ACCOUNT, email_identity(email.lower()))
    user = await users_repo.find_by_email(email.lower())
    if user is not None and user.is_active and user.deleted_at is None:
        async with transaction():
            await enqueue(
                JobType.AUTH_SEND_TOKEN_EMAIL,
                SendTokenEmailPayload(user_id=user.id, purpose=TokenPurpose.RESET_PASSWORD),
                user_id=user.id,
            )
            await audit.record(
                AuditAction.AUTH_PASSWORD_RESET_REQUEST,
                AuditResource.USER,
                user.id,
                metadata={"email_hash": email_identity(email)},
            )


async def reset_password(payload: ResetPasswordIn) -> None:
    record = await one_time_repo.find_by_hash(hash_token(payload.token))
    if (
        record is None
        or record.purpose != TokenPurpose.RESET_PASSWORD
        or record.expires_at <= utcnow()
    ):
        raise UnauthorizedError(Msg.AUTH_ONE_TIME_TOKEN_INVALID)
    user = await users_service_get(record.user_id)
    if user is None:
        raise UnauthorizedError(Msg.AUTH_ONE_TIME_TOKEN_INVALID)
    async with transaction():
        if not await one_time_repo.consume(record.id):
            raise UnauthorizedError(Msg.AUTH_ONE_TIME_TOKEN_INVALID)
        await users_repo.update(
            user.id,
            {
                "password_hash": hash_password(payload.new_password),
                "token_version": user.token_version + 1,
            },
        )
        await refresh_repo.revoke_all_for_user(user.id)
        await audit.record(AuditAction.AUTH_PASSWORD_RESET, AuditResource.USER, user.id)
    from app.features.users import service as users_service

    await after_commit(lambda: users_service.find.invalidate(user.id))
