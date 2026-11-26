"""Unit of work: transaction fallback, after_commit ordering, nesting, current_db."""

from app.core import uow
from app.core.database import db


def test_current_db_defaults_to_shared_client():
    assert uow.current_db() is db
    assert uow.in_transaction() is False


async def test_transaction_without_db_yields():
    async with uow.transaction():
        assert uow.in_transaction() is False  # no DB -> no real tx


async def test_after_commit_runs_immediately_without_tx():
    ran = []
    await uow.after_commit(lambda: ran.append(1) or _noop())
    assert ran == [1]


async def _noop():
    return None


async def test_nested_transaction_joins():
    async with uow.transaction(), uow.transaction():  # nested joins, no error
        pass
