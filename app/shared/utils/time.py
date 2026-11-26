"""Time helpers: timezone-aware UTC now, zone conversion, ISO formatting, range building."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def to_zone(dt: datetime, tz_name: str) -> datetime:
    """Convert `dt` to the given IANA timezone (e.g. ``Asia/Manila``)."""
    return dt.astimezone(ZoneInfo(tz_name))


def iso(dt: datetime) -> str:
    """Serialize a datetime to an ISO-8601 string."""
    return dt.isoformat()


def date_range(since: datetime | None, until: datetime | None) -> dict | None:
    """Build a Prisma `occurred_at` filter `{"gte": since, "lt": until}` from the bounds."""
    bounds: dict[str, datetime] = {}
    if since is not None:
        bounds["gte"] = since
    if until is not None:
        bounds["lt"] = until
    return bounds or None
