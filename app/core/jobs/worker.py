"""Worker: claims jobs, runs handlers (timeout/heartbeat/retry), reaps stale jobs, schedules."""

import asyncio
import contextlib
import logging
import random
import socket
import time
import uuid
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.core.constants import ActorType, JobPolicy
from app.core.context import RequestContext, request_ctx, request_id_var
from app.core.exceptions import AppError
from app.core.jobs import registry
from app.core.jobs.store import JobStore, claim_attempt
from app.core.jobs.types import JobCancelled, JobContext, JobRecord, PermanentError
from app.core.messages import Msg
from app.core.metrics import (
    job_duration_seconds,
    jobs_oldest_queued_age_seconds,
    jobs_processed_total,
    jobs_queue_depth,
)
from app.shared.utils import json as jsonx
from app.shared.utils.time import utcnow

log = logging.getLogger(__name__)


def backoff_seconds(attempts: int) -> float:
    base = min(JobPolicy.BACKOFF_BASE * 2 ** max(attempts - 1, 0), JobPolicy.BACKOFF_MAX)
    return float(base * random.uniform(0.8, 1.2))


def _bind_job_context(job: JobRecord) -> None:
    ctx = RequestContext(
        request_id=job.request_id or uuid.uuid4().hex,
        user_id=job.user_id,
        actor_type=ActorType.USER if job.user_id else ActorType.SYSTEM,
        job_id=job.id,
    )
    request_ctx.set(ctx)
    request_id_var.set(ctx.request_id)


async def _heartbeat(job_id: str, store: JobStore) -> None:
    while True:
        await asyncio.sleep(JobPolicy.HEARTBEAT_SECONDS)
        try:
            await store.heartbeat(job_id)
        except Exception:
            log.warning("heartbeat failed for job %s", job_id, exc_info=True)


async def _invoke(job: JobRecord, store: JobStore) -> dict[str, Any] | None:
    handler = registry.get_handler(job.type)
    ctx = JobContext(job, store)
    await ctx.raise_if_cancelled()
    args = (
        (ctx, handler.payload_model.model_validate(job.payload))
        if handler.payload_model
        else (ctx,)
    )
    async with asyncio.timeout(handler.timeout):
        result = await handler.fn(*args)
    await ctx.raise_if_cancelled()
    if result is not None and len(jsonx.dumps(result)) > JobPolicy.RESULT_MAX_BYTES:
        raise PermanentError(Msg.JOB_RESULT_TOO_LARGE)
    return result


async def _fail(job: JobRecord, store: JobStore, msg: Msg, *, retry: bool) -> None:
    retry_at = (
        utcnow() + timedelta(seconds=backoff_seconds(job.attempts))
        if retry and job.attempts < job.max_attempts
        else None
    )
    try:
        await store.fail(job.id, msg, retry_at=retry_at)
    except Exception:
        log.exception("failed to record failure for job %s", job.id)


async def execute(job: JobRecord, store: JobStore) -> None:
    """Run ONE claimed job to a terminal or retry state. Never raises (except task cancellation)."""
    _bind_job_context(job)
    attempt_token = claim_attempt.set(job.attempts)
    beat = asyncio.create_task(_heartbeat(job.id, store))
    started = time.perf_counter()
    outcome = "failed"
    try:
        result = await _invoke(job, store)
        await store.succeed(job.id, result)
        outcome = "succeeded"
    except JobCancelled:
        await store.cancelled(job.id)
        outcome = "cancelled"
    except AppError as exc:  # includes PermanentError: business failure, no retry
        await _fail(job, store, exc.msg, retry=False)
    except ValidationError:  # bad payload: no retry
        await _fail(job, store, Msg.VALIDATION_ERROR, retry=False)
    except TimeoutError:
        await _fail(job, store, Msg.JOB_TIMEOUT, retry=True)
    except Exception:  # details go to logs, NEVER to the client
        log.exception("job %s (%s) crashed", job.id, job.type)
        await _fail(job, store, Msg.INTERNAL_ERROR, retry=True)
    finally:
        beat.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await beat
        finally:
            claim_attempt.reset(attempt_token)
        jobs_processed_total.labels(type=job.type, outcome=outcome).inc()
        job_duration_seconds.labels(type=job.type).observe(time.perf_counter() - started)


class Worker:
    def __init__(self, store: JobStore, *, worker_id: str | None = None):
        self.store = store
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._running: set[asyncio.Task[None]] = set()
        self._last_reap = 0.0
        self._last_schedule = 0.0

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self._maintenance()
                free = settings.worker_concurrency - len(self._running)
                claimed: list[JobRecord] = []
                if free > 0:
                    claimed = await self.store.claim(
                        self.worker_id, [t.value for t in registry.handlers()], free
                    )
                for job in claimed:
                    task = asyncio.create_task(execute(job, self.store))
                    self._running.add(task)
                    task.add_done_callback(self._running.discard)
                if not claimed:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), settings.worker_poll_seconds)
            except Exception:
                log.exception("worker loop error")
                await asyncio.sleep(settings.worker_poll_seconds)
        if self._running:
            await asyncio.wait(list(self._running), timeout=JobPolicy.SHUTDOWN_GRACE)
        for task in list(self._running):
            task.cancel()

    async def _maintenance(self) -> None:
        now = time.monotonic()
        try:
            stats = await self.store.queue_stats()
            for status_name, count in stats.get("depth", {}).items():
                jobs_queue_depth.labels(status=status_name).set(count)
            jobs_oldest_queued_age_seconds.set(float(stats.get("oldest_queued_age", 0.0)))
        except Exception:
            log.exception("queue_stats failed")
        if now - self._last_reap > settings.job_stale_seconds / 2:
            self._last_reap = now
            try:
                reaped = await self.store.reap_stale(settings.job_stale_seconds)
                if reaped:
                    log.info("reaped %d stale job(s)", reaped)
            except Exception:
                log.exception("reap_stale failed")
        if now - self._last_schedule > JobPolicy.SCHEDULE_CHECK_SECONDS:
            self._last_schedule = now
            await self._schedule()

    async def _schedule(self) -> None:
        bucket = int(time.time())
        for handler in registry.handlers().values():
            if not handler.schedule_every:
                continue
            dedupe = (
                f"{JobPolicy.SYSTEM_SCOPE}:schedule:{handler.job_type.value}:"
                f"{bucket // handler.schedule_every}"
            )
            try:
                await self.store.enqueue(
                    type=handler.job_type.value,
                    payload={},
                    user_id=None,
                    request_id=None,
                    max_attempts=handler.max_attempts,
                    run_at=utcnow(),
                    dedupe_key=dedupe,
                    priority=0,
                )
            except Exception:
                log.exception("schedule enqueue failed for %s", handler.job_type)
