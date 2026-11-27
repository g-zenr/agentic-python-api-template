"""Standalone worker process `app.worker.main` wiring (no real DB/signals)."""

import asyncio

import app.worker as worker_mod


class _FakeLoop:
    def add_signal_handler(self, sig, callback):  # noqa: ANN001
        pass


class _FakeWorker:
    def __init__(self, store):
        self.store = store

    async def run(self, stop):  # noqa: ANN001
        return None


async def test_main_wires_and_cleans_up(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(worker_mod, "configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(worker_mod, "feature_modules", lambda name: calls.append(f"modules:{name}"))

    async def connect():
        calls.append("connect")

    async def disconnect():
        calls.append("disconnect")

    async def close_cache():
        calls.append("close_cache")

    monkeypatch.setattr(worker_mod, "connect_db", connect)
    monkeypatch.setattr(worker_mod, "disconnect_db", disconnect)
    monkeypatch.setattr(worker_mod, "close_cache", close_cache)
    monkeypatch.setattr(worker_mod, "get_store", lambda: object())
    monkeypatch.setattr(worker_mod, "Worker", _FakeWorker)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())

    await worker_mod.main()

    assert "logging" in calls
    assert "modules:jobs" in calls
    assert "connect" in calls
    assert "disconnect" in calls  # finally
    assert "close_cache" in calls  # finally
    # order: cache closed before db disconnect in finally
    assert calls.index("close_cache") < calls.index("disconnect")
