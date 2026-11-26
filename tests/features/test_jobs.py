"""Jobs feature tests: ownership, cancel states, and the HTTP polling contract (ETag/304)."""

from types import SimpleNamespace

import httpx
import pytest

from app.core.constants import JobStatus, Role
from app.core.exceptions import ConflictError, NotFoundError
from app.core.jobs import set_store
from app.features.auth.deps import get_current_user
from app.features.jobs import service
from app.main import app


def _user(id="u1", role=Role.USER):
    return SimpleNamespace(id=id, role=role, is_active=True)


async def _enqueue(store, user_id="u1"):
    job, _ = await store.enqueue(
        type="notes.export",
        payload={},
        user_id=user_id,
        request_id="r",
        max_attempts=3,
        run_at=__import__("app.shared.utils.time", fromlist=["utcnow"]).utcnow(),
        dedupe_key=None,
        priority=0,
    )
    return job


async def test_owned_hides_other_users_job(fake_store):
    set_store(fake_store)
    job = await _enqueue(fake_store, user_id="other")
    with pytest.raises(NotFoundError):
        await service.get(_user("u1"), job.id)


async def test_admin_can_read_any_job(fake_store):
    set_store(fake_store)
    job = await _enqueue(fake_store, user_id="other")
    out = await service.get(_user("admin", Role.ADMIN), job.id)
    assert out.id == job.id


async def test_cancel_queued(fake_store, audit_sink):
    set_store(fake_store)
    job = await _enqueue(fake_store)
    out, msg = await service.cancel(_user(), job.id)
    assert out.status == JobStatus.CANCELLED
    assert msg.value == "job.cancelled"


async def test_cancel_running_requests(fake_store, audit_sink):
    set_store(fake_store)
    job = await _enqueue(fake_store)
    await fake_store.claim("w", ["notes.export"], 1)
    out, msg = await service.cancel(_user(), job.id)
    assert msg.value == "job.cancel_requested"


async def test_cancel_terminal_conflicts(fake_store, audit_sink):
    set_store(fake_store)
    job = await _enqueue(fake_store)
    await fake_store.succeed(job.id, {"ok": 1})
    with pytest.raises(ConflictError):
        await service.cancel(_user(), job.id)


@pytest.fixture
def client(fake_store):
    set_store(fake_store)
    app.dependency_overrides[get_current_user] = lambda: _user()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def test_http_poll_running_has_retry_after(client, fake_store):
    job = await _enqueue(fake_store)
    await fake_store.claim("w", ["notes.export"], 1)
    r = await client.get(f"/api/v1/jobs/{job.id}")
    assert r.status_code == 200
    assert "retry-after" in r.headers
    assert r.headers["cache-control"] == "private, no-cache"


async def test_http_poll_terminal_no_retry_after(client, fake_store):
    job = await _enqueue(fake_store)
    await fake_store.succeed(job.id, {"ok": 1})
    r = await client.get(f"/api/v1/jobs/{job.id}")
    assert r.status_code == 200
    assert "retry-after" not in r.headers


async def test_http_etag_304(client, fake_store):
    job = await _enqueue(fake_store)
    r1 = await client.get(f"/api/v1/jobs/{job.id}")
    etag = r1.headers["etag"]
    r2 = await client.get(f"/api/v1/jobs/{job.id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304
