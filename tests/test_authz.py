"""PDP (app/core/authz.py): baseline, grants, deny-wins, expiry, own_only, fail-closed."""

from types import SimpleNamespace

import pytest

from app.core import authz
from app.core.constants import Permission, Role
from app.core.exceptions import ForbiddenError
from app.core.messages import Msg


def _user(role=Role.USER, user_id="u1"):
    return SimpleNamespace(id=user_id, role=role.value if isinstance(role, Role) else role)


@pytest.fixture(autouse=True)
def _grants_backend(monkeypatch):
    """Default: an empty grants backend (baseline-only decisions). `_set` also busts the cache."""
    from app.core.cache import cache as cache_facade

    state: dict = {"rows": [], "fail": False}

    async def query_raw(sql, *params):
        if state["fail"]:
            raise RuntimeError("grants backend down")
        return state["rows"]

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))

    def _set(rows=None, fail=False):
        if rows is not None:
            state["rows"] = rows
        state["fail"] = fail
        cache_facade.backend = type(cache_facade.backend)()  # fresh memory backend per set
        cache_facade.stats = {"hits": 0, "misses": 0, "errors": 0}

    yield _set


@pytest.fixture(autouse=True)
def _fresh_permission_cache(_fresh_cache):
    yield


async def test_baseline_admin_allowed_user_denied(_grants_backend):
    assert (await authz.evaluate(_user(Role.ADMIN), Permission.USERS_READ)).allowed
    decision = await authz.evaluate(_user(Role.USER), Permission.USERS_READ)
    assert not decision.allowed
    assert decision.reason.value == "insufficient_permission"


async def test_allow_grant_extends_baseline(_grants_backend):
    _grants_backend(
        rows=[
            {
                "resource": "users",
                "action": "read",
                "effect": "ALLOW",
                "conditions": None,
                "expires_at": None,
            }
        ]
    )
    assert (await authz.evaluate(_user(Role.USER), Permission.USERS_READ)).allowed


async def test_deny_grant_beats_baseline_and_allow(_grants_backend):
    _grants_backend(
        rows=[
            {
                "resource": "users",
                "action": "read",
                "effect": "DENY",
                "conditions": None,
                "expires_at": None,
            },
        ]
    )
    decision = await authz.evaluate(_user(Role.ADMIN), Permission.USERS_READ)
    assert not decision.allowed
    assert decision.reason.value == "permission_denied"


async def test_own_only_grant_needs_owner_match(_grants_backend):
    _grants_backend(
        rows=[
            {
                "resource": "jobs",
                "action": "read_all",
                "effect": "ALLOW",
                "conditions": {"own_only": True},
                "expires_at": None,
            }
        ]
    )
    user = _user(Role.USER)
    # route-level (no resource context): not allowed
    assert not (await authz.evaluate(user, Permission.JOBS_READ_ALL)).allowed
    # resource-level with a matching owner: allowed
    assert (await authz.evaluate(user, Permission.JOBS_READ_ALL, resource_owner_id="u1")).allowed
    # resource-level with someone else's resource: not allowed
    assert not (
        await authz.evaluate(user, Permission.JOBS_READ_ALL, resource_owner_id="u2")
    ).allowed


async def test_expired_grants_are_ignored(_grants_backend, monkeypatch):

    async def query_raw(sql, *params):
        assert "expires_at IS NULL OR expires_at > now()" in sql  # expiry filtered in SQL
        return []

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))
    assert not (await authz.evaluate(_user(Role.USER), Permission.USERS_READ)).allowed


async def test_backend_error_degrades_to_baseline_by_default(_grants_backend, caplog):
    _grants_backend(fail=True)
    assert (await authz.evaluate(_user(Role.ADMIN), Permission.USERS_READ)).allowed
    assert not (await authz.evaluate(_user(Role.USER), Permission.USERS_READ)).allowed


async def test_backend_error_denies_when_fail_closed(_grants_backend, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "authz_fail_closed", True)
    _grants_backend(fail=True)
    decision = await authz.evaluate(_user(Role.ADMIN), Permission.USERS_READ)
    assert not decision.allowed
    assert decision.reason.value == "policy_error"


