"""Audit service: read-only cursor queries over the audit and activity logs (no COUNT)."""

from typing import Any

from prisma.models import User

from app.core.activity.repository import activity_repo
from app.core.audit.repository import audit_repo
from app.features.audit.schemas import ActivityQuery, AuditQuery
from app.shared.helpers.pagination import CursorParams
from app.shared.utils.time import date_range

_AUDIT_ORDER = [{"occurred_at": "desc"}, {"id": "desc"}]


def _audit_where(query: AuditQuery, *, actor_id: str | None = None) -> dict[str, Any]:
    where: dict[str, Any] = {}
    if actor_id is not None:
        where["actor_id"] = actor_id
    elif query.actor_id is not None:
        where["actor_id"] = query.actor_id
    if query.action is not None:
        where["action"] = query.action
    if query.resource_type is not None:
        where["resource_type"] = query.resource_type
    if query.resource_id is not None:
        where["resource_id"] = query.resource_id
    if query.outcome is not None:
        where["outcome"] = query.outcome
    occurred = date_range(query.since, query.until)
    if occurred is not None:
        where["occurred_at"] = occurred
    return where


async def list_audit(params: CursorParams, query: AuditQuery):
    return await audit_repo.paginate_cursor(params, where=_audit_where(query), order=_AUDIT_ORDER)


async def list_my_audit(user: User, params: CursorParams):
    return await audit_repo.paginate_cursor(params, where={"actor_id": user.id}, order=_AUDIT_ORDER)


async def list_activity(params: CursorParams, query: ActivityQuery):
    where: dict[str, Any] = {}
    if query.user_id is not None:
        where["user_id"] = query.user_id
    if query.status_code is not None:
        where["status_code"] = query.status_code
    if query.path is not None:
        where["path"] = query.path
    occurred = date_range(query.since, query.until)
    if occurred is not None:
        where["occurred_at"] = occurred
    return await activity_repo.paginate_cursor(params, where=where, order=_AUDIT_ORDER)
