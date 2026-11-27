"""Audit feature service: filter building + cursor delegation (read-only)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.activity.repository import activity_repo
from app.core.audit.repository import audit_repo
from app.features.audit.schemas import ActivityQuery, AuditQuery
from app.features.audit.service import list_activity, list_audit, list_my_audit
from app.shared.helpers.pagination import CursorParams

_AUDIT_ORDER = [{"occurred_at": "desc"}, {"id": "desc"}]


def _audit_query(**kw) -> AuditQuery:
    base = dict(
        actor_id=None,
        action=None,
        resource_type=None,
        resource_id=None,
        outcome=None,
        since=None,
        until=None,
    )
    base.update(kw)
    return AuditQuery(**base)


def _activity_query(**kw) -> ActivityQuery:
    base = dict(user_id=None, status_code=None, path=None, since=None, until=None)
    base.update(kw)
    return ActivityQuery(**base)


def _params(size: int = 10) -> CursorParams:
    return CursorParams(cursor=None, size=size)


async def test_list_audit_builds_where_and_order(monkeypatch):
    captured: dict = {}

    async def fake(params, where=None, order=None):
        captured["where"] = where
        captured["order"] = order
        return ([], None)

    monkeypatch.setattr(audit_repo, "paginate_cursor", fake)
    since = datetime(2026, 1, 1, tzinfo=UTC)
    await list_audit(
        _params(),
        _audit_query(
            actor_id="u1",
            action="note.create",
            resource_type="note",
            resource_id="n1",
            outcome="success",
            since=since,
        ),
    )
    assert captured["where"] == {
        "actor_id": "u1",
        "action": "note.create",
        "resource_type": "note",
        "resource_id": "n1",
        "outcome": "success",
        "occurred_at": {"gte": since},
    }
    assert captured["order"] == _AUDIT_ORDER


async def test_list_my_audit_forces_actor(monkeypatch):
    captured: dict = {}

    async def fake(params, where=None, order=None):
        captured["where"] = where
        return ([], None)

    monkeypatch.setattr(audit_repo, "paginate_cursor", fake)
    await list_my_audit(SimpleNamespace(id="me"), _params())
    assert captured["where"] == {"actor_id": "me"}


async def test_list_activity_filters(monkeypatch):
    captured: dict = {}

    async def fake(params, where=None, order=None):
        captured["where"] = where
        return ([], None)

    monkeypatch.setattr(activity_repo, "paginate_cursor", fake)
    await list_activity(_params(), _activity_query(user_id="u1", status_code=200, path="/api/v1/x"))
    assert captured["where"] == {"user_id": "u1", "status_code": 200, "path": "/api/v1/x"}
