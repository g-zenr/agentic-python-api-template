"""Auth dependencies: `CurrentUser`, `VerifiedUser`, and `require_permission` (RBAC)."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prisma.models import User

from app.core import audit, authz
from app.core.constants import (
    AuditAction,
    AuditOutcome,
    AuditResource,
    Permission,
)
from app.core.context import bind_user
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.messages import Msg
from app.core.security import decode_access_token
from app.features.users.repository import users_repo

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise UnauthorizedError()
    sub, token_version = decode_access_token(creds.credentials)
    # H4: read the user UNCACHED on the auth path so is_active/role/email_verified_at/token_version
    # changes take effect immediately (no ~60s stale-cache authorization window).
    user = await users_repo.get(sub)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or user.token_version != token_version
    ):
        raise UnauthorizedError(Msg.AUTH_TOKEN_INVALID)
    bind_user(user.id)
    return user


def require_permission(*perms: Permission) -> Callable[..., Any]:
    async def checker(
        user: User = Depends(get_current_user),
        request: Request = None,  # type: ignore[assignment]  # FastAPI special-cases exact Request
    ) -> User:
        decision = await authz.allowed(user, *perms)
        if not decision.allowed:
            route = request.scope.get("route") if request else None
            path = route.path if route else (request.url.path if request else None)
            await audit.record(
                AuditAction.ACCESS_DENIED,
                AuditResource.ENDPOINT,
                path,
                outcome=AuditOutcome.DENIED,
                metadata={
                    "reason": decision.reason.value if decision.reason else "unknown",
                    "required": [p.value for p in perms],
                },
            )
            raise ForbiddenError()
        return user

    return checker


async def get_verified_user(user: User = Depends(get_current_user)) -> User:
    from app.core.config import settings

    if settings.require_email_verification and user.email_verified_at is None:
        raise ForbiddenError(Msg.AUTH_EMAIL_NOT_VERIFIED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(get_verified_user)]
