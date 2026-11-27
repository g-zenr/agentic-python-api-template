"""Unit of work: one DB transaction per mutation. Repositories join it automatically."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import timedelta
from typing import Any

from app.core.config import settings
from app.core.database import db

log = logging.getLogger(__name__)

_tx: ContextVar[Any | None] = ContextVar("tx", default=None)
_after: ContextVar[list[Callable[[], Awaitable[None]]] | None] = ContextVar("after", default=None)


def current_db() -> Any:
    """The active transaction client, else the shared client."""
    return _tx.get() or db


def in_transaction() -> bool:
    return _tx.get() is not None


@asynccontextmanager
async def transaction() -> AsyncIterator[None]:
    if in_transaction():  # nested: join the outer transaction
        yield
        return
    if not db.is_connected():  # unit tests / no DB: run without a real transaction
        yield
        return
    callbacks: list[Callable[[], Awaitable[None]]] = []
    async with db.tx(timeout=timedelta(milliseconds=settings.db_tx_timeout_ms)) as tx:
        t1, t2 = _tx.set(tx), _after.set(callbacks)
        try:
            yield
        finally:
            _tx.reset(t1)
            _after.reset(t2)
    for cb in callbacks:  # reached only after a successful commit; an exception discards them
        try:
            await cb()
        except Exception:
            log.exception("after_commit callback failed")


async def after_commit(cb: Callable[[], Awaitable[None]]) -> None:
    callbacks = _after.get()
    if callbacks is None:
        await cb()
    else:
        callbacks.append(cb)
