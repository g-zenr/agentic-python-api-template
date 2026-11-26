"""Job store: the data layer for the queue. `PrismaJobStore` is the production implementation.

The `JobStore` Protocol is the seam: tests swap in a `FakeJobStore`, and a future broker swap
reimplements this protocol without touching the worker or the feature. All queries go through
`current_db()` so enqueueing inside a mutation is atomic with it.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Protocol

import prisma
from app.core.constants import TERMINAL_JOB_STATUSES, JobStatus
from app.core.jobs.types import JobRecord
from app.core.messages import Msg
from app.core.uow import current_db
from app.shared.helpers.pagination import PageParams
from app.shared.utils.time import utcnow


class JobStore(Protocol):
    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        user_id: str | None,
        request_id: str | None,
        max_attempts: int,
        run_at: datetime,
        dedupe_key: str | None,
        priority: int,
    ) -> tuple[JobRecord, bool]: ...
    async def claim(self, worker_id: str, types: list[str], limit: int) -> list[JobRecord]: ...
    async def heartbeat(self, job_id: str) -> None: ...
    async def set_progress(self, job_id: str, percent: int) -> None: ...
    async def is_cancel_requested(self, job_id: str) -> bool: ...
    async def succeed(self, job_id: str, result: dict | None) -> None: ...
    async def fail(self, job_id: str, error: Msg, *, retry_at: datetime | None) -> None: ...
    async def cancelled(self, job_id: str) -> None: ...
    async def reap_stale(self, stale_seconds: int) -> int: ...
    async def get(self, job_id: str) -> JobRecord | None: ...
    async def list_for_user(
        self, user_id: str, params: PageParams, status: JobStatus | None
    ) -> tuple[list[JobRecord], int]: ...
    async def cancel_queued(self, job_id: str) -> bool: ...
    async def request_cancel(self, job_id: str) -> None: ...
    async def purge_finished_before(self, cutoff: datetime) -> int: ...
    async def queue_stats(self) -> dict[str, Any]: ...


class PrismaJobStore:
    def __init__(self, delegate: Any = None):
        self._delegate = delegate

    @property
    def d(self) -> Any:
        return self._delegate or current_db().job

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        user_id: str | None,
        request_id: str | None,
        max_attempts: int,
        run_at: datetime,
        dedupe_key: str | None,
        priority: int,
    ) -> tuple[JobRecord, bool]:
        client = current_db()
        sql = (
            "INSERT INTO jobs (id, type, status, payload, max_attempts, run_at, dedupe_key, "
            "priority, user_id, request_id, attempts, progress, cancel_requested, created_at, updated_at) "  # noqa: E501
            "VALUES (gen_random_uuid(), $1, 'QUEUED'::\"JobStatus\", $2::jsonb, $3, $4, $5, $6, $7, "  # noqa: E501
            "$8, 0, 0, false, now(), now()) "
            "ON CONFLICT (dedupe_key) DO NOTHING RETURNING *;"
        )
        rows = await client.query_raw(
            sql,
            type,
            json.dumps(payload),
            max_attempts,
            run_at,
            dedupe_key,
            priority,
            user_id,
            request_id,
        )
        if rows:
            return JobRecord.from_row(rows[0]), True
        existing = await client.query_raw("SELECT * FROM jobs WHERE dedupe_key = $1;", dedupe_key)
        return JobRecord.from_row(existing[0]), False

    async def claim(self, worker_id: str, types: list[str], limit: int) -> list[JobRecord]:
        if not types or limit <= 0:
            return []
        placeholders = ", ".join(f"${i + 2}" for i in range(len(types)))
        limit_param = f"${len(types) + 2}"
        sql = (
            "UPDATE jobs SET status = 'RUNNING'::\"JobStatus\", locked_by = $1, heartbeat_at = now(), "  # noqa: E501
            "started_at = COALESCE(started_at, now()), attempts = attempts + 1, updated_at = now() "
            "WHERE id IN ("
            "SELECT id FROM jobs WHERE status = 'QUEUED'::\"JobStatus\" AND run_at <= now() "
            f"AND type IN ({placeholders}) "
            "ORDER BY priority DESC, run_at ASC FOR UPDATE SKIP LOCKED "
            f"LIMIT {limit_param}) RETURNING *;"
        )
        rows = await current_db().query_raw(sql, worker_id, *types, limit)
        return [JobRecord.from_row(r) for r in rows]

    async def heartbeat(self, job_id: str) -> None:
        await self.d.update(where={"id": job_id}, data={"heartbeat_at": utcnow()})

    async def set_progress(self, job_id: str, percent: int) -> None:
        await self.d.update(where={"id": job_id}, data={"progress": percent})

    async def is_cancel_requested(self, job_id: str) -> bool:
        row = await self.d.find_unique(where={"id": job_id})
        return bool(row and row.cancel_requested)

    async def succeed(self, job_id: str, result: dict | None) -> None:
        await self.d.update(
            where={"id": job_id},
            data={
                "status": JobStatus.SUCCEEDED.value,
                "progress": 100,
                "result": prisma.Json(result) if result is not None else None,
                "finished_at": utcnow(),
                "locked_by": None,
            },
        )

    async def fail(self, job_id: str, error: Msg, *, retry_at: datetime | None) -> None:
        if retry_at is not None:
            data = {
                "status": JobStatus.QUEUED.value,
                "run_at": retry_at,
                "locked_by": None,
                "error": error.value,
            }
        else:
            data = {
                "status": JobStatus.FAILED.value,
                "error": error.value,
                "finished_at": utcnow(),
                "locked_by": None,
            }
        await self.d.update(where={"id": job_id}, data=data)

    async def cancelled(self, job_id: str) -> None:
        await self.d.update(
            where={"id": job_id},
            data={"status": JobStatus.CANCELLED.value, "finished_at": utcnow(), "locked_by": None},
        )

    async def reap_stale(self, stale_seconds: int) -> int:
        sql = (
            "UPDATE jobs SET status = CASE WHEN attempts >= max_attempts THEN 'FAILED'::\"JobStatus\" "  # noqa: E501
            "ELSE 'QUEUED'::\"JobStatus\" END, error = $2, locked_by = NULL, "
            "finished_at = CASE WHEN attempts >= max_attempts THEN now() ELSE NULL END, updated_at = now() "  # noqa: E501
            "WHERE status = 'RUNNING'::\"JobStatus\" "
            "AND heartbeat_at < now() - make_interval(secs => $1);"
        )
        return await current_db().execute_raw(sql, stale_seconds, Msg.INTERNAL_ERROR.value)

    async def get(self, job_id: str) -> JobRecord | None:
        row = await self.d.find_unique(where={"id": job_id})
        return JobRecord.from_row(row) if row else None

    async def list_for_user(
        self, user_id: str, params: PageParams, status: JobStatus | None
    ) -> tuple[list[JobRecord], int]:
        where: dict[str, Any] = {"user_id": user_id}
        if status is not None:
            where["status"] = status.value
        items, total = await asyncio.gather(
            self.d.find_many(
                where=where, skip=params.skip, take=params.take, order={"created_at": "desc"}
            ),
            self.d.count(where=where),
        )
        return [JobRecord.from_row(i) for i in items], total

    async def cancel_queued(self, job_id: str) -> bool:
        result = await self.d.update_many(
            where={"id": job_id, "status": JobStatus.QUEUED.value},
            data={"status": JobStatus.CANCELLED.value, "finished_at": utcnow()},
        )
        return result == 1

    async def request_cancel(self, job_id: str) -> None:
        await self.d.update(where={"id": job_id}, data={"cancel_requested": True})

    async def purge_finished_before(self, cutoff: datetime) -> int:
        result = await self.d.delete_many(
            where={
                "status": {"in": [s.value for s in TERMINAL_JOB_STATUSES]},
                "finished_at": {"lt": cutoff},
            }
        )
        return result

    async def queue_stats(self) -> dict[str, Any]:
        rows = await current_db().query_raw(
            "SELECT status::text AS status, count(*) AS count FROM jobs GROUP BY status;"
        )
        oldest = await current_db().query_raw(
            "SELECT EXTRACT(EPOCH FROM (now() - min(run_at))) AS age "
            "FROM jobs WHERE status = 'QUEUED'::\"JobStatus\";"
        )
        return {
            "depth": {r["status"]: int(r["count"]) for r in rows},
            "oldest_queued_age": float(oldest[0]["age"]) if oldest and oldest[0]["age"] else 0.0,
        }


_store: JobStore = PrismaJobStore()


def get_store() -> JobStore:
    return _store


def set_store(store: JobStore) -> None:
    global _store
    _store = store
