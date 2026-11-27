"""Routers exercised via direct handler calls (thin HTTP layer; deps stubbed)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.constants import JobStatus, Role
from app.core.exceptions import (
    PreconditionRequiredError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.messages import Msg
from app.features.audit import router as audit_router
from app.features.audit.schemas import ActivityQuery, AuditQuery
from app.features.auth import router as auth_router
from app.features.auth.deps import get_current_user, get_verified_user
from app.features.auth.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    VerifyEmailIn,
)
from app.features.health import router as health_router
from app.features.jobs import router as jobs_router
from app.features.notes import router as notes_router
from app.features.notes.schemas import NoteCreate, NoteUpdate
from app.features.users import router as users_router
from app.shared.helpers.pagination import CursorParams, PageParams


def _audit_query(**kw):
    base = dict(
        actor_id=None,
        action=None,
        resource_type=None,
        resource_id=None,
        outcome=None,
        since=None,
        until=None,
    )
    base.update(kw)
    return AuditQuery(**base)


def _activity_query(**kw):
    base = dict(user_id=None, status_code=None, path=None, since=None, until=None)
    base.update(kw)
    return ActivityQuery(**base)


def _user():
    return SimpleNamespace(
        id="u1",
        email="a@example.com",
        name="A",
        role=Role.USER,
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        password_hash="h",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _resp():
    return SimpleNamespace(headers={}, status_code=None)


# --- notes router ------------------------------------------------------------


async def test_notes_router_all_handlers(monkeypatch):
    user = _user()
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

    async def get(u, nid):
        return note

    async def update(u, nid, p, v):
        return note

    async def delete(u, nid):
        return None

    async def export(u, key):
        return SimpleNamespace(
            id="job1",
            type="notes.export",
            status=JobStatus.QUEUED,
            progress=0,
            attempts=0,
            max_attempts=3,
            result=None,
            error=None,
            created_at=datetime(2026, 1, 1),
            started_at=None,
            finished_at=None,
            updated_at=datetime(2026, 1, 1),
        )

    monkeypatch.setattr(notes_router.service, "create", create)

    async def list_notes(u, params, sort=None, q=None):
        return [note], 1

    monkeypatch.setattr(notes_router.service, "list_notes", list_notes)
    monkeypatch.setattr(notes_router.service, "get", get)
    monkeypatch.setattr(notes_router.service, "update", update)
    monkeypatch.setattr(notes_router.service, "delete", delete)
    monkeypatch.setattr(notes_router.service, "request_export", export)

    r = await notes_router.create_note(_resp(), user, NoteCreate(title="T", body="B"), None)
    assert r.data.version == 1 and _resp().headers == {}

    r = await notes_router.list_notes(user, PageParams(page=1, size=5), None, None)
    assert r.success

    r = await notes_router.export_notes(_resp(), user, None)
    assert r.success

    r = await notes_router.get_note(_resp(), user, "n1")
    assert r.data.id == "n1"

    r = await notes_router.update_note(_resp(), user, "n1", NoteUpdate(title="U"), '"1"')
    assert r.data.title in ("T", "U")

    r = await notes_router.delete_note(user, "n1")
    assert r.data == {"id": "n1"}


async def test_notes_update_requires_if_match():
    with pytest.raises(PreconditionRequiredError):
        await notes_router.update_note(_resp(), _user(), "n1", NoteUpdate(title="U"), None)


async def test_notes_create_with_idempotency_key_replay(monkeypatch):
    user = _user()

    async def fake_run_once(scope, key, payload, fn):
        return 201, {"id": "n9"}, True

    monkeypatch.setattr(notes_router, "run_once", fake_run_once)
    r = await notes_router.create_note(_resp(), user, NoteCreate(title="T"), "key-1")
    assert r.data == {"id": "n9"}


# --- users router ------------------------------------------------------------


async def test_users_router_all_handlers(monkeypatch):
    user = _user()

    async def update_me(u, p):
        return u

    async def list_users(params):
        return [user], 1

    async def delete_me(u, pw):
        return None

    async def export(u, key):
        return SimpleNamespace(
            id="job1",
            type="account.export",
            status=JobStatus.QUEUED,
            progress=0,
            attempts=0,
            max_attempts=3,
            result=None,
            error=None,
            created_at=datetime(2026, 1, 1),
            started_at=None,
            finished_at=None,
            updated_at=datetime(2026, 1, 1),
        )

    monkeypatch.setattr(users_router.service, "update_me", update_me)
    monkeypatch.setattr(users_router.service, "list_users", list_users)
    monkeypatch.setattr(users_router.service, "delete_me", delete_me)
    monkeypatch.setattr(users_router.service, "request_export", export)

    r = await users_router.read_me(user)
    assert r.data.email == "a@example.com"

    r = await users_router.update_me(user, users_router.UserUpdate(name="B"))
    assert r.success

    r = await users_router.list_users(PageParams(page=1, size=5))
    assert r.success

    r = await users_router.delete_me(user, users_router.DeleteMeIn(password="pw"))
    assert r.success

    r = await users_router.export_me(_resp(), user, None)
    assert r.success


# --- audit router ------------------------------------------------------------


async def test_audit_router_all_handlers(monkeypatch):
    from types import SimpleNamespace as NS

    user = _user()
    request = NS(scope={"route": NS(path="/api/v1/audit")})

    async def list_audit(params, query, *, actor_id=None):
        captured["actor_id"] = actor_id
        return [], None

    async def list_my(u, params):
        return [], None

    async def list_activity(params, query, *, user_id=None):
        captured["activity_user_id"] = user_id
        return [], None

    captured: dict = {}

    async def scope_all(u, perm):
        return "all"

    monkeypatch.setattr(audit_router.service, "list_audit", list_audit)
    monkeypatch.setattr(audit_router.service, "list_my_audit", list_my)
    monkeypatch.setattr(audit_router.service, "list_activity", list_activity)
    monkeypatch.setattr(audit_router.authz, "read_scope", scope_all)

    r = await audit_router.search_audit(
        request, user, CursorParams(cursor=None, size=5), _audit_query()
    )
    assert r.success and captured["actor_id"] is None  # "all" scope: no forced filter
    r = await audit_router.my_audit(user, CursorParams(cursor=None, size=5))
    assert r.success
    r = await audit_router.activity_log(
        request, user, CursorParams(cursor=None, size=5), _activity_query()
    )
    assert r.success and captured["activity_user_id"] is None


async def test_audit_router_own_scope_narrows_and_blocks_others(monkeypatch, audit_sink):
    from types import SimpleNamespace as NS

    from app.core.constants import Permission
    from app.core.exceptions import ForbiddenError

    user = _user()
    request = NS(scope={"route": NS(path="/api/v1/audit")})

    async def list_audit(params, query, *, actor_id=None):
        return [], None

    async def scope_own(u, perm):
        return "own"

    monkeypatch.setattr(audit_router.service, "list_audit", list_audit)
    monkeypatch.setattr(audit_router.authz, "read_scope", scope_own)

    r = await audit_router.search_audit(
        request, user, CursorParams(cursor=None, size=5), _audit_query()
    )
    assert r.success  # own scope applied inside the service (actor_id forced)

    # own-scope grant cannot inspect someone else's audit trail
    with pytest.raises(ForbiddenError):
        await audit_router.search_audit(
            request, user, CursorParams(cursor=None, size=5), _audit_query(actor_id="someone-else")
        )
    assert any(
        e["action"] == "access.denied" and Permission.AUDIT_READ.value in e["metadata"]["required"]
        for e in audit_sink.entries
    )

    async def list_activity(params, query, *, user_id=None):
        return [], None

    monkeypatch.setattr(audit_router.service, "list_activity", list_activity)
    r = await audit_router.activity_log(
        request, user, CursorParams(cursor=None, size=5), _activity_query()
    )
    assert r.success
    with pytest.raises(ForbiddenError):
        await audit_router.activity_log(
            request, user, CursorParams(cursor=None, size=5), _activity_query(user_id="other")
        )


async def test_audit_router_denied_when_no_scope(monkeypatch, audit_sink):
    from types import SimpleNamespace as NS

    from app.core.exceptions import ForbiddenError

    user = _user()
    request = NS(scope={"route": NS(path="/api/v1/audit")})

    async def scope_none(u, perm):
        return None

    monkeypatch.setattr(audit_router.authz, "read_scope", scope_none)
    with pytest.raises(ForbiddenError):
        await audit_router.search_audit(
            request, user, CursorParams(cursor=None, size=5), _audit_query()
        )
    with pytest.raises(ForbiddenError):
        await audit_router.activity_log(
            request, user, CursorParams(cursor=None, size=5), _activity_query()
        )
    denied = [e for e in audit_sink.entries if e["action"] == "access.denied"]
    assert len(denied) == 2


# --- jobs router -------------------------------------------------------------


async def test_jobs_router_list_and_cancel(monkeypatch):
    user = _user()

    async def list_jobs(u, params, status):
        return [], 0

    async def cancel(u, job_id):
        return SimpleNamespace(
            id=job_id,
            type="notes.export",
            status=JobStatus.CANCELLED,
            progress=100,
            attempts=1,
            max_attempts=3,
            result=None,
            error=None,
            created_at=datetime(2026, 1, 1),
            started_at=None,
            finished_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        ), Msg.JOB_CANCELLED

    monkeypatch.setattr(jobs_router.service, "list_jobs", list_jobs)
    monkeypatch.setattr(jobs_router.service, "cancel", cancel)

    r = await jobs_router.list_jobs(user, PageParams(page=1, size=5), None)
    assert r.success

    r = await jobs_router.cancel_job("j1", user)
    assert r.success


async def test_jobs_router_poll_304_and_retry_after(monkeypatch):
    from types import SimpleNamespace as NS

    user = _user()
    job = NS(
        id="j1",
        type="notes.export",
        status=JobStatus.QUEUED,
        progress=0,
        attempts=1,
        max_attempts=3,
        result=None,
        error=None,
        created_at=datetime(2026, 1, 1),
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 1, 1),
    )

    async def get(u, job_id):
        return job

    monkeypatch.setattr(jobs_router.service, "get", get)

    resp = _resp()
    r = await jobs_router.get_job("j1", NS(headers={}), resp, user)
    assert r.success
    from app.core.constants import Header

    assert resp.headers[Header.RETRY_AFTER] == "2"

    # If-None-Match matching the ETag => 304
    from app.shared.helpers.http import etag_for

    etag = etag_for(job.id, job.status, job.progress, job.updated_at)
    r2 = await jobs_router.get_job("j1", NS(headers={"if-none-match": etag}), _resp(), user)
    assert getattr(r2, "status_code", None) == 304 or getattr(r2, "body", None) == b""


# --- health router -----------------------------------------------------------


class FakeHealthDb:
    def __init__(self, fail=False):
        self.fail = fail

    async def query_raw(self, sql):
        if self.fail:
            raise RuntimeError("db down")
        return []


async def test_health_ready_paths(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(shutting_down=False)))

    monkeypatch.setattr(health_router, "db", FakeHealthDb(fail=False))
    monkeypatch.setattr(health_router.settings, "cache_backend", "memory")
    r = await health_router.ready(request)
    assert r.data["checks"] == {"database": "up", "cache": "skipped"}

    monkeypatch.setattr(health_router, "db", FakeHealthDb(fail=True))
    with pytest.raises(ServiceUnavailableError):
        await health_router.ready(request)

    monkeypatch.setattr(health_router, "db", FakeHealthDb(fail=False))
    monkeypatch.setattr(health_router.settings, "cache_backend", "redis")
    monkeypatch.setattr(health_router.cache.backend, "ping", _ok)
    r = await health_router.ready(request)
    assert r.data["checks"]["cache"] == "up"


async def _ok():
    return True


async def test_health_ready_shutting_down(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(shutting_down=True)))
    with pytest.raises(ServiceUnavailableError):
        await health_router.ready(request)


async def test_health_alias_and_tools():
    r = await health_router.health_alias()
    assert r.data["status"] == "up"

    from app.features.health.tools import get_current_time

    out = await get_current_time()
    assert isinstance(out, (dict, str))
    if isinstance(out, dict):
        assert out  # non-empty payload


def _store_stub():
    from types import SimpleNamespace as NS

    async def cancel_queued(job_id):
        return False

    async def request_cancel(job_id):
        return None

    async def get(job_id):
        return None

    return NS(cancel_queued=cancel_queued, request_cancel=request_cancel, get=get)


# --- auth router -------------------------------------------------------------


async def test_auth_router_handlers(monkeypatch):
    user = _user()
    token = SimpleNamespace(access_token="a", refresh_token="r", expires_in=900)

    async def register(p):
        return token

    async def login(p):
        return token

    async def refresh(raw):
        return token

    async def logout(raw):
        return None

    async def logout_all(u):
        return None

    async def change_password(u, p):
        return None

    async def verify_email(raw):
        return None

    async def resend(u):
        return None

    async def forgot(email):
        return None

    async def reset(p):
        return None

    monkeypatch.setattr(auth_router.service, "register", register)
    monkeypatch.setattr(auth_router.service, "login", login)
    monkeypatch.setattr(auth_router.service, "refresh", refresh)
    monkeypatch.setattr(auth_router.service, "logout", logout)
    monkeypatch.setattr(auth_router.service, "logout_all", logout_all)
    monkeypatch.setattr(auth_router.service, "change_password", change_password)
    monkeypatch.setattr(auth_router.service, "verify_email", verify_email)
    monkeypatch.setattr(auth_router.service, "resend_verification", resend)
    monkeypatch.setattr(auth_router.service, "forgot_password", forgot)
    monkeypatch.setattr(auth_router.service, "reset_password", reset)

    register_call = auth_router.register(RegisterIn(email="a@b.co", password="p1234567", name="A"))
    assert (await register_call).success
    assert (await auth_router.login(LoginIn(email="a@b.co", password="p"))).success
    assert (await auth_router.refresh(RefreshIn(refresh_token="r"))).success
    assert (await auth_router.logout(LogoutIn(refresh_token="r"))).success
    assert (await auth_router.logout_all(user)).success
    cp = ChangePasswordIn(current_password="a", new_password="b1234567")
    assert (await auth_router.change_password(user, cp)).success
    assert (await auth_router.verify_email(VerifyEmailIn(token="t"))).success
    assert (await auth_router.resend_verification(user)).success
    assert (await auth_router.forgot_password(ForgotPasswordIn(email="a@b.co"))).success
    reset_call = auth_router.reset_password(ResetPasswordIn(token="t", new_password="b1234567"))
    assert (await reset_call).success


# --- auth deps ---------------------------------------------------------------


async def test_get_current_user_guards(monkeypatch):
    with pytest.raises(UnauthorizedError):
        await get_current_user(None)  # no bearer credentials

    from app.core.security import create_access_token

    token = create_access_token("u1", 0)
    creds = SimpleNamespace(credentials=token)

    async def none(uid):
        return None

    monkeypatch.setattr("app.features.auth.deps.users_repo.get", none)
    with pytest.raises(UnauthorizedError):
        await get_current_user(creds)  # unknown/deleted user


async def test_get_verified_user(monkeypatch):
    from app.core.config import settings
    from app.core.messages import Msg

    user = _user()
    monkeypatch.setattr(settings, "require_email_verification", True)

    user.email_verified_at = None
    with pytest.raises(Exception) as ei:
        await get_verified_user(user)
    assert ei.value.msg == Msg.AUTH_EMAIL_NOT_VERIFIED

    from datetime import datetime as dt

    user.email_verified_at = dt.now(UTC)
    assert await get_verified_user(user) is user

    monkeypatch.setattr(settings, "require_email_verification", False)
    user.email_verified_at = None
    assert await get_verified_user(user) is user  # not required -> passes


# --- services remainder ------------------------------------------------------


async def test_notes_service_list_q_filter_and_delete(monkeypatch):
    from prisma.models import Note

    from app.features.notes import service as notes_service

    user = _user()
    seen: dict = {}

    async def paginate(params, where=None, order=None):
        seen["where"] = where
        return [], 0

    monkeypatch.setattr(notes_service.notes_repo, "paginate", paginate)
    await notes_service.list_notes(user, PageParams(page=1, size=5), None, "hello")
    assert seen["where"]["title"] == {"contains": "hello", "mode": "insensitive"}

    note = Note(
        id="n1",
        user_id="u1",
        title="T",
        body="",
        version=1,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )

    async def get_owned(nid):
        return note

    deleted: list = []

    async def delete(nid):
        deleted.append(nid)

    monkeypatch.setattr(notes_service.notes_repo, "get", get_owned)
    monkeypatch.setattr(notes_service.notes_repo, "delete", delete)
    await notes_service.delete(user, "n1")
    assert deleted == ["n1"]


async def test_users_service_paths(monkeypatch):

    from app.core.exceptions import NotFoundError
    from app.features.users import service as users_service

    async def none(uid):
        return None

    monkeypatch.setattr(users_service.users_repo, "get", none)
    with pytest.raises(NotFoundError):
        await users_service.get("nope")

    user = _user()

    async def find_cached(uid):
        return user

    monkeypatch.setattr(users_service, "find", find_cached)
    assert await users_service.get("u1") is user

    async def paginate(params, where=None, order=None):
        return [], 0

    monkeypatch.setattr(users_service.users_repo, "paginate", paginate)
    items, total = await users_service.list_users(PageParams(page=1, size=5))
    assert total == 0


async def test_users_service_update_me_missing_and_delete_wrong_password(monkeypatch):
    from app.core.exceptions import NotFoundError, UnauthorizedError
    from app.features.users import service as users_service
    from app.features.users.schemas import UserUpdate

    user = _user()

    async def update_none(uid, data):
        return None

    async def noop(cb):
        return None

    monkeypatch.setattr(users_service.users_repo, "update", update_none)
    monkeypatch.setattr(users_service, "after_commit", noop)
    with pytest.raises(NotFoundError):
        await users_service.update_me(user, UserUpdate(name="B"))

    from prisma.models import User as U

    from app.core.security import hash_password

    real_user = U(
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
    with pytest.raises(UnauthorizedError):
        await users_service.delete_me(real_user, "wrong")


async def test_auth_service_login_account_locked(monkeypatch):
    from app.features.auth import service as auth_service

    async def locked(bucket, identity):
        return 5

    monkeypatch.setattr(auth_service, "peek", locked)
    with pytest.raises(UnauthorizedError):
        await auth_service.login(LoginIn(email="a@example.com", password="pw"))


async def test_auth_service_reset_unknown_user(monkeypatch):
    from datetime import timedelta

    from app.core.constants import TokenPurpose
    from app.features.auth import service as auth_service
    from app.features.auth.repository import one_time_repo
    from app.features.auth.schemas import ResetPasswordIn

    record = SimpleNamespace(
        id="ot1",
        user_id="ghost",
        purpose=TokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    async def find(h):
        return record

    async def find_user(uid):
        return None

    monkeypatch.setattr(one_time_repo, "find_by_hash", find)
    monkeypatch.setattr("app.features.users.service.find", find_user)
    with pytest.raises(UnauthorizedError):
        await auth_service.reset_password(ResetPasswordIn(token="t", new_password="b1234567"))


async def test_audit_service_actor_and_time_filters(monkeypatch):
    from datetime import UTC
    from datetime import datetime as dt

    from app.core.activity.repository import activity_repo
    from app.core.audit.repository import audit_repo
    from app.features.audit.service import list_activity, list_audit

    captured: dict = {}

    async def cap(params, where=None, order=None):
        captured["where"] = where
        return [], None

    monkeypatch.setattr(audit_repo, "paginate_cursor", cap)
    since = dt(2026, 1, 1, tzinfo=UTC)
    await list_audit(CursorParams(cursor=None, size=5), _audit_query(since=since))
    assert captured["where"]["occurred_at"] == {"gte": since}

    monkeypatch.setattr(activity_repo, "paginate_cursor", cap)
    until = dt(2026, 2, 1, tzinfo=UTC)
    await list_activity(
        CursorParams(cursor=None, size=5), _activity_query(since=since, until=until)
    )
    assert captured["where"]["occurred_at"] == {"gte": since, "lt": until}


async def test_jobs_service_list_and_cancel_paths(monkeypatch):
    from app.features.jobs import service as jobs_service

    user = _user()

    async def list_for_user(uid, params, status):
        return [], 0

    monkeypatch.setattr(jobs_service, "get_store", lambda: _store_with_list(list_for_user))
    items, total = await jobs_service.list_jobs(user, PageParams(page=1, size=5), None)
    assert total == 0


def _store_with_list(list_for_user):
    from types import SimpleNamespace as NS

    async def cancel_queued(job_id):
        return False

    async def request_cancel(job_id):
        return None

    async def get(job_id):
        return None

    return NS(
        list_for_user=list_for_user,
        cancel_queued=cancel_queued,
        request_cancel=request_cancel,
        get=get,
    )


async def test_jobs_service_cancel_requested_path(monkeypatch, audit_sink):
    """RUNNING job: cancel() requests cancellation instead of cancelling outright."""
    from datetime import datetime as dt
    from types import SimpleNamespace as NS

    from app.features.jobs import service as jobs_service

    user = _user()
    job = NS(
        id="j1",
        type="notes.export",
        status=JobStatus.RUNNING.value,
        progress=10,
        attempts=1,
        max_attempts=3,
        result=None,
        error=None,
        user_id="u1",
        created_at=dt(2026, 1, 1),
        started_at=dt(2026, 1, 1),
        finished_at=None,
        updated_at=dt(2026, 1, 1),
        cancel_requested=False,
    )

    async def owned(u, job_id, write=False):
        return job

    requested: list = []

    async def request_cancel(job_id):
        requested.append(job_id)

    async def get(job_id):
        return job

    store = NS(request_cancel=request_cancel, get=get, cancel_queued=None)
    monkeypatch.setattr(jobs_service, "get_store", lambda: store)
    monkeypatch.setattr(jobs_service, "_owned", owned)

    out, msg = await jobs_service.cancel(user, "j1")
    assert requested == ["j1"] and msg == Msg.JOB_CANCEL_REQUESTED
    assert out.id == "j1"


async def test_jobs_service_cancel_terminal_conflict(monkeypatch):
    from datetime import datetime as dt
    from types import SimpleNamespace as NS

    from app.core.exceptions import ConflictError
    from app.features.jobs import service as jobs_service

    user = _user()
    job = NS(
        id="j1",
        type="notes.export",
        status=JobStatus.SUCCEEDED.value,
        progress=100,
        attempts=1,
        max_attempts=3,
        result=None,
        error=None,
        user_id="u1",
        created_at=dt(2026, 1, 1),
        started_at=dt(2026, 1, 1),
        finished_at=dt(2026, 1, 1),
        updated_at=dt(2026, 1, 1),
    )

    async def owned(u, job_id, write=False):
        return job

    monkeypatch.setattr(jobs_service, "_owned", owned)
    with pytest.raises(ConflictError):
        await jobs_service.cancel(user, "j1")
