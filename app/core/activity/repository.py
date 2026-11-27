"""Activity repository: append-only data access over the `activity_logs` table."""

from datetime import datetime
from typing import Any, cast

from prisma.models import ActivityLog

from app.core.uow import current_db
from app.shared.helpers.repository import ReadRepository


class ActivityRepository(ReadRepository[ActivityLog]):
    default_order = {"occurred_at": "desc"}

    async def append_many(self, entries: list[dict[str, Any]]) -> int:
        """Bulk-insert a batch of activity entries."""
        if not entries:
            return 0
        result = await self.d.create_many(data=entries)
        return len(result) if result is not None else len(entries)

    async def scrub_ip_for_user(self, user_id: str) -> int:
        """Null IP on this user's activity rows (account erasure)."""
        return cast(
            int,
            await current_db().execute_raw(
                "UPDATE activity_logs SET ip = NULL WHERE user_id = $1;", user_id
            ),
        )

    async def purge_before(self, cutoff: datetime) -> int:
        return cast(int, await self.d.delete_many(where={"occurred_at": {"lt": cutoff}}))


activity_repo = ActivityRepository("activitylog")
