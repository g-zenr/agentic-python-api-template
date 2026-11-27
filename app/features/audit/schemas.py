"""Audit feature schemas: read models for audit/activity logs and their query dependencies."""

from datetime import datetime
from typing import Any

from fastapi import Query

from app.shared.schemas import ApiModel


class AuditLogOut(ApiModel):
    id: str
    occurred_at: datetime
    actor_id: str | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    changes: dict[str, Any] | None
    metadata: dict[str, Any] | None
    request_id: str | None
    ip: str | None
    user_agent: str | None


class ActivityLogOut(ApiModel):
    id: str
    occurred_at: datetime
    user_id: str | None
    method: str
    path: str
    status_code: int
    duration_ms: int
    request_id: str | None
    ip: str | None


class AuditQuery:
    def __init__(
        self,
        actor_id: str | None = Query(default=None),
        action: str | None = Query(default=None),
        resource_type: str | None = Query(default=None),
        resource_id: str | None = Query(default=None),
        outcome: str | None = Query(default=None),
        since: datetime | None = Query(default=None),
        until: datetime | None = Query(default=None),
    ):
        self.actor_id = actor_id
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.outcome = outcome
        self.since = since
        self.until = until


class ActivityQuery:
    def __init__(
        self,
        user_id: str | None = Query(default=None),
        status_code: int | None = Query(default=None),
        path: str | None = Query(default=None),
        since: datetime | None = Query(default=None),
        until: datetime | None = Query(default=None),
    ):
        self.user_id = user_id
        self.status_code = status_code
        self.path = path
        self.since = since
        self.until = until
