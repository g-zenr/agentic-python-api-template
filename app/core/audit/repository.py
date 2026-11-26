"""Audit repository: append-only data access over the `audit_logs` table.

Subclasses `ReadRepository` (no create/update/delete-by-id), so append-only is enforced by type.
The only write is `append`; the only bulk removal is `purge_before` (retention).
"""

from datetime import datetime
from typing import Any

from prisma.models import AuditLog

import prisma
from app.shared.helpers.pagination import PageParams
from app.shared.helpers.repository import ReadRepository
from app.shared.utils.time import date_range


class AuditRepository(ReadRepository[AuditLog]):
    default_order = {"occurred_at": "desc"}

    async def append(self, entry: dict[str, Any]) -> AuditLog:
        """Insert one audit entry (append-only). JSON fields are wrapped for Prisma."""
        data = dict(entry)
        for field in ("changes", "metadata"):
            if data.get(field) is not None:
                data[field] = prisma.Json(data[field])
        return await self.d.create(data=data)

    async def search(
        self,
        params: PageParams,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        where: dict[str, Any] = {}
        if actor_id is not None:
            where["actor_id"] = actor_id
        if action is not None:
            where["action"] = action
        if resource_type is not None:
            where["resource_type"] = resource_type
        if resource_id is not None:
            where["resource_id"] = resource_id
        if outcome is not None:
            where["outcome"] = outcome
        occurred = date_range(since, until)
        if occurred is not None:
            where["occurred_at"] = occurred
        return await self.paginate(params, where=where)

    async def purge_before(self, cutoff: datetime) -> int:
        result = await self.d.delete_many(where={"occurred_at": {"lt": cutoff}})
        return result


audit_repo = AuditRepository("auditlog")
