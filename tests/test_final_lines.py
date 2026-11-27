"""The last uncovered lines: heartbeat/fail guards, drain path, mcp lifespan, misc branches."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from asgi_lifespan import LifespanManager

import app.main as main_mod
from app.core.constants import JobPolicy, JobType, TokenPurpose
from app.core.exceptions import UnauthorizedError
from app.core.jobs import registry as job_registry
from app.core.jobs.types import JobRecord
from app.core.messages import Msg
from app.shared.utils.time import utcnow
from tests.fakes import FakeJobStore


def _job(job_id="j1", status="RUNNING"):
    return JobRecord(
        id=job_id,
        type="notes.export",
        status=status,
        payload={},
        result=None,
        error=None,
        progress=0,
        attempts=1,
        max_attempts=3,
        user_id="u1",
        request_id=None,
        cancel_requested=False,
        created_at=utcnow(),
        updated_at=utcnow(),
        started_at=None,
        finished_at=None,
    )


async def test_heartbeat_loop_sleeps_beats_and_warns(monkeypatch, fake_store):
    from app.core.jobs.worker import _heartbeat

    monkeypatch.setattr(JobPolicy, "HEARTBEAT_SECONDS", 0.01)
    fake_store.jobs["j1"] = SimpleNamespace(id="j1", status="RUNNING")

    async def failing(job_id):
        raise RuntimeError("store down")

    monkeypatch.setattr(fake_store, "heartbeat", failing)
    task = asyncio.create_task(_heartbeat("j1", fake_store))
    await asyncio.sleep(0.04)  # several beats, all failing -> warning logged, loop continues
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_fail_swallows_store_errors():
    from app.core.jobs.worker import _fail

    class ExplodingStore:
        async def fail(self, job_id, msg, *, retry_at):
            raise RuntimeError("write failed")

    await _fail(_job(), ExplodingStore(), Msg.INTERNAL_ERROR, retry=True)  # must not raise


async def test_worker_run_drains_running_tasks_at_stop(monkeypatch):
    """A RUNNING handler still executing at stop is awaited/cancelled, not abandoned."""
    from app.core.jobs import Worker

    async def slow(ctx):
        await asyncio.sleep(0.4)

    handler = job_registry.get_handler(JobType.NOTES_EXPORT)
    monkeypatch.setattr(
        job_registry,
        "_handlers",
        {JobType.NOTES_EXPORT: type(handler)(**{**handler.__dict__, "fn": slow, "timeout": 5})},
    )
    monkeypatch.setattr(JobPolicy, "SHUTDOWN_GRACE", 0.01)
    monkeypatch.setattr(JobPolicy, "SCHEDULE_CHECK_SECONDS", 10_000)
    monkeypatch.setattr("app.core.jobs.worker.settings.worker_poll_seconds", 0.01)
    monkeypatch.setattr("app.core.jobs.worker.settings.job_stale_seconds", 10_000)

    store = FakeJobStore()
    await store.enqueue(
        type=JobType.NOTES_EXPORT.value,
        payload={},
        user_id="u1",
        request_id=None,
        max_attempts=1,
        run_at=utcnow(),
        dedupe_key=None,
        priority=0,
    )
    worker = Worker(store)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.08)  # claimed and executing
    assert worker._running, "the slow handler must be in-flight"
    stop.set()
    await asyncio.wait_for(task, timeout=3)  # drain path: wait + cancel remaining tasks


async def test_maintenance_swallows_queue_stats_and_reap_errors(monkeypatch, fake_store):
    from app.core.jobs import Worker

    async def stats_boom():
        raise RuntimeError("stats down")

    async def reap_boom(seconds):
        raise RuntimeError("reap down")

    monkeypatch.setattr(fake_store, "queue_stats", stats_boom)
    monkeypatch.setattr(fake_store, "reap_stale", reap_boom)
    worker = Worker(fake_store)
    await worker._maintenance()  # both failures swallowed, no raise


async def test_maintenance_reap_logs_when_reaped(fake_store):
    from app.core.jobs import Worker

    async def reap(seconds):
        return 2

    fake_store.reap_stale = reap
    worker = Worker(fake_store)
    await worker._maintenance()  # reaped=2 -> info log branch


async def test_buffer_drains_batches_and_joins_flush_task(monkeypatch):
    """record -> start -> stop: the drain task collects, flushes, and is joined on stop."""
    from app.core.activity.buffer import ActivityBuffer

    flushed: list = []

    class Sink:
        async def append_many(self, entries):
            flushed.append(entries)
            return len(entries)

    monkeypatch.setattr("app.core.activity.buffer.settings.activity_enabled", True)
    monkeypatch.setattr("app.core.activity.buffer.settings.activity_flush_seconds", 0.01)
    buf = ActivityBuffer(sink=Sink())
    buf.record({"method": "GET", "path": "/x", "status_code": 200})
    await buf.start()  # task drains the queued entry
    await asyncio.sleep(0.05)  # let at least one collect+flush cycle run
    await buf.stop()  # joins the (already-stopping) task, clears it
    assert flushed and flushed[0][0]["path"] == "/x"
    assert buf._task is None


async def test_buffer_collect_timeout_and_batch_drain(monkeypatch):
    from app.core.activity.buffer import ActivityBuffer

    monkeypatch.setattr("app.core.activity.buffer.settings.activity_flush_seconds", 0.01)
    monkeypatch.setattr("app.core.activity.buffer.settings.activity_batch_size", 2)
    buf = ActivityBuffer(sink=None)
    buf._stopping = True  # collect works even while stopping; drain drains
    for i in range(3):
        buf._q.put_nowait({"i": i})
    first = await buf._collect()  # one from get() + batch-size-1 drained -> 2 items
    assert len(first) == 2
    second = await buf._collect()  # remaining item
    assert len(second) == 1
    third = await buf._collect()  # empty queue -> wait_for timeout -> []
    assert third == []


async def test_get_current_user_success_binds_user(monkeypatch):
    from app.core.context import request_ctx
    from app.core.security import create_access_token
    from app.features.auth.deps import get_current_user

    token = create_access_token("u1", 7)
    u = SimpleNamespace(
        id="u1",
        is_active=True,
        deleted_at=None,
        token_version=7,
    )

    async def get_active(uid):
        return u

    monkeypatch.setattr("app.features.auth.deps.users_repo.get", get_active)
    token_ctx = request_ctx.set(None)
    try:
        out = await get_current_user(SimpleNamespace(credentials=token))
        assert out is u
        assert request_ctx.get().user_id == "u1"  # bind_user ran
    finally:
        request_ctx.reset(token_ctx)


async def test_audit_service_actor_filter_from_query(monkeypatch):
    from app.core.audit.repository import audit_repo
    from app.features.audit.schemas import AuditQuery
    from app.features.audit.service import list_audit
    from app.shared.helpers.pagination import CursorParams

    captured: dict = {}

    async def cap(params, where=None, order=None):
        captured["where"] = where
        return [], None

    monkeypatch.setattr(audit_repo, "paginate_cursor", cap)
    q = AuditQuery(
        actor_id="u2",
        action=None,
        resource_type=None,
        resource_id=None,
        outcome=None,
        since=None,
        until=None,
    )
    await list_audit(CursorParams(cursor=None, size=5), q)  # no forced actor -> query filter
    assert captured["where"]["actor_id"] == "u2"


async def test_get_current_user_deleted_user_rejected(monkeypatch):
    from app.core.security import create_access_token
    from app.features.auth.deps import get_current_user

    token = create_access_token("u1", 0)
    u = SimpleNamespace(
        id="u1",
        is_active=True,
        deleted_at=datetime(2026, 1, 1),
        token_version=0,
    )

    async def get_deleted(uid):
        return u

    monkeypatch.setattr("app.features.auth.deps.users_repo.get", get_deleted)
    with pytest.raises(UnauthorizedError):
        await get_current_user(SimpleNamespace(credentials=token))


async def test_auth_service_reset_token_already_consumed(monkeypatch):
    from app.features.auth import service as auth_service
    from app.features.auth.repository import one_time_repo
    from app.features.auth.schemas import ResetPasswordIn

    record = SimpleNamespace(
        id="ot1",
        user_id="u1",
        purpose=TokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    async def find(h):
        return record

    async def consume(tid):
        return False  # already used (race) -> rejected

    async def find_user(uid):
        return SimpleNamespace(id="u1", token_version=0)

    monkeypatch.setattr(one_time_repo, "find_by_hash", find)
    monkeypatch.setattr(one_time_repo, "consume", consume)
    monkeypatch.setattr("app.features.users.service.find", find_user)
    with pytest.raises(UnauthorizedError):
        await auth_service.reset_password(ResetPasswordIn(token="t", new_password="b1234567"))


async def test_lifespan_with_mcp_enabled(monkeypatch):
    """The MCP mount branch of the lifespan: session manager enters and exits cleanly."""
    calls: list[str] = []

    async def connect():
        calls.append("connect")

    async def disconnect():
        calls.append("disconnect")

    async def close_cache():
        calls.append("close_cache")

    class _Activity:
        async def start(self):
            pass

        async def stop(self):
            pass

    monkeypatch.setattr(main_mod, "connect_db", connect)
    monkeypatch.setattr(main_mod, "disconnect_db", disconnect)
    monkeypatch.setattr(main_mod, "close_cache", close_cache)
    monkeypatch.setattr(main_mod, "activity", _Activity())
    monkeypatch.setattr(main_mod.settings, "worker_embedded", False)
    monkeypatch.setattr(main_mod.settings, "mcp_enabled", True)

    async with LifespanManager(main_mod.app, startup_timeout=10, shutdown_timeout=10):
        pass
    assert calls[:2] == ["connect", "close_cache"] and calls[-1] == "disconnect"
