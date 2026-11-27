"""UoW: the REAL transaction path (fake connected client), nesting, and after-commit timing."""

import logging
from contextlib import asynccontextmanager

import pytest

from app.core import uow
from app.core.uow import after_commit, current_db, in_transaction, transaction


class FakeTx:
    def __init__(self):
        self.committed = False


class FakeDb:
    """Stands in for the Prisma client with a working tx() (so the real path runs)."""

    def __init__(self):
        self.connected = True
        self.tx_calls = 0

    def is_connected(self) -> bool:
        return self.connected

    @asynccontextmanager
    async def tx(self, timeout=None):  # noqa: ASYNC109 - matches Prisma's db.tx(timeout=...)
        self.tx_calls += 1
        tx = FakeTx()
        yield tx
        tx.committed = True


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(uow, "db", db)
    return db


async def test_real_transaction_commits_and_joins(fake_db):
    assert in_transaction() is False
    async with transaction():
        assert in_transaction() is True
        assert current_db() is not None  # the tx client (FakeTx), not the shared client
        inner_seen = in_transaction()
        async with transaction():  # nested: joins the OUTER tx, no second db.tx()
            pass
        assert inner_seen is True
    assert fake_db.tx_calls == 1  # nested join did not open a second transaction
    assert in_transaction() is False


async def test_after_commit_runs_only_after_commit(fake_db):
    order: list[str] = []

    async def cb():
        order.append("committed")

    with pytest.raises(RuntimeError):
        async with transaction():
            await after_commit(cb)
            raise RuntimeError("rollback")
    assert order == []  # discarded on error

    async with transaction():
        await after_commit(cb)
        order.append("inside")
    assert order == ["inside", "committed"]  # ran after the tx body, post-commit


async def test_after_commit_without_tx_runs_immediately(fake_db, monkeypatch):
    fake_db.connected = False  # unit path: no real transaction, callbacks run inline
    ran: list[bool] = []

    async def cb():
        ran.append(True)

    await after_commit(cb)
    assert ran == [True]


async def test_after_commit_failure_is_swallowed(fake_db, caplog):
    async def boom():
        raise RuntimeError("callback failed")

    with caplog.at_level(logging.ERROR, logger="app.core.uow"):
        async with transaction():
            await after_commit(boom)
    assert any("after_commit callback failed" in r.message for r in caplog.records)
