"""Generic repositories over a Prisma delegate resolved per call (so they join the active tx).

`ReadRepository` is read-only (get/paginate/paginate_cursor); `BaseRepository` adds writes and
`update_versioned` for optimistic concurrency. Repositories are constructed with the model NAME
(e.g. `NotesRepository("note")`); the delegate is resolved from `current_db()` on every call.
"""

import asyncio
from typing import Any

from app.core.uow import current_db
from app.shared.helpers.pagination import CursorParams, PageParams


class ReadRepository[M]:
    """Read-only access. Subclass and add queries. Construct with the Prisma model name."""

    default_order: dict[str, str] = {"created_at": "desc"}

    def __init__(self, model: str):
        self.model = model

    @property
    def d(self) -> Any:
        return getattr(current_db(), self.model)

    async def get(self, id: str, **opts: Any) -> M | None:
        return await self.d.find_unique(where={"id": id}, **opts)

    async def paginate(
        self,
        params: PageParams,
        where: dict[str, Any] | None = None,
        order: dict[str, str] | None = None,
        **opts: Any,
    ) -> tuple[list[M], int]:
        items, total = await asyncio.gather(
            self.d.find_many(
                where=where,
                skip=params.skip,
                take=params.take,
                order=order or self.default_order,
                **opts,
            ),
            self.d.count(where=where),
        )
        return items, total

    async def paginate_cursor(
        self,
        params: CursorParams,
        where: dict[str, Any] | None = None,
        order: list[dict[str, str]] | None = None,
    ) -> tuple[list[M], str | None]:
        """Fetch size+1 rows starting AT the cursor id; return (rows, next_cursor)."""
        clause = dict(where or {})
        if params.cursor_id is not None:
            clause["id"] = {"not": params.cursor_id}
        rows = await self.d.find_many(
            where=clause,
            take=params.size + 1,
            skip=0 if params.cursor_id is not None else params.skip,
            order=order or [{"created_at": "desc"}, {"id": "desc"}],
        )
        has_more = len(rows) > params.size
        rows = rows[: params.size]
        next_cursor = rows[-1].id if has_more and rows else None
        return rows, next_cursor


class BaseRepository[M](ReadRepository[M]):
    """Read + write. The default for feature repositories."""

    async def create(self, data: dict[str, Any], **opts: Any) -> M:
        return await self.d.create(data=data, **opts)

    async def update(self, id: str, data: dict[str, Any]) -> M | None:
        return await self.d.update(where={"id": id}, data=data)

    async def delete(self, id: str) -> M | None:
        return await self.d.delete(where={"id": id})

    async def update_versioned(self, id: str, expected_version: int, data: dict[str, Any]) -> bool:
        result = await self.d.update_many(
            where={"id": id, "version": expected_version},
            data={**data, "version": {"increment": 1}},
        )
        return result == 1
