"""User service: profile access, administration, and account deletion/export (audited)."""

import secrets
from typing import cast

from prisma.models import User

from app.core import audit
from app.core.cache import cached
from app.core.config import settings
from app.core.constants import AuditAction, AuditResource, CacheNS, CacheTTL, JobType, Limits
from app.core.exceptions import BadInputError, ConflictError, NotFoundError, UnauthorizedError
from app.core.jobs import enqueue
from app.core.messages import Msg
from app.core.security import hash_password, verify_password
from app.core.uow import after_commit, transaction
from app.features.jobs import service as jobs_service
from app.features.jobs.schemas import JobOut
from app.features.users.repository import users_repo
from app.features.users.schemas import UserOut, UserUpdate
from app.shared.helpers.pagination import PageParams
from app.shared.utils.time import utcnow


@cached(CacheNS.USER, CacheTTL.SHORT, key=lambda user_id: user_id, type_=User)
async def find(user_id: str) -> User | None:
    """Fetch a user by id (cached per user for CacheTTL.SHORT). Invalidated on every user write."""
    return await users_repo.get(user_id)


async def get(user_id: str) -> User:
    user = cast("User | None", await find(user_id))
    if user is None:
        raise NotFoundError(Msg.USER_NOT_FOUND)
    return user


async def update_me(user: User, payload: UserUpdate) -> User:
    data = payload.model_dump(exclude_unset=True)
    async with transaction():
        updated = await users_repo.update(user.id, data)
        if updated is None:
            raise NotFoundError(Msg.USER_NOT_FOUND)
        await audit.record(
            AuditAction.USER_UPDATE,
            AuditResource.USER,
            user.id,
            before=UserOut.model_validate(user),
            after=UserOut.model_validate(updated),
        )
    await after_commit(lambda: find.invalidate(user.id))
    return updated


async def delete_me(user: User, password: str) -> None:
    """Anonymize and deactivate the account, revoke tokens, and schedule the erase job."""
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError(Msg.AUTH_PASSWORD_INCORRECT)
    async with transaction():
        await users_repo.update(
            user.id,
            {
                "email": f"deleted-{user.id}@invalid",
                "name": "Deleted user",
                "password_hash": hash_password(secrets.token_urlsafe(32)),
                "is_active": False,
                "deleted_at": utcnow(),
                "token_version": user.token_version + 1,
            },
        )
        from app.features.auth.repository import refresh_repo

        await refresh_repo.revoke_all_for_user(user.id)
        await audit.record(AuditAction.USER_DELETE, AuditResource.USER, user.id)
        await enqueue(
            JobType.ACCOUNT_ERASE,
            user_id=None,
            delay_seconds=settings.account_erase_delay_days * 86400,
        )
    await after_commit(lambda: find.invalidate(user.id))


async def request_export(user: User, idempotency_key: str | None) -> JobOut:
    async with transaction():
        job = await jobs_service.submit(
            user, JobType.ACCOUNT_EXPORT, idempotency_key=idempotency_key
        )
        await audit.record(AuditAction.USER_EXPORT_REQUEST, AuditResource.USER, user.id)
    return job


async def list_users(params: PageParams) -> tuple[list[User], int]:
    return await users_repo.paginate(params)


async def create_admin(email: str, password: str, promote: bool) -> None:
    """Create an ADMIN (verified) or promote an existing user (only with promote=True). Audited as SYSTEM."""  # noqa: E501

    from app.core.constants import ActorType, Role
    from app.core.context import RequestContext, request_ctx

    email = email.lower()
    if not (Limits.PASSWORD_MIN <= len(password) <= Limits.PASSWORD_MAX):
        raise BadInputError(Msg.VALIDATION_ERROR)
    ctx_token = request_ctx.set(RequestContext(actor_type=ActorType.SYSTEM))
    try:
        async with transaction():
            existing = await users_repo.find_by_email(email)
            if existing is not None:
                if not promote:
                    raise ConflictError(Msg.USER_EMAIL_TAKEN)
                await users_repo.update(existing.id, {"role": Role.ADMIN.value})
                user_id = existing.id
            else:
                user = await users_repo.create(
                    data={
                        "email": email,
                        "password_hash": hash_password(password),
                        "name": "Admin",
                        "role": Role.ADMIN.value,
                        "email_verified_at": utcnow(),
                    }
                )
                user_id = user.id
            await audit.record(AuditAction.ADMIN_BOOTSTRAP, AuditResource.USER, user_id)
        if existing is not None:  # role changed -> the user's cached grants/baseline is stale
            from app.core.authz import _load_grants

            await after_commit(lambda: _load_grants.invalidate(existing.id))
    finally:
        request_ctx.reset(ctx_token)
