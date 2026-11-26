"""Audit router: read-only cursor access to the audit trail and request activity log."""

from fastapi import APIRouter, Depends

from app.core.constants import Permission, Tag
from app.features.audit import service
from app.features.audit.schemas import ActivityLogOut, ActivityQuery, AuditLogOut, AuditQuery
from app.features.auth.deps import CurrentUser, require_permission
from app.shared.helpers.pagination import CursorParams
from app.shared.helpers.responses import cursor_page_of
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/audit", tags=[Tag.AUDIT])


@router.get(
    "",
    response_model=ApiResponse[list[AuditLogOut]],
    summary="Search the audit trail",
    description="Cursor-paginated, filterable audit entries. Requires audit:read.",
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
async def search_audit(
    params: CursorParams = Depends(), query: AuditQuery = Depends()
) -> ApiResponse:  # noqa: E501
    items, next_cursor = await service.list_audit(params, query)
    return cursor_page_of(items, next_cursor, params, schema=AuditLogOut)


@router.get(
    "/me",
    response_model=ApiResponse[list[AuditLogOut]],
    summary="My audit trail",
    description="Cursor-paginated audit entries where I am the actor.",
)
async def my_audit(user: CurrentUser, params: CursorParams = Depends()) -> ApiResponse:
    items, next_cursor = await service.list_my_audit(user, params)
    return cursor_page_of(items, next_cursor, params, schema=AuditLogOut)


@router.get(
    "/activity",
    response_model=ApiResponse[list[ActivityLogOut]],
    summary="Request activity log",
    description="Cursor-paginated per-request activity. Requires activity:read.",
    dependencies=[Depends(require_permission(Permission.ACTIVITY_READ))],
)
async def activity_log(
    params: CursorParams = Depends(), query: ActivityQuery = Depends()
) -> ApiResponse:  # noqa: E501
    items, next_cursor = await service.list_activity(params, query)
    return cursor_page_of(items, next_cursor, params, schema=ActivityLogOut)
