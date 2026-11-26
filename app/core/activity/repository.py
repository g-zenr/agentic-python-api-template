"""Activity repository: append-only data access over the `activity_logs` table."""

from datetime import datetime
from typing import Any

from prisma.models import ActivityLog

from app.shared.helpers.pagination import PageParams
from app.shared.helpers.repository import ReadRepository
from app.shared.utils.time import date_range


class ActivityRepository(ReadRepository[ActivityLog]):
    default_order = {"occurred_at": "desc"}

    async def append_many(self, entries: list[dict[str, Any]]) -> int:
        """Bulk-insert a batch of activity entries."""
        if not entries:
            return 0
        result = await self.d.create_many(data=entries)
        return len(result) if result is not None else len(entries)

    async def search(
        self,
        params: PageParams,
        *,
        user_id: str | None = None,
        status_code: int | None = None,
        path: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[ActivityLog], int]:
        where: dict[str, Any] = {}
        if user_id is not None:
            where["user_id"] = user_id
        if status_code is not None:
            where["status_code"] = status_code
        if path is not None:
            where["path"] = path
        occurred = date_range(since, until)
        if occurred is not None:
            where["occurred_at"] = occurred
        return await self.paginate(params, where=where)

    async def purge_before(self, cutoff: datetime) -> int:
        result = await self.d.delete_many(where={"occurred_at": {"lt": cutoff}})
        return result


activity_repo = ActivityRepository("activitylog")
