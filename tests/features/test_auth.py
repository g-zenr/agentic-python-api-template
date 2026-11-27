"""Auth tests: audit on login/denied, identical client error, token_version, permissions."""

from datetime import UTC, datetime
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

    monkeypatch.setattr("app.features.auth.deps.users_repo.get", find)
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


# --- refresh-token rotation + reuse detection -------------------------------


class FakeRefreshFull:
    def __init__(self, record, revoke_if_active=True):
        self.record = record
        self._revoke_if_active = revoke_if_active
        self.created: list[dict] = []
        self.marked: list[tuple] = []
        self.revoked_family: list[str] = []
        self.revoked_all: list[str] = []

    async def find_by_hash(self, h):
        return self.record

    async def create(self, data):
        self.created.append(data)
        return SimpleNamespace(**data)

    async def revoke_if_active(self, tid):
        return self._revoke_if_active

    async def revoke_family(self, fid):
        self.revoked_family.append(fid)
        return 1

    async def revoke_all_for_user(self, uid):
        self.revoked_all.append(uid)
        return 1

    async def mark_replaced(self, tid, replaced_by):
        self.marked.append((tid, replaced_by))


def _refresh_record(revoked_at=None):
    return SimpleNamespace(
        id="rt1",
        user_id="u1",
        family_id="fam1",
        token_hash="oldhash",
        expires_at=datetime(2999, 1, 1, tzinfo=UTC),
        revoked_at=revoked_at,
    )


def _wire_refresh(monkeypatch, fake):
    monkeypatch.setattr(refresh_repo, "find_by_hash", fake.find_by_hash)
    monkeypatch.setattr(refresh_repo, "create", fake.create)
    monkeypatch.setattr(refresh_repo, "revoke_if_active", fake.revoke_if_active)
    monkeypatch.setattr(refresh_repo, "revoke_family", fake.revoke_family)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", fake.revoke_all_for_user)
    monkeypatch.setattr(refresh_repo, "mark_replaced", fake.mark_replaced)

    # no cached wrapper: patch the underlying users service find
    async def _find(uid):
        return _row()

    monkeypatch.setattr("app.features.users.service.find", _find)


async def test_refresh_rotation_links_replacement(monkeypatch, audit_sink):
    from app.core.security import hash_token

    fake = FakeRefreshFull(_refresh_record())
    _wire_refresh(monkeypatch, fake)
    token = await service.refresh("raw-old")

    assert token.access_token and token.refresh_token
    assert fake.created, "a new refresh token row must be stored"
    new_hash = fake.created[0]["token_hash"]
    # C2: replacement links the OLD row (rt1) -> NEW hash, NOT itself
    assert fake.marked == [("rt1", new_hash)]
    assert new_hash != "oldhash"
    assert fake.marked[0][1] != fake.record.token_hash
    # returned raw token hashes to the stored new hash
    assert hash_token(token.refresh_token) == new_hash
    assert any(e["action"] == "auth.refresh" for e in audit_sink.entries)


async def test_refresh_reuse_of_revoked_token_revokes_family(monkeypatch, audit_sink):
    fake = FakeRefreshFull(_refresh_record(revoked_at=datetime(2026, 1, 1, tzinfo=UTC)))
    _wire_refresh(monkeypatch, fake)
    with pytest.raises(UnauthorizedError):
        await service.refresh("raw-old")
    assert fake.revoked_family == ["fam1"]
    assert fake.created == []  # no new token on reuse
    assert any(e["action"] == "auth.refresh_reuse_detected" for e in audit_sink.entries)


async def test_refresh_lost_race_treated_as_reuse(monkeypatch, audit_sink):
    fake = FakeRefreshFull(_refresh_record(), revoke_if_active=False)
    _wire_refresh(monkeypatch, fake)
    with pytest.raises(UnauthorizedError):
        await service.refresh("raw-old")
    assert fake.revoked_family == ["fam1"]
    assert fake.marked == []  # no replacement linked
    assert any(e["action"] == "auth.refresh_reuse_detected" for e in audit_sink.entries)


async def test_refresh_unknown_token_rejected(monkeypatch):
    async def none(h):
        return None

    monkeypatch.setattr(refresh_repo, "find_by_hash", none)
    with pytest.raises(UnauthorizedError):
        await service.refresh("nope")


async def test_refresh_inactive_user_rejected(monkeypatch):
    fake = FakeRefreshFull(_refresh_record())
    _wire_refresh(monkeypatch, fake)
    monkeypatch.setattr("app.features.users.service.find", _inactive_user)
    with pytest.raises(UnauthorizedError):
        await service.refresh("raw-old")


async def _inactive_user(uid):
    u = _row()
    return User(
        id=u.id,
        email=u.email,
        password_hash=u.password_hash,
        name=u.name,
        role=u.role,
        locale=u.locale,
        is_active=False,
        token_version=u.token_version,
        email_verified_at=u.email_verified_at,
        deleted_at=u.deleted_at,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


# --- logout -----------------------------------------------------------------


async def test_logout_revokes_family(monkeypatch, audit_sink):
    fake = FakeRefreshFull(_refresh_record())
    monkeypatch.setattr(refresh_repo, "find_by_hash", fake.find_by_hash)
    monkeypatch.setattr(refresh_repo, "revoke_family", fake.revoke_family)
    await service.logout("raw-old")
    assert fake.revoked_family == ["fam1"]
    assert any(e["action"] == "auth.logout" for e in audit_sink.entries)


async def test_logout_unknown_token_still_audits(monkeypatch, audit_sink):
    async def none(h):
        return None

    monkeypatch.setattr(refresh_repo, "find_by_hash", none)
    await service.logout("nope")
    assert any(e["action"] == "auth.logout" for e in audit_sink.entries)


# --- password change / reset / verify ---------------------------------------


async def _noop(*a, **k):
    return None


async def test_change_password_revokes_and_bumps_version(monkeypatch, audit_sink):
    from app.features.auth.schemas import ChangePasswordIn

    user = _row(password="pw")
    captured: dict = {}

    async def _update(uid, data):
        captured.update(data)
        return User(
            id=user.id,
            email=user.email,
            password_hash=data["password_hash"],
            name=user.name,
            role=user.role,
            locale=user.locale,
            is_active=True,
            token_version=data["token_version"],
            email_verified_at=None,
            deleted_at=None,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    revoked: list[str] = []

    async def _revoke_all(uid):
        revoked.append(uid)
        return 1

    monkeypatch.setattr(service.users_repo, "update", _update)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", _revoke_all)
    monkeypatch.setattr(service, "after_commit", _noop)
    await service.change_password(
        user, ChangePasswordIn(current_password="pw", new_password="new-password-123")
    )
    assert revoked == ["u1"]
    assert captured["token_version"] == 1  # bumped
    assert any(e["action"] == "auth.password_change" for e in audit_sink.entries)


async def test_change_password_wrong_current_rejected(monkeypatch):
    from app.features.auth.schemas import ChangePasswordIn

    user = _row(password="pw")
    with pytest.raises(UnauthorizedError):
        await service.change_password(
            user, ChangePasswordIn(current_password="wrong", new_password="new-password-123")
        )
