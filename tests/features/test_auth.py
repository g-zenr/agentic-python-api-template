"""Auth tests: audit on login/denied, identical client error, token_version, permissions."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from prisma.models import User

from app.core.constants import Permission, Role
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, hash_password
from app.features.auth import service
from app.features.auth.deps import get_current_user, require_permission
from app.features.auth.repository import refresh_repo
from app.features.auth.schemas import LoginIn
from app.features.users.repository import users_repo


def _row(password="pw", token_version=0):
    return User(
        id="u1",
        email="a@example.com",
        password_hash=hash_password(password),
        name="A",
        role=Role.USER,
        locale="en",
        is_active=True,
        token_version=token_version,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class FakeRefresh:
    def __init__(self):
        self.rows = {}

    async def find_by_hash(self, h):
        return self.rows.get(h)

    async def create(self, data):
        row = SimpleNamespace(**data)
        self.rows[data["token_hash"]] = row
        return row

    async def revoke_if_active(self, tid):
        return True

    async def revoke_family(self, fid):
        return 1

    async def revoke_all_for_user(self, uid):
        return 1


@pytest.fixture
def refresh(monkeypatch):
    fake = FakeRefresh()
    monkeypatch.setattr(refresh_repo, "find_by_hash", fake.find_by_hash)
    monkeypatch.setattr(refresh_repo, "create", fake.create)
    monkeypatch.setattr(refresh_repo, "revoke_if_active", fake.revoke_if_active)
    monkeypatch.setattr(refresh_repo, "revoke_family", fake.revoke_family)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", fake.revoke_all_for_user)
    return fake


async def test_failed_login_unknown_email(monkeypatch, audit_sink):
    async def none(email):
        return None

    monkeypatch.setattr(users_repo, "find_by_email", none)
    with pytest.raises(UnauthorizedError):
        await service.login(LoginIn(email="x@example.com", password="pw"))
    assert audit_sink.entries[0]["action"] == "auth.login_failed"
    assert audit_sink.entries[0]["metadata"]["reason"] == "unknown_email"
    assert "email" not in audit_sink.entries[0]["metadata"]


async def test_failed_login_bad_password(monkeypatch, audit_sink):
    async def found(email):
        return _row()

    monkeypatch.setattr(users_repo, "find_by_email", found)
    with pytest.raises(UnauthorizedError):
        await service.login(LoginIn(email="a@example.com", password="wrong"))
    assert audit_sink.entries[0]["metadata"]["reason"] == "bad_password"


async def test_successful_login(monkeypatch, audit_sink, refresh):
    async def found(email):
        return _row()

    monkeypatch.setattr(users_repo, "find_by_email", found)
    token = await service.login(LoginIn(email="a@example.com", password="pw"))
    assert token.access_token and token.refresh_token
    assert audit_sink.entries[0]["action"] == "auth.login"


async def test_token_version_mismatch_rejected(monkeypatch):
    token = create_access_token("u1", 0)

    async def find(uid):
        return _row(token_version=1)

    monkeypatch.setattr("app.features.users.service.find", find)
    creds = SimpleNamespace(credentials=token)
    with pytest.raises(UnauthorizedError):
        await get_current_user(creds)


async def test_require_permission_denied(audit_sink):
    checker = require_permission(Permission.USERS_READ)
    request = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/users")})
    with pytest.raises(ForbiddenError):
        await checker(user=SimpleNamespace(id="u1", role=Role.USER), request=request)
    assert audit_sink.entries[0]["action"] == "access.denied"
    assert audit_sink.entries[0]["metadata"]["reason"] == "insufficient_permission"
