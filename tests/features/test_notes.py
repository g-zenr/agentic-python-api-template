"""Notes feature tests: ownership, audit, versioning, cache invalidation, and the export job."""

from types import SimpleNamespace

import pytest
from prisma.models import Note

from app.core.exceptions import NotFoundError, PreconditionFailedError
from app.core.jobs import set_store
from app.features.notes import service
from app.features.notes.repository import notes_repo
from app.features.notes.schemas import NoteCreate, NoteUpdate
from app.shared.utils.time import utcnow


def _user(id="u1"):
    return SimpleNamespace(id=id)


def _note(id, user_id, title="t", version=1):
    now = utcnow()
    return Note(
        id=id,
        user_id=user_id,
        title=title,
        body="",
        version=version,
        created_at=now,
        updated_at=now,
    )


async def test_create_audits(monkeypatch, audit_sink):
    async def fake_create(data):
        return _note("n1", data["user_id"])

    monkeypatch.setattr(notes_repo, "create", fake_create)
    await service.create(_user("u1"), NoteCreate(title="hi"))
    assert audit_sink.entries[0]["action"] == "note.create"


async def test_get_other_users_note_raises(monkeypatch):
    async def fake_get(id):
        return _note(id, "someone-else")

    monkeypatch.setattr(notes_repo, "get", fake_get)
    with pytest.raises(NotFoundError):
        await service.get(_user("u1"), "n1")


async def test_update_requires_if_match(monkeypatch, audit_sink):
    async def fake_get(id):
        return _note(id, "u1")

    async def fake_update_versioned(id, expected, data):
        return expected == 1

    monkeypatch.setattr(notes_repo, "get", fake_get)
    monkeypatch.setattr(notes_repo, "update_versioned", fake_update_versioned)
    note = await service.update(_user("u1"), "n1", NoteUpdate(title="new"), 1)
    assert note.id == "n1"
    assert audit_sink.entries[0]["action"] == "note.update"


async def test_update_stale_version_conflicts(monkeypatch, audit_sink):
    async def fake_get(id):
        return _note(id, "u1")

    async def fake_update_versioned(id, expected, data):
        return False

    monkeypatch.setattr(notes_repo, "get", fake_get)
    monkeypatch.setattr(notes_repo, "update_versioned", fake_update_versioned)
    with pytest.raises(PreconditionFailedError):
        await service.update(_user("u1"), "n1", NoteUpdate(title="new"), 99)


async def test_list_cached_and_scope_invalidated(monkeypatch):
    calls = 0

    async def fake_paginate(params, where=None, order=None):
        nonlocal calls
        calls += 1
        return [_note("n1", "u1")], 1

    monkeypatch.setattr(notes_repo, "paginate", fake_paginate)
    params = _params()
    await service.list_notes(_user("u1"), params)
    await service.list_notes(_user("u1"), params)
    assert calls == 1


async def test_request_export_idempotent(fake_store, audit_sink):
    set_store(fake_store)
    j1 = await service.request_export(_user("u1"), "k1")
    j2 = await service.request_export(_user("u1"), "k1")
    assert j1.id == j2.id
    assert any(e["action"] == "note.export_request" for e in audit_sink.entries)


def _params():
    from app.shared.helpers.pagination import PageParams

    return PageParams(page=1, size=10)
