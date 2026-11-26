"""Idempotency: request hashing and replay/mismatch/in-progress via a fake record store."""

import pytest
from prisma.errors import UniqueViolationError

from app.core.exceptions import ConflictError
from app.shared.helpers import idempotency as idem


class FakeRecord:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeDelegate:
    def __init__(self):
        self.rows: dict[tuple, FakeRecord] = {}
        self._n = 0

    async def create(self, data):
        key = (data["scope"], data["key"])
        if key in self.rows:
            raise UniqueViolationError({})
        self._n += 1
        rec = FakeRecord(
            id=str(self._n), status_code=None, response=None, request_hash=data["request_hash"]
        )
        self.rows[key] = rec
        return rec

    async def find_first(self, where):
        if "scope" in where:
            return self.rows.get((where["scope"], where["key"]))
        for rec in self.rows.values():
            if rec.id == where["id"]:
                return rec
        return None

    async def update(self, where, data):
        rec = await self.find_first(where)
        rec.__dict__.update(data)
        return rec

    async def delete(self, where):
        rec = await self.find_first(where)
        for k, v in list(self.rows.items()):
            if v is rec:
                del self.rows[k]


class FakeClient:
    def __init__(self):
        self.idempotencyrecord = FakeDelegate()


@pytest.fixture
def fake_db(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(idem, "current_db", lambda: client)
    return client


async def test_run_once_executes_and_stores(fake_db):
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        return 201, {"ok": 1}

    status, data, replay = await idem.run_once("u1", "k1", {"a": 1}, fn)
    assert (status, data, replay) == (201, {"ok": 1}, False)
    status, data, replay = await idem.run_once("u1", "k1", {"a": 1}, fn)
    assert replay is True and calls == 1


async def test_mismatch_raises(fake_db):
    async def fn():
        return 201, {}

    await idem.run_once("u1", "k1", {"a": 1}, fn)
    with pytest.raises(ConflictError):
        await idem.run_once("u1", "k1", {"a": 2}, fn)


async def test_in_progress_raises(fake_db):
    async def fn():
        return 201, {}

    await idem.run_once("u1", "k1", {"a": 1}, fn)
    fake_db.idempotencyrecord.rows[("u1", "k1")].status_code = None
    with pytest.raises(ConflictError):
        await idem.run_once("u1", "k1", {"a": 1}, fn)
