"""Account lifecycle: create_admin (new/promote/refuse) and delete_me (anonymize + tokens)."""

from datetime import datetime

import pytest
from prisma.models import User

from app.core.constants import Role
from app.core.discovery import feature_modules
from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.features.auth.repository import refresh_repo
from app.features.users import service
from app.features.users.repository import users_repo

feature_modules("jobs")


def _row():
    return User(
        id="u1",
        email="a@example.com",
        password_hash=hash_password("pw"),
        name="A",
        role=Role.USER,
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


async def test_create_admin_new(monkeypatch, audit_sink):
    created = {}

    async def none(email):
        return None

    async def create(data):
        created.update(data)
        return type("U", (), {"id": "new"})()

    monkeypatch.setattr(users_repo, "find_by_email", none)
    monkeypatch.setattr(users_repo, "create", create)
    await service.create_admin("admin@example.com", "supersecret", promote=False)
    assert created["role"] == Role.ADMIN.value
    assert audit_sink.entries[0]["action"] == "admin.bootstrap"
    assert audit_sink.entries[0]["actor_type"] == "system"


async def test_create_admin_refuses_without_promote(monkeypatch, audit_sink):
    async def found(email):
        return _row()

    monkeypatch.setattr(users_repo, "find_by_email", found)
    with pytest.raises(ConflictError):
        await service.create_admin("a@example.com", "supersecret", promote=False)


async def test_create_admin_password_length_typed_error(monkeypatch, audit_sink):
    from app.core.exceptions import BadInputError

    async def none(email):
        return None

    monkeypatch.setattr(users_repo, "find_by_email", none)
    with pytest.raises(BadInputError):
        await service.create_admin("a@example.com", "x", promote=False)


async def test_delete_me_anonymizes(monkeypatch, audit_sink, fake_store):
    updated = {}

    async def upd(id, data):
        updated.update(data)
        return _row()

    async def revoke(uid):
        return 1

    monkeypatch.setattr(users_repo, "update", upd)
    monkeypatch.setattr(refresh_repo, "revoke_all_for_user", revoke)
    await service.delete_me(_row(), "pw")
    assert updated["is_active"] is False
    assert updated["email"].startswith("deleted-")
    assert updated["token_version"] == 1
    assert any(e["action"] == "user.delete" for e in audit_sink.entries)
