"""PrismaJobStore: SQL/query construction verified against a fake client (no database)."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.jobs.store import PrismaJobStore
from app.core.messages import Msg
from app.shared.helpers.pagination import PageParams
from app.shared.utils.time import utcnow

NOW = utcnow()


def _row(job_id="j1", **over):
    base = {
        "id": job_id,
        "type": "notes.export",
        "status": "QUEUED",
        "payload": '{"a": 1}',  # JSON string column: exercises the decode path
        "result": None,
        "error": None,
        "progress": 0,
        "attempts": 0,
        "max_attempts": 3,
        "user_id": "u1",
        "request_id": None,
        "cancel_requested": False,
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": None,
        "finished_at": None,
    }
    base.update(over)
    return base


class FakeClient:
    """Stands in for the Prisma client: records raw SQL, returns canned rows."""

    def __init__(self, query_rows=None, execute_count=1):
        self.query_rows = query_rows if query_rows is not None else []
        self.execute_count = execute_count
        self.queries: list[tuple] = []

    async def query_raw(self, sql, *params):
        self.queries.append((sql, params))
        return self.query_rows

    async def execute_raw(self, sql, *params):
        self.queries.append((sql, params))
        return self.execute_count


class FakeD:
    def __init__(self):
        self.updates: list = []
        self.row: SimpleNamespace | None = SimpleNamespace(cancel_requested=False)
        self.total = 0
        self.find_many_rows: list = []
        self.update_many_result = 1
        self.delete_many_result = 0

    async def update(self, where, data):
        self.updates.append((where, data))
        return None

    async def find_unique(self, where):
        return self.row

    async def find_many(self, **kw):
        return self.find_many_rows

    async def count(self, where):
        return self.total

    async def update_many(self, where, data):
        self.updates.append((where, data))
        return self.update_many_result

    async def delete_many(self, where):
        self.updates.append(("delete_many", where))
        return self.delete_many_result


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def store(client, monkeypatch):
    monkeypatch.setattr("app.core.jobs.store.current_db", lambda: client)
    return PrismaJobStore(delegate=FakeD())


def _kwargs(**over):
    base = dict(
        type="notes.export",
        payload={"a": 1},
        user_id="u1",
        request_id=None,
        max_attempts=3,
        run_at=NOW,
        dedupe_key=None,
        priority=0,
    )
    base.update(over)
    return base


async def test_enqueue_inserts_and_returns_new(store, client):
    client.query_rows = [_row()]
    job, created = await store.enqueue(**_kwargs())
    assert created is True
    assert job.id == "j1"
    assert job.payload == {"a": 1}  # decoded from the JSON string column
    sql, params = client.queries[0]
    assert "INSERT INTO jobs" in sql and "ON CONFLICT (dedupe_key)" in sql
    assert params[0] == "notes.export"


async def test_enqueue_dedupe_returns_existing(store, client):
    client.query_rows = []  # INSERT ... DO NOTHING RETURNING => no rows
    client.query_rows_second = [_row("j9")]

    async def query_raw(sql, *params):
        client.queries.append((sql, params))
        if "SELECT * FROM jobs WHERE dedupe_key" in sql:
            return [_row("j9")]
        return []

    client.query_raw = query_raw
    job, created = await store.enqueue(**_kwargs(dedupe_key="dk"))
    assert created is False
    assert job.id == "j9"


async def test_claim_guards_and_sql(store, client):
    assert await store.claim("w1", [], 5) == []
    assert await store.claim("w1", ["notes.export"], 0) == []
    client.query_rows = [_row(), _row("j2")]
    jobs = await store.claim("w1", ["notes.export", "account.erase"], 2)
    assert [j.id for j in jobs] == ["j1", "j2"]
    sql, params = client.queries[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "$2, $3" in sql  # one placeholder per type
    assert params == ("w1", "notes.export", "account.erase", 2)  # values BOUND, not inlined


async def test_lifecycle_updates(store):
    d = store._delegate
    await store.heartbeat("j1")
    assert d.updates[-1][1] == {"heartbeat_at": d.updates[-1][1]["heartbeat_at"]}
    await store.set_progress("j1", 50)
    assert d.updates[-1][1] == {"progress": 50}

    d.row = SimpleNamespace(cancel_requested=True)
    assert await store.is_cancel_requested("j1") is True
    d.row = SimpleNamespace(cancel_requested=False)
    assert await store.is_cancel_requested("j1") is False
    d.row = None
    assert await store.is_cancel_requested("j1") is False

    await store.succeed("j1", {"x": 1})
    assert d.updates[-1][1]["status"] == "SUCCEEDED"

    await store.fail("j1", Msg.INTERNAL_ERROR, retry_at=NOW + timedelta(seconds=5))
    assert d.updates[-1][1]["status"] == "QUEUED"  # retry => back to the queue

    await store.fail("j1", Msg.INTERNAL_ERROR, retry_at=None)
    assert d.updates[-1][1]["status"] == "FAILED"

    await store.cancelled("j1")
    assert d.updates[-1][1]["status"] == "CANCELLED"


async def test_reap_stale_uses_raw_sql(store, client):
    client.execute_count = 3
    assert await store.reap_stale(120) == 3
    sql, params = client.queries[-1]
    assert "heartbeat_at < now()" in sql and params == (120, Msg.INTERNAL_ERROR.value)


async def test_get_and_list_for_user(store):
    d = store._delegate
    d.row = _row("j1")
    job = await store.get("j1")
    assert job is not None and job.id == "j1"
    d.row = None
    assert await store.get("nope") is None

    d.find_many_rows = [_row("j1")]
    d.total = 7
    items, total = await store.list_for_user("u1", PageParams(page=1, size=10), None)
    assert total == 7 and [i.id for i in items] == ["j1"]


async def test_list_for_user_applies_status_filter(store):
    d = store._delegate
    d.find_many_rows = []
    d.total = 0

    seen: dict = {}

    async def find_many(*, where, skip, take, order):
        seen["where"] = where
        return []

    d.find_many = find_many
    from app.core.constants import JobStatus

    await store.list_for_user("u1", PageParams(page=1, size=5), JobStatus.QUEUED)
    assert seen["where"] == {"user_id": "u1", "status": "QUEUED"}
    await store.list_for_user("u1", PageParams(page=1, size=5), None)
    assert seen["where"] == {"user_id": "u1"}


async def test_cancel_and_purge(store):
    d = store._delegate
    d.update_many_result = 1
    assert await store.cancel_queued("j1") is True
    d.update_many_result = 0
    assert await store.cancel_queued("j1") is False
    await store.request_cancel("j1")
    assert d.updates[-1][1] == {"cancel_requested": True}

    d.delete_many_result = 4
    from datetime import datetime

    assert await store.purge_finished_before(datetime(2026, 1, 1)) == 4


async def test_queue_stats(store, client):
    client.query_rows = [{"status": "QUEUED", "count": 2}]
    calls = {"n": 0}

    async def query_raw(sql, *params):
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"status": "QUEUED", "count": 2}]
        return [{"age": 30.5}]

    client.query_raw = query_raw
    stats = await store.queue_stats()
    assert stats == {"depth": {"QUEUED": 2}, "oldest_queued_age": 30.5}


async def test_queue_stats_empty_oldest(store, client):
    async def query_raw(sql, *params):
        if "GROUP BY" in sql:
            return []
        return [{"age": None}]

    client.query_raw = query_raw
    stats = await store.queue_stats()
    assert stats == {"depth": {}, "oldest_queued_age": 0.0}
