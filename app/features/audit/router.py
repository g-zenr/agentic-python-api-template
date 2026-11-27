"""Audit router: read-only cursor access to the audit trail and request activity log.

`/audit` and `/audit/activity` are scope-aware: an `own_only` grant (ABAC, ADR-0019) authorizes
the route but narrows results to the caller's own rows; baseline/`all` grants see everything.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core import audit as audit_log
from app.core import authz
from app.core.constants import (
    AuditAction,
    AuditOutcome,
    AuditReason,
    AuditResource,
    Permission,
    Tag,
)
from app.core.exceptions import ForbiddenError
from app.features.audit import service
from app.features.audit.schemas import ActivityLogOut, ActivityQuery, AuditLogOut, AuditQuery
from app.features.auth.deps import CurrentUser
from app.shared.helpers.pagination import CursorParams
from app.shared.helpers.responses import cursor_page_of
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/audit", tags=[Tag.AUDIT])


async def _deny(request: Request, required: Permission) -> None:
    route = request.scope.get("route")
    path = route.path if route else request.url.path
    await audit_log.record(
        AuditAction.ACCESS_DENIED,
        AuditResource.ENDPOINT,
        path,
        outcome=AuditOutcome.DENIED,
        metadata={
            "reason": AuditReason.INSUFFICIENT_PERMISSION.value,
            "required": [required.value],
        },
    )


@router.get(
    "",
    response_model=ApiResponse[list[AuditLogOut]],
    summary="Search the audit trail",
    description=(
        "Cursor-paginated, filterable audit entries. Requires audit:read; an own_only grant "
        "narrows results to your own entries."
    ),
)
async def search_audit(
    request: Request,
    user: CurrentUser,
    params: CursorParams = Depends(),
    query: AuditQuery = Depends(),
) -> ApiResponse[Any]:  # noqa: E501
    scope = await authz.read_scope(user, Permission.AUDIT_READ)
    if scope is None:
        await _deny(request, Permission.AUDIT_READ)
        raise ForbiddenError()
    actor_id = user.id if scope == "own" else None
    if scope == "own" and query.actor_id not in (None, user.id):
        await _deny(request, Permission.AUDIT_READ)
        raise ForbiddenError()  # an own-scope grant cannot inspect someone else
    items, next_cursor = await service.list_audit(params, query, actor_id=actor_id)
    return cursor_page_of(items, next_cursor, params, schema=AuditLogOut)


@router.get(
    "/me",
    response_model=ApiResponse[list[AuditLogOut]],
    summary="My audit trail",
    description="Cursor-paginated audit entries where I am the actor.",
)
async def my_audit(user: CurrentUser, params: CursorParams = Depends()) -> ApiResponse[Any]:
    items, next_cursor = await service.list_my_audit(user, params)
    return cursor_page_of(items, next_cursor, params, schema=AuditLogOut)


@router.get(
    "/activity",
    response_model=ApiResponse[list[ActivityLogOut]],
    summary="Request activity log",
    description=(
        "Cursor-paginated per-request activity. Requires activity:read; an own_only grant narrows "
        "results to your own requests."
    ),
)
async def activity_log(
    request: Request,
    user: CurrentUser,
    params: CursorParams = Depends(),
    query: ActivityQuery = Depends(),
) -> ApiResponse[Any]:  # noqa: E501
    scope = await authz.read_scope(user, Permission.ACTIVITY_READ)
    if scope is None:
        await _deny(request, Permission.ACTIVITY_READ)
        raise ForbiddenError()
    forced_user = user.id if scope == "own" else None
    if scope == "own" and query.user_id not in (None, user.id):
        await _deny(request, Permission.ACTIVITY_READ)
        raise ForbiddenError()
    items, next_cursor = await service.list_activity(params, query, user_id=forced_user)
    return cursor_page_of(items, next_cursor, params, schema=ActivityLogOut)