async def test_allowed_requires_all_permissions(_grants_backend):
    assert (
        await authz.allowed(_user(Role.ADMIN), Permission.USERS_READ, Permission.AUDIT_READ)
    ).allowed
    decision = await authz.allowed(_user(Role.USER), Permission.USERS_READ, Permission.AUDIT_READ)
    assert not decision.allowed


async def test_read_scope_none_own_all(_grants_backend):
    user = _user(Role.USER)
    assert await authz.read_scope(user, Permission.AUDIT_READ) is None  # no baseline, no grant

    _grants_backend(
        rows=[
            {
                "resource": "audit",
                "action": "read",
                "effect": "ALLOW",
                "conditions": {"own_only": True},
                "expires_at": None,
            }
        ]
    )
    assert await authz.read_scope(user, Permission.AUDIT_READ) == "own"

    _grants_backend(
        rows=[
            {
                "resource": "audit",
                "action": "read",
                "effect": "ALLOW",
                "conditions": None,
                "expires_at": None,
            }
        ]
    )
    assert await authz.read_scope(user, Permission.AUDIT_READ) == "all"

    _grants_backend(
        rows=[
            {
                "resource": "audit",
                "action": "read",
                "effect": "DENY",
                "conditions": None,
                "expires_at": None,
            }
        ]
    )
    assert await authz.read_scope(user, Permission.AUDIT_READ) is None  # deny wins

    admin = _user(Role.ADMIN)
    _grants_backend(rows=[])
    assert await authz.read_scope(admin, Permission.AUDIT_READ) == "all"


async def test_grants_cached_per_user(monkeypatch, _grants_backend):
    calls: list = []

    async def query_raw(sql, *params):
        calls.append(params)
        return [
            {
                "resource": "users",
                "action": "read",
                "effect": "ALLOW",
                "conditions": None,
                "expires_at": None,
            }
        ]

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))
    user = _user(Role.USER)
    assert (await authz.evaluate(user, Permission.USERS_READ)).allowed
    assert (await authz.evaluate(user, Permission.USERS_READ)).allowed
    assert len(calls) == 1  # second evaluation was served from the per-user cache


async def test_grants_cache_invalidated_on_write(monkeypatch, _grants_backend):
    calls: list = []

    async def query_raw(sql, *params):
        calls.append(sql)
        return []

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))

    user = _user(Role.USER)
    assert not (await authz.evaluate(user, Permission.USERS_READ)).allowed
    await authz._load_grants.invalidate("u1")  # what the permissions service does after commit
    assert not (await authz.evaluate(user, Permission.USERS_READ)).allowed
    assert len(calls) == 2


async def test_require_permission_uses_grants(monkeypatch, audit_sink):
    """End-to-end PEP: a USER with an explicit grant passes; with a DENY they get 403 + audit."""
    from app.features.auth.deps import require_permission

    rows: list = []

    async def query_raw(sql, *params):
        return rows

    monkeypatch.setattr("app.core.authz.current_db", lambda: SimpleNamespace(query_raw=query_raw))
    checker = require_permission(Permission.USERS_READ)
    request = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/users")})
    user = _user(Role.USER)

    rows.append(
        {
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "expires_at": None,
        }
    )
    assert (await checker(user=user, request=request)) is user

    rows.clear()
    rows.append(
        {
            "resource": "users",
            "action": "read",
            "effect": "DENY",
            "conditions": None,
            "expires_at": None,
        }
    )
    from app.core.cache import cache as cache_facade

    await cache_facade.delete(
        cache_facade.key(
            __import__("app.core.constants", fromlist=["CacheNS"]).CacheNS.PERMISSIONS, "u1"
        )
    )
    with pytest.raises(ForbiddenError):
        await checker(user=user, request=request)
    denied = [e for e in audit_sink.entries if e["action"] == "access.denied"]
    assert denied and denied[-1]["metadata"]["reason"] == "permission_denied"
    assert Msg.FORBIDDEN  # 403 message key exists
