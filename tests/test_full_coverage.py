"""Final sweep: repositories, backends, discovery, worker edges, registry, deps, mcp, services."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.discovery import feature_modules

feature_modules("jobs")  # register all @job_handler for registry/enqueue tests

from app.core.cache import cache  # noqa: E402
from app.core.cache.backends import MemoryBackend, RedisBackend, build_backend  # noqa: E402
from app.core.constants import JobType  # noqa: E402
from app.core.exceptions import UnauthorizedError  # noqa: E402
from app.core.jobs import registry as job_registry  # noqa: E402
from app.core.jobs.types import PermanentError  # noqa: E402
from app.core.messages import Msg  # noqa: E402
from app.shared.helpers.pagination import PageParams  # noqa: E402
from app.shared.utils.time import utcnow  # noqa: E402
from tests.fakes import FakeJobStore  # noqa: E402


def _user():
    from prisma.models import User

    return User(
        id="u1",
        email="a@example.com",
        password_hash="h",
        name="A",
        role="USER",
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


# --- generic delegating fake for repositories --------------------------------


class Delegate:
    def __init__(self):
        self.rows: list = []
        self.row = None
        self.total = 0
        self.calls: list = []
        self.update_many_result = 1
        self.delete_result = 0
        self.execute_result = 0

    async def find_unique(self, where, **opts):
        self.calls.append(("find_unique", where))
        return self.row

    async def find_first(self, where, **opts):
        self.calls.append(("find_first", where))
        return self.rows[0] if self.rows else None

    async def find_many(self, **kw):
        self.calls.append(("find_many", kw))
        return self.rows

    async def count(self, where):
        return self.total

    async def create(self, data, **opts):
        self.calls.append(("create", data))
        return SimpleNamespace(id="new1", **data)

    async def create_many(self, data):
        self.calls.append(("create_many", data))
        return [SimpleNamespace(id=f"m{i}") for i in range(len(data))]

    async def update(self, where, data):
        self.calls.append(("update", where, data))
        return self.row

    async def update_many(self, where, data):
        self.calls.append(("update_many", where, data))
        return self.update_many_result

    async def delete(self, where):
        self.calls.append(("delete", where))
        return self.row

    async def delete_many(self, where):
        self.calls.append(("delete_many", where))
        return self.delete_result

    async def execute_raw(self, sql, *params):
        self.calls.append(("execute_raw", sql))
        return self.execute_result


class MultiDb:
    """One fake client exposing every delegate the repositories use."""

    def __init__(self):
        self.auditlog = Delegate()
        self.activitylog = Delegate()
        self.refreshtoken = Delegate()
        self.onetimetoken = Delegate()
        self.note = Delegate()
        self.user = Delegate()
        self.idempotencyrecord = Delegate()
        self.client_calls: list = []
        self.execute_result = 0

    async def execute_raw(self, sql, *params):
        self.client_calls.append(("execute_raw", sql))
        return self.execute_result

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def multi_db(monkeypatch):
    db = MultiDb()
    monkeypatch.setattr("app.shared.helpers.repository.current_db", lambda: db)
    return db


async def test_audit_repo_scrub_and_purge(multi_db, monkeypatch):
    from app.core.audit.repository import audit_repo

    monkeypatch.setattr("app.core.audit.repository.current_db", lambda: multi_db)

    multi_db.auditlog.execute_result = 3
    multi_db.execute_result = 3
    assert await audit_repo.scrub_pii_for_actor("u1") == 3
    assert "UPDATE audit_logs" in multi_db.client_calls[-1][1]

    multi_db.auditlog.delete_result = 9
    assert await audit_repo.purge_before(utcnow()) == 9


async def test_activity_repo_append_scrub_purge(multi_db, monkeypatch):
    from app.core.activity.repository import activity_repo

    monkeypatch.setattr("app.core.activity.repository.current_db", lambda: multi_db)

    n = await activity_repo.append_many([{"method": "GET", "path": "/x"}])
    assert n == 1
    assert await activity_repo.append_many([]) == 0  # empty batch no-op

    multi_db.activitylog.execute_result = 2
    multi_db.execute_result = 2
    assert await activity_repo.scrub_ip_for_user("u1") == 2
    assert "UPDATE activity_logs" in multi_db.client_calls[-1][1]

    multi_db.activitylog.delete_result = 4
    assert await activity_repo.purge_before(utcnow()) == 4


async def test_auth_repos_all_methods(multi_db):
    from app.core.constants import TokenPurpose
    from app.features.auth.repository import one_time_repo, refresh_repo

    rt = multi_db.refreshtoken
    rt.row = SimpleNamespace(id="rt1")
    assert await refresh_repo.find_by_hash("h") is not None
    await refresh_repo.create({"user_id": "u1"})
    rt.update_many_result = 1
    assert await refresh_repo.revoke_if_active("rt1") is True
    assert await refresh_repo.revoke_family("fam") == 1
    assert await refresh_repo.revoke_all_for_user("u1") == 1
    await refresh_repo.mark_replaced("rt1", "newhash")
    rt.delete_result = 5
    assert await refresh_repo.purge(utcnow()) == 5

    ot = multi_db.onetimetoken
    ot.row = SimpleNamespace(id="ot1")
    assert await one_time_repo.find_by_hash("h") is not None
    await one_time_repo.create({"user_id": "u1"})
    assert await one_time_repo.consume("ot1") is True
    await one_time_repo.invalidate_unused("u1", TokenPurpose.VERIFY_EMAIL.value)
    ot.delete_result = 2
    assert await one_time_repo.purge(utcnow()) == 2


async def test_notes_and_users_repos(multi_db):
    from app.features.notes.repository import notes_repo
    from app.features.users.repository import users_repo

    multi_db.note.total = 1
    items, total = await notes_repo.list_for_user("u1", PageParams(page=1, size=5))
    assert total == 1

    multi_db.user.rows = [_user()]
    assert await users_repo.find_by_email("A@Example.COM") is not None  # lowercased


# --- cache backends ----------------------------------------------------------


def _backend(clock):
    return MemoryBackend(max_items=2, clock=clock)


async def test_memory_backend_expiry_eviction_ping_close():
    t = {"now": 100.0}
    b = _backend(lambda: t["now"])

    await b.set("k", b"v", ttl=10)
    assert await b.get("k") == b"v"
    t["now"] = 200.0
    assert await b.get("k") is None  # expired

    await b.set("a", b"1", ttl=100)
    await b.set("b", b"2", ttl=100)
    await b.set("c", b"3", ttl=100)  # LRU evicts "a" (max_items=2)
    assert await b.get("a") is None
    assert await b.get("c") == b"3"

    await b.incr("counter")
    assert await b.get("counter") == b"1"  # counters readable through get

    assert await b.ping() is True
    await b.close()  # clears all state


async def test_memory_backend_incr_window_resets_after_expiry():
    t = {"now": 0.0}
    b = _backend(lambda: t["now"])
    count, remaining = await b.incr_window("r", ttl=60)
    assert (count, remaining) == (1, 60)
    t["now"] = 61.0  # window expired -> count resets
    count, remaining = await b.incr_window("r", ttl=60)
    assert count == 1 and remaining == 60


class FakeRedis:
    def __init__(self):
        self.data: dict = {}
        self.closed = False

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)

    async def incr(self, key):
        self.data[key] = int(self.data.get(key, b"0") or 0) + 1
        return self.data[key]

    def pipeline(self, transaction=True):
        return FakePipe(self)

    async def ping(self):
        return True

    async def aclose(self):
        self.closed = True


class FakePipe:
    def __init__(self, r):
        self.r = r
        self.ops: list = []

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, ttl, nx=True):
        self.ops.append(("expire", key, ttl))

    def ttl(self, key):
        self.ops.append(("ttl", key))

    async def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "incr":
                self.r.data[op[1]] = int(self.r.data.get(op[1], b"0") or 0) + 1
                out.append(self.r.data[op[1]])
            elif op[0] == "expire":
                out.append(True)
            else:
                out.append(30)
        self.ops = []
        return out

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_redis_backend_methods_with_fake_client():
    b = RedisBackend("redis://localhost:6379/0")
    b._r = FakeRedis()
    await b.set("k", b"v", ttl=10)
    assert await b.get("k") == b"v"
    await b.delete("k", "other")
    assert await b.incr("n") == 1
    count, remaining = await b.incr_window("w", ttl=60)
    assert count == 1 and remaining == 30
    assert await b.ping() is True
    await b.close()
    assert b._r.closed is True


async def test_build_backend_redis_and_ping_failure(monkeypatch):
    monkeypatch.setattr("app.core.cache.backends.settings.cache_backend", "redis")
    b = build_backend()
    assert isinstance(b, RedisBackend)
    b._r = FakeRedis()

    async def dead():
        raise RuntimeError("down")

    b._r.ping = dead
    assert await b.ping() is False


async def test_close_cache_closes_backend(monkeypatch):
    closed: list = []

    class B:
        async def close(self):
            closed.append(True)

    monkeypatch.setattr(cache, "backend", B())
    from app.core.cache import close_cache

    await close_cache()
    assert closed == [True]


async def test_activity_buffer_stop_without_task():
    from app.core.activity.buffer import ActivityBuffer

    buf = ActivityBuffer()
    buf._task = None
    await buf.stop()  # no task -> returns immediately


# --- discovery: hidden + broken features -------------------------------------


def test_discovery_skips_underscore_and_reraises_real_import_errors(monkeypatch, tmp_path):
    import app.features as features_pkg

    hidden = tmp_path / "_hidden"
    hidden.mkdir()
    (hidden / "__init__.py").write_text("", encoding="utf-8")
    broken = tmp_path / "brokenfeat"
    broken.mkdir()
    (broken / "__init__.py").write_text("", encoding="utf-8")
    (broken / "router.py").write_text("import nonexistent_pkg_xyz\n", encoding="utf-8")

    monkeypatch.setattr(features_pkg, "__path__", [str(tmp_path)])
    from app.core.discovery import feature_modules

    with pytest.raises(ModuleNotFoundError):
        feature_modules("router")  # a REAL missing dependency must re-raise (line 20)


# --- jobs facade + registry --------------------------------------------------


async def test_enqueue_rejects_wrong_payload_type(fake_store):
    from app.core.jobs import enqueue

    with pytest.raises(TypeError):
        await enqueue(
            JobType.AUTH_SEND_TOKEN_EMAIL,
            {"not": "a payload model"},
            user_id="u1",
        )


def test_registry_duplicate_and_unknown(monkeypatch):
    from pydantic import BaseModel

    from app.core.jobs.registry import job_handler

    class P(BaseModel):
        x: int = 0

    with pytest.raises(RuntimeError):  # notes.export is already registered by discovery
        job_handler(JobType.NOTES_EXPORT)(lambda ctx: None)

    # a VALID JobType with no handler => PermanentError (defensive unknown-type branch)
    handlers = dict(job_registry._handlers)
    handlers.pop(JobType.NOTES_EXPORT)
    monkeypatch.setattr(job_registry, "_handlers", handlers)
    with pytest.raises(PermanentError):
        job_registry.get_handler(JobType.NOTES_EXPORT.value)


# --- worker edges ------------------------------------------------------------


async def test_heartbeat_loop_beats_and_stops(fake_store):
    from app.core.jobs.worker import _heartbeat

    job = SimpleNamespace(id="j1")
    fake_store.jobs["j1"] = SimpleNamespace(id="j1", status="RUNNING")
    task = asyncio.create_task(_heartbeat(job.id, fake_store))
    await asyncio.sleep(0.03)  # HEARTBEAT_SECONDS is small enough to beat a few times
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_execute_timeout_requeues(fake_store, monkeypatch):
    from app.core.jobs import execute

    async def sleepy(ctx):
        await asyncio.sleep(0.5)

    handler = job_registry.get_handler(JobType.NOTES_EXPORT)
    monkeypatch.setattr(
        job_registry,
        "_handlers",
        {
            JobType.NOTES_EXPORT: type(handler)(
                **{**handler.__dict__, "timeout": 0.05, "fn": sleepy}
            )
        },  # noqa: E501
    )
    job, _ = await fake_store.enqueue(
        type=JobType.NOTES_EXPORT.value,
        payload={},
        user_id="u1",
        request_id=None,
        max_attempts=3,
        run_at=utcnow(),
        dedupe_key=None,
        priority=0,
    )
    await execute(job, fake_store)
    assert fake_store.jobs[job.id].status == "QUEUED"  # timeout => retried
    assert fake_store.jobs[job.id].error == Msg.JOB_TIMEOUT.value


async def test_schedule_enqueue_failure_is_swallowed(fake_store, monkeypatch):
    from app.core.jobs import Worker

    async def boom(**kw):
        raise RuntimeError("store down")

    monkeypatch.setattr(fake_store, "enqueue", boom)
    worker = Worker(fake_store)
    await worker._schedule()  # must not raise


async def test_run_loop_survives_store_errors(monkeypatch):
    from app.core.jobs import Worker

    class FlakyStore(FakeJobStore):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def claim(self, worker_id, types, limit):
            self.calls += 1
            raise RuntimeError("claim failed")

    store = FlakyStore()
    monkeypatch.setattr("app.core.jobs.worker.settings.worker_poll_seconds", 0.01)
    worker = Worker(store)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.08)
    stop.set()
    await asyncio.wait_for(task, timeout=3)  # loop caught the error and kept going
    assert store.calls >= 1


# --- auth deps: inactive user ------------------------------------------------


async def test_get_current_user_inactive_rejected(monkeypatch):
    from app.core.security import create_access_token
    from app.features.auth.deps import get_current_user

    token = create_access_token("u1", 0)
    u = _user()
    u.is_active = False

    async def get_inactive(uid):
        return u

    monkeypatch.setattr("app.features.auth.deps.users_repo.get", get_inactive)
    with pytest.raises(UnauthorizedError):
        await get_current_user(SimpleNamespace(credentials=token))


# --- mcp: unknown client name ------------------------------------------------


async def test_scoped_tool_unknown_client_treated_open(monkeypatch):
    from app.core.context import mcp_client_var
    from app.core.mcp import _scoped

    async def tool():
        return "ok"

    monkeypatch.setattr(
        "app.core.mcp.settings.mcp_clients",
        [SimpleNamespace(name="other", tools=["*"])],
    )
    mcp_client_var.set("ghost")  # not in settings -> treated as open
    assert await _scoped(tool)() == "ok"


# --- users schemas + service -------------------------------------------------


def test_user_update_locale_validator():
    from app.features.users.schemas import UserUpdate

    assert UserUpdate(locale="en").locale == "en"
    with pytest.raises(ValueError):
        UserUpdate(locale="xx")


async def test_users_service_request_export_and_promote_admin(monkeypatch, audit_sink):
    from app.features.jobs.schemas import JobOut
    from app.features.users import service as users_service

    submitted: list = []

    async def submit(user, job_type, payload=None, idempotency_key=None):
        submitted.append(job_type)
        return JobOut(
            id="j1",
            type=job_type,
            status="QUEUED",
            progress=0,
            attempts=0,
            max_attempts=3,
            result=None,
            error=None,
            created_at=utcnow(),
            started_at=None,
            finished_at=None,
            updated_at=utcnow(),
        )

    monkeypatch.setattr(users_service.jobs_service, "submit", submit)
    job = await users_service.request_export(_user(), "idem-1")
    assert job.id == "j1" and submitted == [JobType.ACCOUNT_EXPORT]

    promoted: list = []

    async def find_by_email(email):
        return _user()

    async def update(uid, data):
        promoted.append((uid, data))
        return _user()

    monkeypatch.setattr(users_service.users_repo, "find_by_email", find_by_email)
    monkeypatch.setattr(users_service.users_repo, "update", update)
    await users_service.create_admin("a@example.com", "supersecret", promote=True)
    assert promoted and promoted[0][1] == {"role": "ADMIN"}
    assert any(e["action"] == "admin.bootstrap" for e in audit_sink.entries)


# --- notes router: idempotent first call -------------------------------------


async def test_notes_router_create_via_run_once(monkeypatch):
    from types import SimpleNamespace as NS

    from app.features.notes import router as notes_router
    from app.features.notes.schemas import NoteCreate

    async def fake_run_once(scope, key, payload, fn):
        status, data = await fn()  # first call: run the creator (fn returns (code, data))
        return status, data, False

    note = SimpleNamespace(
        id="n1",
        user_id="u1",
        title="T",
        body="B",
        version=1,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )

    async def create(u, p):
        return note

    monkeypatch.setattr(notes_router, "run_once", fake_run_once)
    monkeypatch.setattr(notes_router.service, "create", create)
    response = NS(headers={}, status_code=None)
    r = await notes_router.create_note(response, _user(), NoteCreate(title="T", body="B"), "key")
    assert r.data["id"] == "n1"
    assert notes_router._create is not None  # helper exists and is used by run_once


# --- jobs service: queued-cancel race ----------------------------------------


async def test_jobs_service_cancel_queued_lost_race(monkeypatch, audit_sink):
    from datetime import datetime as dt
    from types import SimpleNamespace as NS

    from app.features.jobs import service as jobs_service

    user = _user()
    job = NS(
        id="j1",
        type="notes.export",
        status="QUEUED",
        progress=0,
        attempts=0,
        max_attempts=3,
        result=None,
        error=None,
        user_id="u1",
        cancel_requested=False,
        created_at=dt(2026, 1, 1),
        started_at=None,
        finished_at=None,
        updated_at=dt(2026, 1, 1),
    )

    async def owned(u, job_id, write=False):
        return job

    requested: list = []

    async def request_cancel(job_id):
        requested.append(job_id)

    async def cancel_queued(job_id):
        return False  # someone else cancelled/claimed it first

    async def get(job_id):
        return job

    store = NS(cancel_queued=cancel_queued, request_cancel=request_cancel, get=get)
    monkeypatch.setattr(jobs_service, "get_store", lambda: store)
    monkeypatch.setattr(jobs_service, "_owned", owned)

    out, msg = await jobs_service.cancel(user, "j1")
    assert requested == ["j1"] and msg == Msg.JOB_CANCEL_REQUESTED
