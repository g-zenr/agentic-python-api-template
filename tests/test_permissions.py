"""RBAC: role→permission matrix and require_permission denial auditing."""

from types import SimpleNamespace

import pytest

from app.core.constants import Permission, Role
from app.core.exceptions import ForbiddenError
from app.core.permissions import has_permission
from app.features.auth.deps import require_permission


def test_user_has_no_permissions():
    assert not has_permission(Role.USER, Permission.USERS_READ)
    assert not has_permission(Role.USER, Permission.AUDIT_READ)


def test_admin_has_all_permissions():
    for perm in Permission:
        assert has_permission(Role.ADMIN, perm)


async def test_require_permission_denies_and_audits(audit_sink):
    checker = require_permission(Permission.AUDIT_READ)
    request = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/audit")})
    with pytest.raises(ForbiddenError):
        await checker(user=SimpleNamespace(id="u1", role=Role.USER), request=request)
    assert audit_sink.entries[0]["action"] == "access.denied"
    assert audit_sink.entries[0]["metadata"]["reason"] == "insufficient_permission"
    assert "audit:read" in audit_sink.entries[0]["metadata"]["required"]


async def test_require_permission_allows(audit_sink):
    checker = require_permission(Permission.AUDIT_READ)
    request = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/audit")})
    user = SimpleNamespace(id="admin", role=Role.ADMIN)
    assert await checker(user=user, request=request) is user
    assert audit_sink.entries == []
