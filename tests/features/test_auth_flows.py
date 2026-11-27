"""Auth service: registration, one-time tokens, password reset, logout-all."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from prisma.models import User

from app.core.constants import Role, TokenPurpose
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.features.auth import service
from app.features.auth.repository import one_time_repo, refresh_repo
from app.features.auth.schemas import RegisterIn, ResetPasswordIn

_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


def _row(password="pw"):
    return User(
        id="u1",
        email="a@example.com",
        password_hash=hash_password(password),
        name="A",
        role=Role.USER,
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _noop(*a, **k):
    return None


# --- register ---------------------------------------------------------------


async def test_register_creates_user_and_audits(monkeypatch, audit_sink):
    async def none(email):
        return None

    async def create(data):
        return _row()

    created_refresh: list[dict] = []

    async def refresh_create(data):
        created_refresh.append(data)
        return SimpleNamespace(**data)

    monkeypatch.setattr(service.users_repo, "find_by_email", none)
    monkeypatch.setattr(service.users_repo, "create", create)
    monkeypatch.setattr(refresh_repo, "create", refresh_create)
    monkeypatch.setattr(service, "enqueue", _noop)

    token = await service.register(
        RegisterIn(email="A@example.com", password="password123", name="A")
    )
    assert token.access_token and token.refresh_token
    assert created_refresh, "refresh token stored"
    assert any(e["action"] == "auth.register" for e in audit_sink.entries)


async def test_register_duplicate_email_conflict(monkeypatch):
    from app.core.exceptions import ConflictError

    async def found(email):
        return _row()

    monkeypatch.setattr(service.users_repo, "find_by_email", found)
    with pytest.raises(ConflictError):
        await service.register(RegisterIn(email="a@example.com", password="password123", name="A"))


# --- verify email -----------------------------------------------------------


async def test_verify_email_marks_verified(monkeypatch, audit_sink):
    record = SimpleNamespace(
        id="ot1", user_id="u1", purpose=TokenPurpose.VERIFY_EMAIL, expires_at=_FUTURE
    )
    captured: dict = {}

    async def find(h):
        return record

    async def consume(tid):
        return True

    async def update(uid, data):
        captured.update(data)
        return None

    monkeypatch.setattr(one_time_repo, "find_by_hash", find)
    monkeypatch.setattr(one_time_repo, "consume", consume)
    monkeypatch.setattr(service.users_repo, "update", update)

    await service.verify_email("raw")
    assert "email_verified_at" in captured
    assert any(e["action"] == "auth.email_verify" for e in audit_sink.entries)


async def test_verify_email_invalid_token(monkeypatch):
    async def find(h):
        return None

    monkeypatch.setattr(one_time_repo, "find_by_hash", find)
    with pytest.raises(UnauthorizedError):
        await service.verify_email("raw")


async def test_verify_email_already_consumed(monkeypatch):
    record = SimpleNamespace(
        id="ot1", user_id="u1", purpose=TokenPurpose.VERIFY_EMAIL, expires_at=_FUTURE
    )

    async def find(h):
        return record

    async def consume(tid):
        return False  # already used / raced

    monkeypatch.setattr(one_time_repo, "find_by_hash", find)
    monkeypatch.setattr(one_time_repo, "consume", consume)
    with pytest.raises(UnauthorizedError):
        await service.verify_email("raw")


# --- reset password ---------------------------------------------------------


async def test_reset_password_rotates_and_revokes(monkeypatch, audit_sink):
    record = SimpleNamespace(
        id="ot1", user_id="u1", purpose=TokenPurpose.RESET_PASSWORD, expires_at=_FUTURE
    )
    captured: dict = {}
    revoked: list[str] = []

    async def find_token(h):
        return record

    async def consume(tid):
        return True

    async def find_user(uid):
        return _row()

    async def update(uid, data):
        captured.update(data)
        return None

    async def revoke_all(uid):
        revoked.append(uid)
        return 1

    monkeypatch.setattr(one_time_repo, "find_by_hash", find_token)
    monkeypatch.setattr(one_time_repo, "consume", consume)
    monkeypatch.setattr("app.features.users.service.find", find_user)
    monkeypatch.setattr(service.users_repo, "update", update)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", revoke_all)
    monkeypatch.setattr(service, "after_commit", _noop)

    await service.reset_password(ResetPasswordIn(token="raw", new_password="new-password-123"))
    assert captured["token_version"] == 1
    assert revoked == ["u1"]
    assert any(e["action"] == "auth.password_reset" for e in audit_sink.entries)


async def test_reset_password_wrong_purpose(monkeypatch):
    record = SimpleNamespace(
        id="ot1", user_id="u1", purpose=TokenPurpose.VERIFY_EMAIL, expires_at=_FUTURE
    )

    async def find_token(h):
        return record

    monkeypatch.setattr(one_time_repo, "find_by_hash", find_token)
    with pytest.raises(UnauthorizedError):
        await service.reset_password(ResetPasswordIn(token="raw", new_password="new-password-123"))


# --- forgot password --------------------------------------------------------


async def test_forgot_password_known_user_enqueues(monkeypatch, audit_sink):
    enqueued: list = []

    async def found(email):
        return _row()

    async def enqueue(*a, **k):
        enqueued.append((a, k))

    monkeypatch.setattr(service.users_repo, "find_by_email", found)
    monkeypatch.setattr(service, "enqueue", enqueue)

    await service.forgot_password("a@example.com")
    assert enqueued, "reset email job enqueued"
    assert any(e["action"] == "auth.password_reset_request" for e in audit_sink.entries)


async def test_forgot_password_unknown_user_silent(monkeypatch, audit_sink):
    async def none(email):
        return None

    async def enqueue(*a, **k):
        raise AssertionError("must not enqueue for unknown user")

    monkeypatch.setattr(service.users_repo, "find_by_email", none)
    monkeypatch.setattr(service, "enqueue", enqueue)
    await service.forgot_password("nobody@example.com")  # no error, no enumeration
    assert not any(e["action"] == "auth.password_reset_request" for e in audit_sink.entries)


# --- logout all -------------------------------------------------------------


async def test_logout_all_bumps_version_and_revokes(monkeypatch, audit_sink):
    user = _row()
    updates: list = []
    revoked: list[str] = []

    async def update(uid, data):
        updates.append((uid, data))
        return None

    async def revoke_all(uid):
        revoked.append(uid)
        return 1

    monkeypatch.setattr(service.users_repo, "update", update)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", revoke_all)
    monkeypatch.setattr(service, "after_commit", _noop)

    await service.logout_all(user)
    assert updates == [("u1", {"token_version": 1})]
    assert revoked == ["u1"]
    assert any(e["action"] == "auth.logout_all" for e in audit_sink.entries)


# --- resend verification ----------------------------------------------------


async def test_resend_verification_enqueues(monkeypatch):
    enqueued: list = []

    async def enqueue(*a, **k):
        enqueued.append((a, k))

    monkeypatch.setattr(service, "enqueue", enqueue)
    await service.resend_verification(_row())
    assert enqueued


async def test_resend_verification_rate_limited(monkeypatch):
    from app.core.exceptions import RateLimitedError

    async def enqueue(*a, **k):
        return None

    monkeypatch.setattr(service, "enqueue", enqueue)
    user = _row()
    for _ in range(3):  # RESEND_USER policy = 3/hour
        await service.resend_verification(user)
    with pytest.raises(RateLimitedError):
        await service.resend_verification(user)
