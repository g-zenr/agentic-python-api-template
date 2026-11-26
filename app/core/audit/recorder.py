"""Audit recorder: the ONLY way to write an audit entry. Call `audit.record(...)` from services."""

import logging
from typing import Any

from app.core.audit.repository import audit_repo
from app.core.config import settings
from app.core.constants import ActorType, AuditAction, AuditOutcome, AuditResource, Limits
from app.core.context import current
from app.core.uow import in_transaction
from app.shared.utils import json as jsonx
from app.shared.utils.diff import diff, redact
from app.shared.utils.text import truncate

log = logging.getLogger(__name__)

_sink = audit_repo


def set_sink(sink: Any) -> None:
    """Swap the audit sink (tests install a list sink)."""
    global _sink
    _sink = sink


async def record(
    action: AuditAction,
    resource: AuditResource,
    resource_id: str | None = None,
    *,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    before: Any = None,
    after: Any = None,
    metadata: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    """Write one audit entry describing who did what to which resource, with a redacted diff."""
    ctx = current()
    actor_id = actor_id or ctx.user_id
    if actor_id:
        actor_type = ActorType.USER
    elif ctx.actor_type == ActorType.SYSTEM:
        actor_type = ActorType.SYSTEM
    else:
        actor_type = ActorType.ANONYMOUS

    changes = diff(before, after) if (before is not None or after is not None) else None

    meta = redact(metadata or {})
    if ctx.job_id:
        meta["job_id"] = ctx.job_id

    entry = {
        "actor_id": actor_id,
        "actor_type": actor_type.value,
        "action": action.value,
        "resource_type": resource.value,
        "resource_id": resource_id,
        "outcome": outcome.value,
        "changes": changes,
        "metadata": meta or None,
        "request_id": ctx.request_id,
        "ip": ctx.ip,
        "user_agent": truncate(ctx.user_agent, Limits.USER_AGENT_MAX) if ctx.user_agent else None,
    }

    try:
        await _sink.append(entry)
    except Exception:
        log.error("audit write failed: %s", jsonx.dumps(entry), exc_info=True)
        # Inside a transaction an audit failure ALWAYS propagates (the mutation rolls back).
        if settings.audit_fail_closed or in_transaction():
            raise
