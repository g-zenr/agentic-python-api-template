"""app.main: lifespan wiring (fake infra), prod warnings, and the /metrics guard."""

import logging

import httpx
import pytest
from asgi_lifespan import LifespanManager
from pydantic import SecretStr

import app.main as main_mod
from app.main import app


class _FakeLoop:
    def add_signal_handler(self, sig, callback):  # noqa: ANN001
        pass


class _FakeWorker:
    def __init__(self, store):
        self.store = store

    async def run(self, stop):  # noqa: ANN001
        await stop.wait()


@pytest.fixture
def fake_infra(monkeypatch):
    calls: list[str] = []

    async def connect():
        calls.append("connect")

    async def disconnect():
        calls.append("disconnect")

    async def close_cache():
        calls.append("close_cache")

    class _Activity:
        async def start(self):
            calls.append("activity_start")

        async def stop(self):
            calls.append("activity_stop")

    monkeypatch.setattr(main_mod, "connect_db", connect)
    monkeypatch.setattr(main_mod, "disconnect_db", disconnect)
    monkeypatch.setattr(main_mod, "close_cache", close_cache)
    monkeypatch.setattr(main_mod, "activity", _Activity())
    monkeypatch.setattr(main_mod, "Worker", _FakeWorker)
    monkeypatch.setattr(main_mod, "get_store", lambda: object())
    monkeypatch.setattr(main_mod.settings, "worker_embedded", True)
    monkeypatch.setattr(main_mod.settings, "mcp_enabled", False)
    return calls


async def test_lifespan_wires_and_shuts_down_in_order(fake_infra):
    calls = fake_infra
    async with LifespanManager(app, startup_timeout=5, shutdown_timeout=5):
        assert calls == ["connect", "activity_start"]
    assert calls == ["connect", "activity_start", "activity_stop", "close_cache", "disconnect"]


async def test_lifespan_marks_shutting_down(fake_infra):
    app.state.shutting_down = False  # a previous test's shutdown may have left it True
    async with LifespanManager(app, startup_timeout=5, shutdown_timeout=5):
        assert app.state.shutting_down is False
    assert app.state.shutting_down is True


async def test_lifespan_worker_shutdown_waits_for_task(fake_infra, monkeypatch):
    """The embedded worker task is cancelled/awaited via _shutdown_worker on shutdown."""
    calls = fake_infra
    async with LifespanManager(app, startup_timeout=5, shutdown_timeout=5):
        pass
    assert "close_cache" in calls and "disconnect" in calls  # clean teardown


async def test_metrics_guard_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(main_mod.settings, "metrics_token", SecretStr("right"))
    monkeypatch.setattr(main_mod.settings, "metrics_enabled", True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/metrics", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
        r2 = await c.get("/metrics", headers={"Authorization": "Bearer right"})
        assert r2.status_code == 200


async def test_prod_memory_cache_warning(caplog, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "env", "prod")
    monkeypatch.setattr(main_mod.settings, "cache_backend", "memory")
    monkeypatch.setattr(main_mod.settings, "worker_embedded", False)
    monkeypatch.setattr(main_mod.settings, "mcp_enabled", False)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main_mod.create_app()
    assert any("cache backend is 'memory' in prod" in r.message for r in caplog.records)


def test_app_version_matches_settings():
    assert app.version == main_mod.settings.app_version
