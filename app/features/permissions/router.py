"""Permissions router: the assignable catalog and per-user grant administration (admin only)."""

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.core.constants import Header, Permission, RateBucket, Tag
from app.core.exceptions import PreconditionFailedError, PreconditionRequiredError
from app.core.messages import Msg
from app.core.ratelimit import by_ip
from app.features.auth.deps import CurrentUser, require_permission
from app.features.permissions import service
from app.features.permissions.schemas import CatalogOut, EffectiveOut, GrantsIn
from app.shared.helpers.http import IdempotencyKey, IfMatch, etag_for
from app.shared.helpers.idempotency import run_once
from app.shared.helpers.responses import ok
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/permissions", tags=[Tag.PERMISSIONS])
_manage = require_permission(Permission.PERMISSIONS_MANAGE)


def _etag(user_id: str, effective: EffectiveOut) -> str:
    return etag_for(
        user_id, len(effective.grants), sorted(g.model_dump_json() for g in effective.grants)
    )


@router.get(
    "/catalog",
    response_model=ApiResponse[CatalogOut],
    summary="Assignable permission catalog",
    description=(
        "Every page (resource) × action that can be granted, derived from the Permission enum. "
        "Requires permissions:manage."
    ),
    dependencies=[Depends(_manage)],
)
async def get_catalog() -> ApiResponse[Any]:
    return ok(service.catalog())


@router.get(
    "/users/{user_id}",
    response_model=ApiResponse[EffectiveOut],
    summary="Effective permissions for a user",
    description=(
        "Role baseline plus explicit grants (DENY grants shown with their effect), and the "
        "resulting effective set. Returns an ETag for optimistic replacement. Requires "
        "permissions:manage."
    ),
    dependencies=[Depends(_manage)],
)
async def get_effective(user_id: str, response: Response) -> ApiResponse[Any]:
    effective = await service.list_effective(user_id)
    response.headers[Header.ETAG] = _etag(user_id, effective)
    return ok(effective)


@router.put(
    "/users/{user_id}",
    response_model=ApiResponse[EffectiveOut],
    summary="Replace a user's grants",
    description=(
        "Replace the full grant set (page × action × effect ± conditions). Send Idempotency-Key on "
        "retry and If-Match from the last GET to avoid overwriting concurrent changes. Requires "
        "permissions:manage."
    ),
    dependencies=[Depends(_manage), Depends(by_ip(RateBucket.PERMISSIONS_IP))],
)
async def put_grants(
    user_id: str,
    payload: GrantsIn,
    response: Response,
    user: CurrentUser,
    key: IdempotencyKey = None,  # noqa: RUF013
    if_match: IfMatch = None,  # noqa: RUF013
) -> ApiResponse[Any]:
    current = await service.list_effective(user_id)
    etag = _etag(user_id, current)
    if if_match is None:
        raise PreconditionRequiredError(Msg.PRECONDITION_REQUIRED)
    if if_match.strip() != etag:
        raise PreconditionFailedError(Msg.PRECONDITION_FAILED)
    if key:  # H1: retries are deduped; a repeated key replays the stored response
        status_code, data, replay = await run_once(
            f"permissions:{user_id}",
            key,
            payload.model_dump(mode="json"),
            lambda: _replace(user, user_id, payload),
        )
        response.status_code = status_code
        if replay:
            response.headers[Header.IDEMPOTENCY_REPLAY] = "true"
        return ok(data, Msg.PERMISSIONS_UPDATED)
    effective = await service.replace_grants(user, user_id, payload)
    response.headers[Header.ETAG] = _etag(user_id, effective)
    return ok(effective, Msg.PERMISSIONS_UPDATED)


async def _replace(
    user: CurrentUser, user_id: str, payload: GrantsIn
) -> tuple[int, dict[str, Any]]:
    effective = await service.replace_grants(user, user_id, payload)
    return 200, effective.model_dump(mode="json")


@router.delete(
    "/users/{user_id}/{grant_id}",
    response_model=ApiResponse[dict[str, Any]],
    summary="Revoke one grant",
    description="Remove a single page × action grant from a user. Requires permissions:manage.",
    dependencies=[Depends(_manage), Depends(by_ip(RateBucket.PERMISSIONS_IP))],
)
async def delete_grant(user_id: str, grant_id: str, user: CurrentUser) -> ApiResponse[Any]:
    await service.delete_grant(user, user_id, grant_id)
    return ok({"id": grant_id}, Msg.DELETED)
