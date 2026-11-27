"""Idempotency for create endpoints: dedupe by (scope, key) with a stored response."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast

from prisma.errors import UniqueViolationError

from app.core.config import settings
from app.core.constants import Header
from app.core.exceptions import ConflictError
from app.core.messages import Msg
from app.core.uow import current_db
from app.shared.utils.time import utcnow


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def run_once(
    scope: str,
    key: str,
    request_payload: Any,
    fn: Callable[[], Awaitable[tuple[int, Any]]],
) -> tuple[int, Any, bool]:
    """Run `fn` once per (scope, key). Returns (status_code, data, replay)."""
    request_hash = _hash(request_payload)
    d = current_db().idempotencyrecord
    try:
        await d.create(data={"scope": scope, "key": key, "request_hash": request_hash})
    except UniqueViolationError as exc:
        existing = await d.find_first(where={"scope": scope, "key": key})
        if existing is None or existing.request_hash != request_hash:
            raise ConflictError(Msg.IDEMPOTENCY_MISMATCH) from exc
        if existing.status_code is None:
            raise ConflictError(Msg.IDEMPOTENCY_IN_PROGRESS) from exc
        return existing.status_code, existing.response, True
    try:
        status_code, data = await fn()
        await d.update(
            where={"id": (await d.find_first(where={"scope": scope, "key": key})).id},
            data={"status_code": status_code, "response": data},
        )
        return status_code, data, False
    except Exception:
        record = await d.find_first(where={"scope": scope, "key": key})
        if record is not None:
            await d.delete(where={"id": record.id})
        raise


async def purge_expired() -> int:
    cutoff = utcnow() - timedelta(hours=settings.idempotency_ttl_hours)
    return cast(
        int, await current_db().idempotencyrecord.delete_many(where={"created_at": {"lt": cutoff}})
    )


IDEMPOTENCY_REPLAY = Header.IDEMPOTENCY_REPLAY
