"""Activity buffer: a best-effort, batched writer for every API request.

`record()` never blocks and never raises: when the queue is full it sheds load (drops) instead of
slowing requests. A background task drains the queue and bulk-inserts batches.
"""

import asyncio
import logging
import time
from typing import Any

from app.core.activity.repository import activity_repo
from app.core.config import settings
from app.core.constants import Activity
from app.core.metrics import activity_dropped_total
from app.shared.helpers.http import client_ip

log = logging.getLogger(__name__)


class ActivityBuffer:
    """Best-effort batched writer. record() never blocks and never raises."""

    def __init__(self, sink: Any = None) -> None:
        self._sink = sink or activity_repo
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=settings.activity_queue_max)
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self.dropped = 0

    def record(self, entry: dict[str, Any]) -> None:
        if not settings.activity_enabled:
            return
        try:
            self._q.put_nowait(entry)
        except asyncio.QueueFull:
            self.dropped += 1  # shed load instead of slowing requests
            activity_dropped_total.inc()

    def record_request(self, request: Any, ctx: Any, status_code: int, started: float) -> None:
        """Build + record an entry. Skips Activity.SKIP_PATHS and f"{api_prefix}/health"."""
        path = request.url.path
        skip = set(Activity.SKIP_PATHS) | {f"{settings.api_prefix}/health"}
        if any(path == s or path.startswith(s) for s in skip):
            return
        route = request.scope.get("route")
        entry = {
            "user_id": ctx.user_id,
            "method": request.method,
            "path": route.path if route else Activity.UNMATCHED,
            "status_code": status_code,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "request_id": ctx.request_id,
            "ip": ctx.ip if ctx.ip is not None else client_ip(request),
        }
        self.record(entry)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            await self._task
            self._task = None

    async def run(self) -> None:
        while not self._stopping or not self._q.empty():
            batch = await self._collect()
            if batch:
                await self._flush(batch)

    async def _collect(self) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        try:
            batch.append(await asyncio.wait_for(self._q.get(), settings.activity_flush_seconds))
        except TimeoutError:
            return batch
        while len(batch) < settings.activity_batch_size and not self._q.empty():
            batch.append(self._q.get_nowait())
        return batch

    async def _flush(self, batch: list[dict[str, Any]]) -> None:
        try:
            await self._sink.append_many(batch)
        except Exception:
            self.dropped += len(batch)
            activity_dropped_total.inc(len(batch))
            log.error("activity flush failed; dropped %d entries", len(batch), exc_info=True)


activity = ActivityBuffer()
