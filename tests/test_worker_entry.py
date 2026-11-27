"""`python -m app.worker` entrypoint: the __main__ guard runs main() end to end (fake infra)."""

import asyncio
import runpy

import pytest


class _FakeLoop:
    def add_signal_handler(self, sig, callback):  # noqa: ANN001
        pass


class _FakeWorker:
    def __init__(self, store):
        self.store = store

    async def run(self, stop):  # noqa: ANN001
        return None


@pytest.fixture
def fake_worker_infra(monkeypatch):
    calls: list[str] = []

    async def connect():
        calls.append("connect")

    async def disconnect():
        calls.append("disconnect")

    async def close_cache():
        calls.append("close_cache")

    monkeypatch.setattr("app.core.logging.configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(
        "app.core.discovery.feature_modules", lambda name: calls.append(f"modules:{name}") or []
    )
    monkeypatch.setattr("app.core.database.connect_db", connect)
    monkeypatch.setattr("app.core.database.disconnect_db", disconnect)
    monkeypatch.setattr("app.core.cache.close_cache", close_cache)
    monkeypatch.setattr("app.core.jobs.Worker", _FakeWorker)
    monkeypatch.setattr("app.core.jobs.get_store", lambda: object())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
    return calls


def test_module_entrypoint_runs_main(fake_worker_infra):
    calls = fake_worker_infra
    # Executes app/worker.py with __name__ == "__main__": the guard calls asyncio.run(main()).
    runpy.run_module("app.worker", run_name="__main__")
    assert "connect" in calls
    assert "close_cache" in calls and "disconnect" in calls  # the finally block ran
    assert calls.index("close_cache") < calls.index("disconnect")
