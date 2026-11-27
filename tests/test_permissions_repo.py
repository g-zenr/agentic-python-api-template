"""Final ABAC gaps: raw-SQL grant repo, PDP json decode, audit elif branches, jobs None."""

from types import SimpleNamespace

import pytest

from app.core.constants import Permission
from app.core.exceptions import NotFoundError


class FakeClient:
    def __init__(self):
        self.query_rows: list = []
        self.execute_count = 1
        self.queries: list = []

    async def query_raw(self, sql, *params):
        self.queries.append(("q", sql, params))
        if "WHERE id = $1" in sql:  # get(): respect the id filter
            return [r for r in self.query_rows if r.get("id") == params[0]]
        if "RETURNING" in sql:  # INSERT ... RETURNING -> one row per call
            return [self._inserted[-1]]
        return self.query_rows

    async def execute_raw(self, sql, *params):
        self.queries.append(("e", sql, params))
        return self.execute_count

    _inserted: list = []


@pytest.fixture
def client(monkeypatch):
    from app.features.permissions import repository as repo_mod

    c = FakeClient()
    monkeypatch.setattr(repo_mod, "current_db", lambda: c)
    return c


async def test_grant_repo_list_get_replace_delete_purge(client):
    from app.features.permissions.repository import permission_grant_repo as repo

    client.query_rows = [
        {
            "id": "g1",
            "user_id": "u1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "granted_by": "admin",
            "expires_at": None,
            "created_at": "2026-01-01",
        }
    ]
    rows = await repo.list_for_user("u1")
    assert rows[0]["effect"] == "ALLOW"  # effect cast to text

    assert (await repo.get("g1"))["id"] == "g1"
    assert await repo.get("nope") is None

    client._inserted = [
        {
            "id": "g2",
            "user_id": "u1",
            "resource": "jobs",
            "action": "read_all",
            "effect": "ALLOW",
            "conditions": {"own_only": True},
            "granted_by": "admin",
            "expires_at": None,
            "created_at": "2026-01-01",
        }
    ]
    out = await repo.replace_for_user(
        "u1",
        [
            {
                "resource": "jobs",
                "action": "read_all",
                "effect": "ALLOW",
                "conditions": {"own_only": True},
                "expires_at": None,
            }
        ],
        granted_by="admin",
    )
    assert out[0]["conditions"] == {"own_only": True}  # jsonb decoded
    assert any("DELETE FROM permission_grants" in q[1] for q in client.queries)
    assert any("INSERT INTO permission_grants" in q[1] for q in client.queries)

    client.execute_count = 1
    assert await repo.delete("g2") is True
    client.execute_count = 0
    assert await repo.delete("g2") is False

    client.execute_count = 5
    assert await repo.purge_expired() == 5
    assert any("expires_at < now()" in q[1] for q in client.queries)


async def test_grant_repo_bad_json_conditions(client):
    from app.features.permissions.repository import permission_grant_repo as repo

    client.query_rows = [
        {
            "id": "g1",
            "user_id": "u1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": "{broken json",
            "granted_by": None,
            "expires_at": None,
            "created_at": "2026-01-01",
        }
    ]
    rows = await repo.list_for_user("u1")
    assert rows[0]["conditions"] is None


async def test_pdp_decodes_bad_json_conditions(monkeypatch):
    from app.core import authz

    async def query_raw(sql, *params):
        return [
            {
                "resource": "users",
                "action": "read",
                "effect": "ALLOW",
                "conditions": "{not json",
                "expires_at": None,
            }
        ]

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))
    user = SimpleNamespace(id="u1", role="USER")
    # unparseable conditions decode to None -> treated as a plain ALLOW (not own-scoped)
    assert (await authz.evaluate(user, Permission.USERS_READ)).allowed
    assert await authz.read_scope(user, Permission.USERS_READ) == "all"  # not "own"


async def test_pdp_string_conditions_with_own_only(monkeypatch):
    from app.core import authz

    async def query_raw(sql, *params):
        return [
            {
                "resource": "audit",
                "action": "read",
                "effect": "ALLOW",
                "conditions": '{"own_only": true}',
                "expires_at": None,
            }
        ]

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))
    user = SimpleNamespace(id="u1", role="USER")
    assert await authz.read_scope(user, Permission.AUDIT_READ) == "own"  # string jsonb decoded


async def test_audit_where_query_filter_branch():
    from app.features.audit.schemas import AuditQuery
    from app.features.audit.service import _audit_where

    q = AuditQuery(
        actor_id="u9",
        action=None,
        resource_type=None,
        resource_id=None,
        outcome=None,
        since=None,
        until=None,
    )
    assert _audit_where(q)["actor_id"] == "u9"  # query filter branch (no forced actor)


async def test_list_activity_uses_query_filter_when_not_forced(monkeypatch):
    from app.features.audit.schemas import ActivityQuery
    from app.features.audit.service import list_activity

    captured: dict = {}

    async def fake(params, where=None, order=None):
        captured["where"] = where
        return [], None

    monkeypatch.setattr("app.features.audit.service.activity_repo.paginate_cursor", fake)
    q = ActivityQuery(user_id="u7", status_code=None, path=None, since=None, until=None)
    from app.shared.helpers.pagination import CursorParams

    await list_activity(CursorParams(cursor=None, size=5), q)
    assert captured["where"]["user_id"] == "u7"  # query filter (no forced user)


async def test_jobs_owned_missing_job(monkeypatch, fake_store):
    from app.features.jobs import service as jobs_service

    async def none(job_id):
        return None

    monkeypatch.setattr(jobs_service, "get_store", lambda: SimpleNamespace(get=none))
    user = SimpleNamespace(id="u1", role="USER")
    with pytest.raises(NotFoundError):
        await jobs_service._owned(user, "missing")


async def test_permissions_purge_expired_via_service(monkeypatch):
    from app.features.permissions import service

    async def purge():
        return 3

    monkeypatch.setattr(service.permission_grant_repo, "purge_expired", purge)
    assert await service.purge_expired() == 3


async def test_audit_service_forced_actor_and_user(monkeypatch):
    """list_audit/list_activity FORCE the scope filter when called with the kwarg."""
    from app.features.audit.schemas import ActivityQuery, AuditQuery
    from app.features.audit.service import list_activity, list_audit
    from app.shared.helpers.pagination import CursorParams

    captured: dict = {}

    async def fake(params, where=None, order=None):
        captured["where"] = where
        return [], None

    monkeypatch.setattr("app.features.audit.service.audit_repo.paginate_cursor", fake)
    monkeypatch.setattr("app.features.audit.service.activity_repo.paginate_cursor", fake)

    q = AuditQuery()
    await list_audit(CursorParams(cursor=None, size=5), q, actor_id="me")
    assert captured["where"]["actor_id"] == "me"  # forced (own scope)

    q2 = ActivityQuery(user_id="someone-else")
    await list_activity(CursorParams(cursor=None, size=5), q2, user_id="me")
    assert captured["where"]["user_id"] == "me"  # forced wins over the query filter
