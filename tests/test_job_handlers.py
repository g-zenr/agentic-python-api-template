"""Job handlers (auth/notes/users/maintenance) and the MCP gate, with fakes."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.constants import TokenPurpose
from app.core.jobs.types import JobContext, JobRecord
from app.shared.utils.time import utcnow
from tests.fakes import FakeJobStore


def _ctx(user_id="u1"):
    store = FakeJobStore()
    job = JobRecord(
        id="j1",
        type="x",
        status="RUNNING",
        payload={},
        result=None,
        error=None,
        progress=0,
        attempts=1,
        max_attempts=3,
        user_id=user_id,
        request_id=None,
        cancel_requested=False,
        created_at=utcnow(),
        updated_at=utcnow(),
        started_at=None,
        finished_at=None,
    )
    store.jobs[job.id] = job  # so progress/heartbeat lookups work
    store._run_at[job.id] = utcnow()
    return JobContext(job, store)


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


# --- auth jobs: send_token_email ---------------------------------------------


@pytest.fixture
def email_env(monkeypatch):
    sent: list = []
    tokens: list = []

    class Sender:
        async def send(self, to, subject, body):
            sent.append((to, subject, body))

    async def get(uid):
        return _user()

    async def invalidate(uid, purpose):
        tokens.append(("invalidate", uid, purpose))

    async def create(data):
        tokens.append(("create", data))
        return SimpleNamespace(**data)

    monkeypatch.setattr("app.features.auth.jobs.users_repo.get", get)
    monkeypatch.setattr("app.features.auth.jobs.one_time_repo.invalidate_unused", invalidate)
    monkeypatch.setattr("app.features.auth.jobs.one_time_repo.create", create)
    monkeypatch.setattr("app.features.auth.jobs.get_sender", lambda: Sender())
    return sent, tokens


async def test_send_token_email_verify_and_reset(email_env):
    from app.features.auth import jobs as auth_jobs
    from app.features.auth.schemas import SendTokenEmailPayload

    sent, tokens = email_env
    out = await auth_jobs.send_token_email(
        _ctx(), SendTokenEmailPayload(user_id="u1", purpose=TokenPurpose.VERIFY_EMAIL)
    )
    assert out == {"sent": True}
    assert len(sent) == 1 and "verify-email?token=" in sent[0][2]
    assert tokens[0][0] == "invalidate"

    out = await auth_jobs.send_token_email(
        _ctx(), SendTokenEmailPayload(user_id="u1", purpose=TokenPurpose.RESET_PASSWORD)
    )
    assert "reset-password?token=" in sent[1][2]


async def test_send_token_email_skips_inactive(email_env, monkeypatch):
    from app.features.auth import jobs as auth_jobs
    from app.features.auth.schemas import SendTokenEmailPayload

    sent, tokens = email_env

    async def inactive(uid):
        u = _user()
        u.is_active = False
        return u

    monkeypatch.setattr("app.features.auth.jobs.users_repo.get", inactive)
    out = await auth_jobs.send_token_email(
        _ctx(), SendTokenEmailPayload(user_id="u1", purpose=TokenPurpose.VERIFY_EMAIL)
    )
    assert out is None and sent == []


# --- notes jobs: export ------------------------------------------------------


async def test_export_notes_pages_until_done(monkeypatch):
    from prisma.models import Note

    from app.core.constants import Pagination
    from app.features.notes import jobs as notes_jobs

    def _note(i):
        return Note(
            id=f"n{i}",
            user_id="u1",
            title=f"T{i}",
            body="B",
            version=1,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

    calls: list = []
    full_page = [_note(i) for i in range(Pagination.MAX_SIZE)]  # exactly one full page
    last_page = [_note(999)]
    pages = [full_page, last_page]

    async def list_for_user(uid, params):
        calls.append(params.page)
        return pages[len(calls) - 1], Pagination.MAX_SIZE + 1

    monkeypatch.setattr(notes_jobs.notes_repo, "list_for_user", list_for_user)
    out = await notes_jobs.export_notes(_ctx())
    assert out["count"] == Pagination.MAX_SIZE + 1 and "# T999" in out["markdown"]
    assert calls == [1, 2]


# --- users jobs: erase + export ----------------------------------------------


async def test_account_erase_scrubs_and_audits(monkeypatch, audit_sink):
    from app.features.users import jobs as users_jobs

    deleted: list = []
    scrubbed: list = []

    async def get(uid):
        return _user()

    async def delete(uid):
        deleted.append(uid)

    async def scrub(actor_id):
        scrubbed.append(("audit", actor_id))
        return 1

    async def scrub_ip(user_id):
        scrubbed.append(("activity", user_id))
        return 2

    monkeypatch.setattr(users_jobs.users_repo, "get", get)
    monkeypatch.setattr(users_jobs.users_repo, "delete", delete)
    monkeypatch.setattr(users_jobs.audit_repo, "scrub_pii_for_actor", scrub)
    monkeypatch.setattr(users_jobs.activity_repo, "scrub_ip_for_user", scrub_ip)

    out = await users_jobs.account_erase(_ctx("u1"))
    assert out == {"deleted": True}
    assert deleted == ["u1"] and scrubbed == [("audit", "u1"), ("activity", "u1")]
    assert any(e["action"] == "account.erase" for e in audit_sink.entries)


async def test_account_erase_missing_user_is_noop(monkeypatch, audit_sink):
    from app.features.users import jobs as users_jobs

    async def get(uid):
        return None

    async def scrub(actor_id):
        return 0

    async def scrub_ip(user_id):
        return 0

    monkeypatch.setattr(users_jobs.users_repo, "get", get)
    monkeypatch.setattr(users_jobs.audit_repo, "scrub_pii_for_actor", scrub)
    monkeypatch.setattr(users_jobs.activity_repo, "scrub_ip_for_user", scrub_ip)
    assert await users_jobs.account_erase(_ctx("ghost")) == {"deleted": False}  # truthful result

    # no user_id at all => pure no-op
    assert await users_jobs.account_erase(_ctx(None)) == {"deleted": False}


async def test_account_erase_without_user_id(monkeypatch):
    from app.features.users import jobs as users_jobs

    assert await users_jobs.account_erase(_ctx(None)) == {"deleted": False}


async def test_account_export_builds_bundle(monkeypatch):
    from app.features.users import jobs as users_jobs

    async def get(uid):
        return _user()

    async def paginate(params, where=None, order=None):
        return [SimpleNamespace(title="T1")], 1

    async def audit_page(params, where=None, order=None):
        return [SimpleNamespace(action="note.create"), SimpleNamespace(action="auth.login")], 2

    monkeypatch.setattr(users_jobs.users_repo, "get", get)
    monkeypatch.setattr("app.features.notes.repository.notes_repo.paginate", paginate)
    monkeypatch.setattr(users_jobs.audit_repo, "paginate", audit_page)

    out = await users_jobs.account_export(_ctx("u1"))
    assert out["profile"]["id"] == "u1"
    assert out["notes"] == ["T1"]
    assert out["audit"] == ["note.create", "auth.login"]


async def test_account_export_without_user_id(monkeypatch):
    from app.features.users import jobs as users_jobs

    assert await users_jobs.account_export(_ctx(None)) == {
        "profile": None,
        "notes": [],
        "audit": [],
    }


async def test_account_export_unknown_user(monkeypatch):
    from app.features.users import jobs as users_jobs

    async def get(uid):
        return None

    monkeypatch.setattr(users_jobs.users_repo, "get", get)
    out = await users_jobs.account_export(_ctx("ghost"))
    assert out == {"profile": None, "notes": [], "audit": []}


# --- maintenance jobs --------------------------------------------------------


async def test_maintenance_handlers(monkeypatch, audit_sink):
    from app.features.maintenance import jobs as maint_jobs

    async def purge_before(cutoff):
        return 5

    deleted: list = []

    async def purge_jobs(cutoff):
        deleted.append(cutoff)
        return 2

    async def refresh_purge(cutoff):
        return 1

    async def one_time_purge(cutoff):
        return 2

    async def idem_purge():
        return 3

    monkeypatch.setattr(maint_jobs.activity_repo, "purge_before", purge_before)
    monkeypatch.setattr(maint_jobs.audit_repo, "purge_before", purge_before)
    monkeypatch.setattr(maint_jobs.settings, "audit_retention_days", 30)
    store = SimpleNamespace(purge_finished_before=purge_jobs)
    monkeypatch.setattr(maint_jobs, "get_store", lambda: store)
    monkeypatch.setattr(maint_jobs.refresh_repo, "purge", refresh_purge)
    monkeypatch.setattr(maint_jobs.one_time_repo, "purge", one_time_purge)
    monkeypatch.setattr(maint_jobs, "purge_expired", idem_purge)

    async def grants_purge():
        return 4

    monkeypatch.setattr(
        "app.features.permissions.service.permission_grant_repo.purge_expired", grants_purge
    )

    out = await maint_jobs.purge_logs(_ctx())
    assert out == {"activity_deleted": 5, "audit_deleted": 5}
    assert any(e["action"] == "retention.purge" for e in audit_sink.entries)

    out = await maint_jobs.purge_jobs(_ctx())
    assert out == {"deleted": 2}

    out = await maint_jobs.purge_expired_tokens(_ctx())
    assert out == {"refresh": 1, "one_time": 2, "idempotency": 3, "grants": 4}


async def test_purge_logs_keeps_audit_forever(monkeypatch, audit_sink):
    from app.features.maintenance import jobs as maint_jobs

    async def purge_before(cutoff):
        return 1

    audit_calls: list = []

    async def audit_purge(cutoff):
        audit_calls.append(cutoff)
        return 0

    monkeypatch.setattr(maint_jobs.activity_repo, "purge_before", purge_before)
    monkeypatch.setattr(maint_jobs.audit_repo, "purge_before", audit_purge)
    monkeypatch.setattr(maint_jobs.settings, "audit_retention_days", 0)  # 0 = keep forever

    out = await maint_jobs.purge_logs(_ctx())
    assert out["audit_deleted"] == 0 and audit_calls == []


# --- MCP: scoped tools + key gate -------------------------------------------


async def test_scoped_tool_wrapper(monkeypatch):
    from app.core.context import mcp_client_var
    from app.core.mcp import _scoped

    calls: list = []

    async def tool(x):
        calls.append(x)
        return x * 2

    wrapped = _scoped(tool)

    mcp_client_var.set(None)  # open client
    assert await wrapped(3) == 6

    monkeypatch.setattr(
        "app.core.mcp.settings.mcp_clients",
        [SimpleNamespace(name="cli", tools=["other_tool"])],
    )
    mcp_client_var.set("cli")
    with pytest.raises(PermissionError):
        await wrapped(3)

    monkeypatch.setattr(
        "app.core.mcp.settings.mcp_clients",
        [SimpleNamespace(name="cli", tools=["*"])],
    )
    assert await wrapped(4) == 8
    assert calls == [3, 4]


def test_client_tools_unknown_and_none():
    from app.core.mcp import _client_tools

    assert _client_tools(None) is None


async def test_api_key_gate(monkeypatch):
    from hashlib import sha256

    from app.core.context import mcp_client_var
    from app.core.mcp import ApiKeyGate

    reached: list = []

    async def downstream(scope, receive, send):
        reached.append(mcp_client_var.get())

    gate = ApiKeyGate(downstream)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    async def send_collect(message):
        sent.append(message)

    # no clients configured in dev -> open passthrough
    monkeypatch.setattr("app.core.mcp.settings.mcp_clients", [])
    monkeypatch.setattr("app.core.mcp.settings.env", "dev")
    await gate({"type": "http", "headers": []}, receive, send)
    assert reached[-1] is None

    # no clients in prod -> 401
    monkeypatch.setattr("app.core.mcp.settings.env", "prod")
    sent: list = []
    await gate({"type": "http", "headers": []}, receive, send_collect)
    assert sent[0]["status"] == 401

    # with clients: wrong key -> 401; right key -> sets the client and passes
    key = "supersecret"
    monkeypatch.setattr(
        "app.core.mcp.settings.mcp_clients",
        [SimpleNamespace(name="cli", key_sha256=sha256(key.encode()).hexdigest(), tools=["*"])],
    )
    monkeypatch.setattr("app.core.mcp.settings.env", "dev")
    sent.clear()
    await gate(
        {"type": "http", "headers": [(b"authorization", b"Bearer wrong")]}, receive, send_collect
    )
    assert sent[0]["status"] == 401

    await gate(
        {"type": "http", "headers": [(b"authorization", f"Bearer {key}".encode())]},
        receive,
        send_collect,
    )
    assert reached[-1] == "cli"

    # non-http scope: passthrough to the app without any auth check
    mcp_client_var.set(None)
    reached.clear()
    await gate({"type": "lifespan"}, receive, send)
    assert reached == [None]  # downstream ran; no client was resolved
