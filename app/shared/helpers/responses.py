"""Builders for the `ApiResponse` envelope: use these in routers, never build it by hand."""

from math import ceil
from typing import Any, cast

from app.core.i18n import t
from app.core.messages import Msg
from app.shared.helpers.pagination import CursorParams, PageParams, encode_cursor
from app.shared.schemas import ApiModel, ApiResponse, CursorMeta, Meta


def ok(data: Any = None, msg: Msg = Msg.OK, **params: object) -> ApiResponse[Any]:
    return ApiResponse(message=t(msg, **cast("dict[str, Any]", params)), data=data)


def page_of(
    items: list[Any],
    total: int,
    params: PageParams,
    schema: type[ApiModel] | None = None,
    msg: Msg = Msg.OK,
) -> ApiResponse[Any]:
    """Offset-paginated envelope. Pass `schema` to convert DB rows to output models."""
    data = [schema.model_validate(i) for i in items] if schema else items
    meta = Meta(page=params.page, size=params.size, total=total, pages=ceil(total / params.size))
    return ApiResponse[Any](message=t(msg), data=data, meta=meta)


def cursor_page_of(
    items: list[Any],
    next_cursor: str | None,
    params: CursorParams,
    schema: type[ApiModel] | None = None,
    msg: Msg = Msg.OK,
) -> ApiResponse[Any]:
    """Cursor-paginated envelope (no COUNT). `next_cursor` is the last row id when more remain."""
    data = [schema.model_validate(i) for i in items] if schema else items
    cursor = CursorMeta(
        next_cursor=encode_cursor(next_cursor) if next_cursor else None,
        size=params.size,
        has_more=next_cursor is not None,
    )
    return ApiResponse[Any](message=t(msg), data=data, cursor=cursor)
