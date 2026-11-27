"""Job engine tests via execute() + FakeJobStore (no DB, no worker loop)."""

import asyncio
from datetime import timedelta

import pytest
from pydantic import BaseModel

from app.core.constants import JobPolicy, JobStatus, JobType
from app.core.jobs import registry
from app.core.jobs.registry import Handler
from app.core.jobs.types import PermanentError
from app.core.jobs.worker import Worker, backoff_seconds, execute
from app.core.messages import Msg
from app.shared.utils.time import utcnow


@pytest.fixture
def handlers():
    saved = dict(registry._handlers)
    yield registry._handlers
    registry._handlers.clear()
    registry._handlers.update(saved)


def _handler(fn, *, timeout=JobPolicy.DEFAULT_TIMEOUT, max_attempts=3, payload=None):
    return Handler(
        job_type=JobType.NOTES_EXPORT,
        fn=fn,
        payload_model=payload,
        timeout=timeout,
        max_attempts=max_attempts,
        schedule_every=None,
    )


async def _enqueue(store, jtype, payload=None, max_attempts=3):
    job, _ = await store.enqueue(
        type=jtype.value,
        payload=payload or {},
        user_id="u1",
        request_id="r",
        max_attempts=max_attempts,
        run_at=utcnow(),
        dedupe_key=None,
        priority=0,
    )
    return job


async def test_success_stores_result_and_progress(handlers, fake_store):
    async def ok(ctx):
        await ctx.progress(50)
        return {"ok": 1}

    handlers[JobType.NOTES_EXPORT] = _handler(ok)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    claimed = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(claimed[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.SUCCEEDED.value
    assert final.result == {"ok": 1}
    assert final.progress == 100


async def test_crash_retries_then_fails(handlers, fake_store):
    async def boom(ctx):
        raise RuntimeError("x")

    handlers[JobType.NOTES_EXPORT] = _handler(boom, max_attempts=2)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT, max_attempts=2)
    # first attempt -> requeued
    c1 = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c1[0], fake_store)
    assert (await fake_store.get(job.id)).status == JobStatus.QUEUED.value
    fake_store._run_at[job.id] = utcnow()  # make the retry due now
    # second attempt -> failed
    c2 = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c2[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.FAILED.value
    assert final.error == Msg.INTERNAL_ERROR.value


async def test_permanent_error_no_retry(handlers, fake_store):
    async def bad(ctx):
        raise PermanentError(Msg.JOB_UNKNOWN_TYPE)

    handlers[JobType.NOTES_EXPORT] = _handler(bad)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    c = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.FAILED.value
    assert final.error == Msg.JOB_UNKNOWN_TYPE.value


async def test_timeout_retries(handlers, fake_store):
    async def slow(ctx):
        await asyncio.sleep(5)

    handlers[JobType.NOTES_EXPORT] = _handler(slow, timeout=0.05)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    c = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.QUEUED.value
    assert final.error == Msg.JOB_TIMEOUT.value


async def test_oversize_result_fails(handlers, fake_store):
    async def big(ctx):
        return {"blob": "x" * (JobPolicy.RESULT_MAX_BYTES + 10)}

    handlers[JobType.NOTES_EXPORT] = _handler(big)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    c = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.FAILED.value
    assert final.error == Msg.JOB_RESULT_TOO_LARGE.value


async def test_cancel_stops_job(handlers, fake_store):
    async def loop(ctx):
        await ctx.raise_if_cancelled()
        return {"done": True}

    handlers[JobType.NOTES_EXPORT] = _handler(loop)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    await fake_store.request_cancel(job.id)
    c = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c[0], fake_store)
    assert (await fake_store.get(job.id)).status == JobStatus.CANCELLED.value


async def test_invalid_payload_fails_without_retry(handlers, fake_store):
    class P(BaseModel):
        n: int

    async def h(ctx, p: P):
        return {"n": p.n}

    handlers[JobType.NOTES_EXPORT] = _handler(h, payload=P)
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT, payload={"n": "not-int"})
    c = await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    await execute(c[0], fake_store)
    final = await fake_store.get(job.id)
    assert final.status == JobStatus.FAILED.value
    assert final.error == Msg.VALIDATION_ERROR.value


def test_backoff_grows_and_caps():
    assert backoff_seconds(1) < backoff_seconds(3)
    assert backoff_seconds(100) <= JobPolicy.BACKOFF_MAX * 1.2


async def test_scheduler_dedupes_across_workers(fake_store):
    w = Worker(fake_store)
    await w._schedule()
    await w._schedule()  # second worker, same bucket
    schedule_keys = [k for k in fake_store._by_dedupe if "schedule" in k]
    # one job per scheduled type, not doubled by the second worker
    assert len(schedule_keys) == len(set(schedule_keys))
    assert len(fake_store.jobs) == len(schedule_keys)


async def test_reaper_requeues_stale(fake_store):
    job = await _enqueue(fake_store, JobType.NOTES_EXPORT)
    await fake_store.claim("w", [JobType.NOTES_EXPORT.value], 1)
    fake_store._heartbeat[job.id] = utcnow() - timedelta(seconds=1000)
    reaped = await fake_store.reap_stale(120)
    assert reaped == 1
    assert (await fake_store.get(job.id)).status == JobStatus.QUEUED.value


def test_registry_handlers_match_jobtypes():
    from app.core.discovery import feature_modules

    feature_modules("jobs")
    assert set(registry.handlers()) == set(JobType)
