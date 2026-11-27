"""User router: authenticated profile endpoints and a permission-gated listing."""

from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.core.constants import Permission, Tag
from app.core.messages import Msg
from app.features.auth.deps import CurrentUser, require_permission
from app.features.jobs.schemas import JobOut
from app.features.users import service
from app.features.users.schemas import UserOut, UserUpdate
from app.shared.helpers.http import IdempotencyKey, set_poll_headers
from app.shared.helpers.pagination import PageParams
from app.shared.helpers.responses import ok, page_of
from app.shared.schemas import ApiModel, ApiResponse

router = APIRouter(prefix="/users", tags=[Tag.USERS])


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="Get my profile",
    description="Return the authenticated user's own profile.",
)
async def read_me(user: CurrentUser) -> ApiResponse[Any]:
    return ok(UserOut.model_validate(user))


@router.patch(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="Update my profile",
    description="Partially update the authenticated user's name or locale.",
)
async def update_me(user: CurrentUser, payload: UserUpdate) -> ApiResponse[Any]:
    updated = await service.update_me(user, payload)
    return ok(UserOut.model_validate(updated), Msg.USER_UPDATED)


@router.get(
    "",
    response_model=ApiResponse[list[UserOut]],
    summary="List users",
    description="Paginated list of all users. Requires users:read.",
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
)
async def list_users(params: PageParams = Depends()) -> ApiResponse[Any]:
    items, total = await service.list_users(params)
    return page_of(items, total, params, schema=UserOut)


class DeleteMeIn(ApiModel):
    password: str


@router.delete(
    "/me",
    response_model=ApiResponse[dict[str, Any]],
    summary="Delete my account",
    description="Anonymize and deactivate the account, revoke tokens, and schedule erasure.",
)
async def delete_me(user: CurrentUser, payload: DeleteMeIn) -> ApiResponse[Any]:
    await service.delete_me(user, payload.password)
    return ok(None, Msg.USER_DELETED)


@router.post(
    "/me/export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[JobOut],
    summary="Export my data (async)",
    description="Returns 202 immediately. Poll the URL in the Location header.",
)
async def export_me(
    response: Response, user: CurrentUser, key: IdempotencyKey = None
) -> ApiResponse[Any]:  # noqa: E501
    job = await service.request_export(user, key)
    set_poll_headers(response, job.id)
    return ok(job, Msg.JOB_QUEUED)
