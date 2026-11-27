"""Fixed-window rate limiting. Sensitive buckets fail closed on backend errors."""

import hashlib
from collections.abc import Callable
from typing import Any

from fastapi import Request

from app.core.cache import cache
from app.core.config import settings
from app.core.constants import RATE_POLICY, RateBucket
from app.core.exceptions import RateLimitedError
from app.core.metrics import rate_limit_rejections_total


async def enforce(
    bucket: RateBucket,
    identity: str,
    *,
    limit: int | None = None,
    window: int | None = None,
) -> None:
    """Count one hit; raise RateLimitedError(retry_after) when over the limit."""
    if not settings.rate_limit_enabled:
        return
    default_limit, default_window = RATE_POLICY.get(
        bucket, (settings.rate_limit_global_per_minute, 60)
    )  # noqa: E501
    retry = await cache.rate_hit(
        bucket.value, identity, limit or default_limit, window or default_window
    )
    if retry:
        rate_limit_rejections_total.labels(bucket=bucket.value).inc()
        raise RateLimitedError(retry)


async def peek(bucket: RateBucket, identity: str) -> int:
    """Current count, no increment."""
    return await cache.rate_peek(bucket.value, identity)


async def reset(bucket: RateBucket, identity: str) -> None:
    await cache.rate_reset(bucket.value, identity)


def by_ip(bucket: RateBucket) -> Callable[..., Any]:
    """FastAPI dependency factory: rate-limit by client IP."""

    async def dep(request: Request) -> None:
        from app.shared.helpers.http import client_ip

        ip = client_ip(request) or "unknown"
        await enforce(bucket, ip)

    return dep


def email_identity(email: str) -> str:
    """sha256 of the lowercased email (never store the raw email as a key)."""
    return hashlib.sha256(email.lower().encode()).hexdigest()
