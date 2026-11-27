"""Generic repositories over a Prisma delegate resolved per call (so they join the active tx).

`ReadRepository` is read-only (get/paginate/paginate_cursor); `BaseRepository` adds writes and
`update_versioned` for optimistic concurrency. Repositories are constructed with the model NAME
(e.g. `NotesRepository("note")`); the delegate is resolved from `current_db()` on every call.
"""

import asyncio
from typing import Any, cast

from app.core.exceptions import BadInputError
from app.core.uow import current_db
from app.shared.helpers.pagination import CursorParams, PageParams


def _cursor_keyset(order: list[dict[str, str]], cursor_row: Any) -> list[dict[str, Any]]:
    """Keyset ("seek") conditions selecting rows strictly AFTER `cursor_row` in `order`.

    For order [(f1, d1), (f2, d2), ...] and cursor values (v1, v2, ...), a row qualifies when
    f1 (d1-op) v1, OR (f1 == v1 AND f2 (d2-op) v2), OR (f1 == v1 AND f2 == v2 AND ...). `op` is
    `gt` for ascending and `lt` for descending. The order list must include a unique tiebreaker
    (typically `id`) for stable paging; ordering keys must be non-null.
    """
    ors: list[dict[str, Any]] = []
    for idx, spec in enumerate(order):
        field, direction = next(iter(spec.items()))
        clause: dict[str, Any] = {}
        for prev in order[:idx]:  # equality on all earlier ordering keys
            prev_field = next(iter(prev))
            clause[prev_field] = {"equals": getattr(cursor_row, prev_field)}
        op = "lt" if direction == "desc" else "gt"
        clause[field] = {op: getattr(cursor_row, field)}
        ors.append(clause)
    return ors


class ReadRepository[M]:
    """Read-only access. Subclass and add queries. Construct with the Prisma model name."""

    default_order: dict[str, str] = {"created_at": "desc"}

    def __init__(self, model: str):
        self.model = model

    @property
    def d(self) -> Any:
        return getattr(current_db(), self.model)

    async def get(self, id: str, **opts: Any) -> M | None:
        return cast("M | None", await self.d.find_unique(where={"id": id}, **opts))

    async def paginate(
        self,
        params: PageParams,
        where: dict[str, Any] | None = None,
        order: dict[str, str] | list[dict[str, str]] | None = None,
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
        return cast("list[M]", items), cast(int, total)

    async def paginate_cursor(
        self,
        params: CursorParams,
        where: dict[str, Any] | None = None,
        order: list[dict[str, str]] | None = None,
    ) -> tuple[list[M], str | None]:
        """Keyset pagination: size+1 rows strictly after `cursor_id`; return (rows, next_cursor).

        The cursor is an opaque row id; on subsequent pages we look up that row's ordering keys
        and emit a keyset ("seek") filter so pages never overlap, repeat, or skip. Unknown cursor
        ids raise `BadInputError`.
        """
        order = order or [{"created_at": "desc"}, {"id": "desc"}]
        base = dict(where or {})
        skip = params.skip
        if params.cursor_id is not None:
            cursor_row = await self.d.find_unique(where={"id": params.cursor_id})
            if cursor_row is None:
                raise BadInputError()
            keyset = _cursor_keyset(order, cursor_row)
            clause: dict[str, Any] = {"AND": [base, {"OR": keyset}]} if base else {"OR": keyset}
            skip = 0
        else:
            clause = base
        rows = cast(
            "list[M]",
            await self.d.find_many(where=clause, take=params.size + 1, skip=skip, order=order),
        )
        has_more = len(rows) > params.size
        rows = rows[: params.size]
        next_cursor = cast(Any, rows[-1]).id if has_more and rows else None
        return rows, next_cursor


class BaseRepository[M](ReadRepository[M]):
    """Read + write. The default for feature repositories."""

    async def create(self, data: dict[str, Any], **opts: Any) -> M:
        return cast("M", await self.d.create(data=data, **opts))

    async def update(self, id: str, data: dict[str, Any]) -> M | None:
        return cast("M | None", await self.d.update(where={"id": id}, data=data))

    async def delete(self, id: str) -> M | None:
        return cast("M | None", await self.d.delete(where={"id": id}))

    async def update_versioned(self, id: str, expected_version: int, data: dict[str, Any]) -> bool:
        result = await self.d.update_many(
            where={"id": id, "version": expected_version},
            data={**data, "version": {"increment": 1}},
        )
        return cast(int, result) == 1
