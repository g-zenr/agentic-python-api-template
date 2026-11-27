"""Audit repository: append-only data access over the `audit_logs` table.

Subclasses `ReadRepository` (no create/update/delete-by-id), so append-only is enforced by type.
The only write is `append`; the only bulk removal is `purge_before` (retention);
`scrub_pii_for_actor` nulls IP/user-agent (the DB trigger permits only NULL-scrubbing).
"""

from datetime import datetime
from typing import Any, cast

from prisma.models import AuditLog

import prisma
from app.core.uow import current_db
from app.shared.helpers.repository import ReadRepository


class AuditRepository(ReadRepository[AuditLog]):
    default_order = {"occurred_at": "desc"}

    async def append(self, entry: dict[str, Any]) -> AuditLog:
        """Insert one audit entry (append-only). JSON fields are wrapped for Prisma."""
        data = dict(entry)
        for field in ("changes", "metadata"):
            if data.get(field) is not None:
                data[field] = prisma.Json(data[field])
            else:
                data.pop(field, None)
        return cast("AuditLog", await self.d.create(data=data))

    async def scrub_pii_for_actor(self, actor_id: str) -> int:
        """Null IP/user-agent on this actor's audit rows (account erasure; trigger permits NULL)."""
        return cast(
            int,
            await current_db().execute_raw(
                "UPDATE audit_logs SET ip = NULL, user_agent = NULL WHERE actor_id = $1;", actor_id
            ),
        )

    async def purge_before(self, cutoff: datetime) -> int:
        return cast(int, await self.d.delete_many(where={"occurred_at": {"lt": cutoff}}))


audit_repo = AuditRepository("auditlog")
