"""HTTP helpers: client IP, ETag/if-match, polling headers, and idempotency key."""

import hashlib
from typing import Annotated

from fastapi import Header, Request, Response

from app.core.config import settings
from app.core.constants import Header as Hdr
from app.core.constants import Limits


def client_ip(request: Request) -> str | None:
    """Resolve the client IP, honoring `X-Forwarded-For` only when `TRUST_PROXY_HEADERS` is set."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get(Hdr.FORWARDED_FOR)
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def etag_for(*parts: object) -> str:
    """Build a quoted ETag from the first 16 hex chars of a sha256 over the joined parts."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]
    return f'"{digest}"'


def etag_matches(request: Request, etag: str) -> bool:
    """True when the request's `If-None-Match` matches `etag` (supports `*` and comma lists)."""
    header = request.headers.get(Hdr.IF_NONE_MATCH)
    if not header:
        return False
    candidates = [c.strip() for c in header.split(",")]
    return "*" in candidates or etag in candidates


def parse_if_match(header: str | None) -> int | None:
    """Parse an `If-Match` header into a version int. Accepts `"3"` and `W/"3"`. None when absent."""  # noqa: E501
    if not header:
        return None
    token = header.strip().strip('"')
    if token.upper().startswith("W/"):
        token = token[2:].strip('"')
    try:
        return int(token)
    except ValueError:
        return None


def set_retry_after(response: Response) -> None:
    """Set `Retry-After` to the configured job poll hint (seconds)."""
    response.headers[Hdr.RETRY_AFTER] = str(settings.job_poll_hint_seconds)


def set_poll_headers(response: Response, job_id: str) -> None:
    """Set `Location` to the job's poll URL and `Retry-After` for a 202 response."""
    response.headers[Hdr.LOCATION] = f"{settings.api_prefix}/jobs/{job_id}"
    set_retry_after(response)


IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", max_length=Limits.IDEMPOTENCY_KEY_MAX)
]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
