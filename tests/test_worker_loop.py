"""Worker loop: poll/claim/drain, maintenance (queue gauges + stale reap), and the scheduler."""

import asyncio
from datetime import timedelta

from app.core import metrics
from app.core.constants import JobPolicy
from app.core.discovery import feature_modules
from app.core.jobs import Worker, set_store
from app.shared.utils.time import utcnow
from tests.fakes import FakeJobStore

feature_modules("jobs")  # register every @job_handler (incl. scheduled maintenance ones)


class _StatsStore(FakeJobStore):
    """FakeJobStore with non-empty queue stats to exercise the gauge labels."""

    async def queue_stats(self):
        return {"depth": {"QUEUED": 2, "RUNNING": 1}, "oldest_queued_age": 12.5}


async def test_maintenance_publishes_queue_gauges(monkeypatch):
    store = _StatsStore()
    set_store(store)
    worker = Worker(store)
    await worker._maintenance()
    text = metrics.render_metrics()[0].decode()
    assert 'jobs_queue_depth{status="QUEUED"} 2.0' in text
    assert 'jobs_queue_depth{status="RUNNING"} 1.0' in text
    assert "jobs_oldest_queued_age_seconds 12.5" in text


async def test_maintenance_reaps_stale_running_jobs(monkeypatch):
    monkeypatch.setattr("app.core.jobs.worker.settings.job_stale_seconds", 30)
    store = FakeJobStore()
    set_store(store)
    job, _ = await store.enqueue(
        type="notes.export",
        payload={},
        user_id="u1",
        request_id=None,
        max_attempts=1,
        run_at=utcnow(),
        dedupe_key=None,
        priority=0,
    )
    job.status = "RUNNING"
    job.attempts = 1  # as if claimed once by a worker that then stalled
    store._heartbeat[job.id] = utcnow() - timedelta(seconds=120)  # far past the stale window
    worker = Worker(store)
    await worker._maintenance()
    assert job.status == "FAILED"  # attempts(1) >= max_attempts(1) => failed, not requeued


async def test_schedule_enqueues_scheduled_handlers_with_dedupe():
    store = FakeJobStore()
    set_store(store)
    worker = Worker(store)
    await worker._schedule()
    scheduled = [j for j in store.jobs.values() if j.request_id is None]
    assert scheduled, "scheduled handlers must enqueue system jobs"
    assert store._by_dedupe, "scheduler must dedupe per bucket (dedupe keys recorded)"
    before = {j.id for j in store.jobs.values()}
    await worker._schedule()  # same bucket => deduped
    assert {j.id for j in store.jobs.values()} == before


async def test_run_with_already_set_stop_exits_immediately():
    store = FakeJobStore()
    set_store(store)
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(Worker(store).run(stop), timeout=2)


async def test_run_loop_claims_polls_and_drains(monkeypatch):
    monkeypatch.setattr("app.core.jobs.worker.settings.worker_poll_seconds", 0.05)
    monkeypatch.setattr("app.core.jobs.worker.settings.job_stale_seconds", 30)
    store = FakeJobStore()
    set_store(store)
    worker = Worker(store)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.15)  # a few loop iterations (empty claim => poll wait)
    stop.set()
    await asyncio.wait_for(task, timeout=3)
    assert not worker._running


async def test_backoff_seconds_bounds():
    from app.core.jobs.worker import backoff_seconds

    assert backoff_seconds(1) >= 0
    assert backoff_seconds(50) <= JobPolicy.BACKOFF_MAX * 1.2 + 0.001
