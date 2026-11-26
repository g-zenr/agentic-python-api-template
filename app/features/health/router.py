"""Health router: liveness, readiness (DB + cache), and a hidden liveness alias at /health."""

import asyncio

from fastapi import APIRouter, Request

from app.core.cache import cache
from app.core.config import settings
from app.core.constants import Tag
from app.core.database import db
from app.core.exceptions import ServiceUnavailableError
from app.core.messages import Msg
from app.shared.helpers.responses import ok
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/health", tags=[Tag.HEALTH], include_in_schema=False)


@router.get(
    "/live",
    response_model=ApiResponse[dict],
    summary="Liveness",
    description="Always 200 if the process is up. Touches no dependencies.",
)
async def live() -> ApiResponse:
    return ok({"status": "up", "version": settings.app_version}, Msg.HEALTH_OK)


@router.get(
    "/ready",
    response_model=ApiResponse[dict],
    summary="Readiness",
    description="200 when the database and cache are reachable, else 503 with per-check status.",
)
async def ready(request: Request) -> ApiResponse:
    if getattr(request.app.state, "shutting_down", False):
        raise ServiceUnavailableError(details={"database": "down", "cache": "down"})
    checks: dict[str, str] = {}
    try:
        await asyncio.wait_for(db.query_raw("SELECT 1"), settings.health_check_timeout_seconds)
        checks["database"] = "up"
    except Exception:
        checks["database"] = "down"
    if settings.cache_backend == "memory":
        checks["cache"] = "skipped"
    else:
        checks["cache"] = "up" if await cache.backend.ping() else "down"
    if any(v == "down" for v in checks.values()):
        raise ServiceUnavailableError(details=checks)
    return ok({"checks": checks}, Msg.HEALTH_OK)


@router.get(
    "",
    response_model=ApiResponse[dict],
    summary="Liveness (alias)",
    description="Hidden alias of /health/live for backward compatibility.",
)
async def health_alias() -> ApiResponse:
    return ok({"status": "up", "version": settings.app_version}, Msg.HEALTH_OK)
