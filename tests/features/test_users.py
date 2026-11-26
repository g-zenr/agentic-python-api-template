"""Users feature tests: cached find, invalidation on update, and USER_UPDATE audit."""

from datetime import datetime

from prisma.models import User

from app.core.constants import Role
from app.features.users import service
from app.features.users.repository import users_repo
from app.features.users.schemas import UserUpdate


def _row(id="u1", name="A"):
    return User(
        id=id,
        email="a@example.com",
        password_hash="x",
        name=name,
        role=Role.USER,
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


async def test_find_is_cached(monkeypatch):
    calls = 0

    async def fake_get(id):
        nonlocal calls
        calls += 1
        return _row(id)

    monkeypatch.setattr(users_repo, "get", fake_get)
    await service.find("u1")
    await service.find("u1")
    assert calls == 1


async def test_update_invalidates_and_audits(monkeypatch, audit_sink):
    calls = 0

    async def fake_get(id):
        nonlocal calls
        calls += 1
        return _row(id)

    async def fake_update(id, data):
        return _row(id, name=data.get("name", "A"))

    monkeypatch.setattr(users_repo, "get", fake_get)
    monkeypatch.setattr(users_repo, "update", fake_update)

    await service.find("u1")  # populate cache (calls=1)
    await service.update_me(_row("u1"), UserUpdate(name="B"))
    await service.find("u1")  # cache was invalidated -> calls=2
    assert calls == 2
    assert audit_sink.entries[0]["action"] == "user.update"
    assert audit_sink.entries[0]["changes"]["name"] == {"from": "A", "to": "B"}
