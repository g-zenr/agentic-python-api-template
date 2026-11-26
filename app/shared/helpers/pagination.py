"""`PageParams` (offset) and `CursorParams` (opaque cursor) dependencies."""

import base64
import binascii

from fastapi import Query

from app.core.constants import Limits, Pagination
from app.core.exceptions import BadInputError


class PageParams:
    def __init__(
        self,
        page: int = Query(Pagination.DEFAULT_PAGE, ge=1),
        size: int = Query(Pagination.DEFAULT_SIZE, ge=1, le=Pagination.MAX_SIZE),
    ):
        self.page, self.size = page, size

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.size

    @property
    def take(self) -> int:
        return self.size


def encode_cursor(value: str) -> str:
    """Encode a row id into an opaque base64url cursor."""
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> str:
    """Decode an opaque cursor back to a row id, raising BadInputError when malformed."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise BadInputError() from exc


class CursorParams:
    def __init__(
        self,
        cursor: str | None = Query(default=None),
        size: int = Query(Pagination.DEFAULT_SIZE, ge=1, le=Pagination.MAX_SIZE),
    ):
        self.size = size
        self.cursor_id = decode_cursor(cursor) if cursor else None
        self.skip = 0

    @property
    def take(self) -> int:
        return self.size


def parse_sort(
    sort: str | None, allowed: set[str], default: str = "-created_at"
) -> list[dict[str, str]]:  # noqa: E501
    """Parse `?sort=-created_at,title` into a Prisma `order` list. Unknown fields raise BadInputError."""  # noqa: E501
    if not sort:
        sort = default
    fields = [f.strip() for f in sort.split(",") if f.strip()][: Limits.SORT_MAX_FIELDS]
    order: list[dict[str, str]] = []
    for field in fields:
        desc = field.startswith("-")
        name = field[1:] if desc else field
        if name not in allowed:
            raise BadInputError()
        order.append({name: "desc" if desc else "asc"})
    return order
