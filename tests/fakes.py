"""In-memory test doubles: a full JobStore, and list sinks for audit/activity."""

import uuid
from datetime import datetime, timedelta

from app.core.constants import TERMINAL_JOB_STATUSES, JobStatus
from app.core.jobs.types import JobRecord
from app.core.messages import Msg
from app.shared.helpers.pagination import PageParams
from app.shared.utils.time import utcnow


class FakeJobStore:
    """In-memory implementation of the full JobStore protocol (no database)."""

    def __init__(self):
        self.jobs: dict[str, JobRecord] = {}
        self._by_dedupe: dict[str, str] = {}
        self._run_at: dict[str, datetime] = {}
        self._priority: dict[str, int] = {}
        self._locked_by: dict[str, str] = {}
        self._heartbeat: dict[str, datetime] = {}

    async def enqueue(
        self, *, type, payload, user_id, request_id, max_attempts, run_at, dedupe_key, priority
    ):
        if dedupe_key and dedupe_key in self._by_dedupe:
            return self.jobs[self._by_dedupe[dedupe_key]], False
        now = utcnow()
        job = JobRecord(
            id=uuid.uuid4().hex,
            type=type,
            status=JobStatus.QUEUED.value,
            payload=payload,
            result=None,
            error=None,
            progress=0,
            attempts=0,
            max_attempts=max_attempts,
            user_id=user_id,
            request_id=request_id,
            cancel_requested=False,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=None,
        )
        self.jobs[job.id] = job
        self._run_at[job.id] = run_at
        self._priority[job.id] = priority
        if dedupe_key:
            self._by_dedupe[dedupe_key] = job.id
        return job, True

    async def claim(self, worker_id, types, limit):
        now = utcnow()
        candidates = [
            j
            for j in self.jobs.values()
            if j.status == JobStatus.QUEUED.value and j.type in types and self._run_at[j.id] <= now
        ]
        candidates.sort(key=lambda j: (-self._priority[j.id], self._run_at[j.id]))
        claimed = candidates[:limit]
        for j in claimed:
            j.status = JobStatus.RUNNING.value
            self._locked_by[j.id] = worker_id
            self._heartbeat[j.id] = now
            j.started_at = j.started_at or now
            j.attempts += 1
            j.updated_at = now
        return claimed

    async def heartbeat(self, job_id):
        self._heartbeat[job_id] = utcnow()

    async def set_progress(self, job_id, percent):
        self.jobs[job_id].progress = percent

    async def is_cancel_requested(self, job_id):
        return self.jobs[job_id].cancel_requested

    async def succeed(self, job_id, result):
        j = self.jobs[job_id]
        j.status = JobStatus.SUCCEEDED.value
        j.progress = 100
        j.result = result
        j.finished_at = utcnow()
        self._locked_by.pop(job_id, None)

    async def fail(self, job_id, error, *, retry_at):
        j = self.jobs[job_id]
        j.error = error.value
        self._locked_by.pop(job_id, None)
        if retry_at is not None:
            j.status = JobStatus.QUEUED.value
            self._run_at[j.id] = retry_at
        else:
            j.status = JobStatus.FAILED.value
            j.finished_at = utcnow()

    async def cancelled(self, job_id):
        j = self.jobs[job_id]
        j.status = JobStatus.CANCELLED.value
        j.finished_at = utcnow()
        self._locked_by.pop(job_id, None)

    async def reap_stale(self, stale_seconds):
        cutoff = utcnow() - timedelta(seconds=stale_seconds)
        n = 0
        for j in self.jobs.values():
            hb = self._heartbeat.get(j.id)
            if j.status == JobStatus.RUNNING.value and hb and hb < cutoff:
                j.error = Msg.INTERNAL_ERROR.value
                self._locked_by.pop(j.id, None)
                if j.attempts >= j.max_attempts:
                    j.status = JobStatus.FAILED.value
                    j.finished_at = utcnow()
                else:
                    j.status = JobStatus.QUEUED.value
                n += 1
        return n

    async def get(self, job_id):
        return self.jobs.get(job_id)

    async def list_for_user(self, user_id, params: PageParams, status):
        items = [
            j
            for j in self.jobs.values()
            if j.user_id == user_id and (status is None or j.status == status.value)
        ]
        items.sort(key=lambda j: j.created_at, reverse=True)
        total = len(items)
        start = params.skip
        return items[start : start + params.take], total

    async def cancel_queued(self, job_id):
        j = self.jobs[job_id]
        if j.status != JobStatus.QUEUED.value:
            return False
        j.status = JobStatus.CANCELLED.value
        j.finished_at = utcnow()
        return True

    async def request_cancel(self, job_id):
        self.jobs[job_id].cancel_requested = True

    async def queue_stats(self):
        return {"depth": {}, "oldest_queued_age": 0.0}

    async def purge_finished_before(self, cutoff):
        remove = [
            k
            for k, j in self.jobs.items()
            if j.status in {s.value for s in TERMINAL_JOB_STATUSES}
            and j.finished_at
            and j.finished_at < cutoff
        ]
        for k in remove:
            del self.jobs[k]
        return len(remove)


class ListAuditSink:
    """Collects audit entries in a list."""

    def __init__(self):
        self.entries: list[dict] = []

    async def append(self, entry: dict) -> None:
        self.entries.append(entry)


class ListActivitySink:
    """Collects activity batches; can be told to fail to exercise the drop path."""

    def __init__(self, fail: bool = False):
        self.batches: list[list[dict]] = []
        self.fail = fail

    async def append_many(self, entries: list[dict]) -> int:
        if self.fail:
            raise RuntimeError("sink down")
        self.batches.append(entries)
        return len(entries)
