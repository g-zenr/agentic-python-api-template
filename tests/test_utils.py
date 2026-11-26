"""Unit tests for the shared utilities (time, text, json)."""

from datetime import UTC, datetime

from app.shared.utils.json import dumps, loads
from app.shared.utils.text import slugify, truncate
from app.shared.utils.time import iso, to_zone, utcnow


def test_utcnow_is_tz_aware():
    assert utcnow().tzinfo is not None


def test_to_zone_converts():
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    zoned = to_zone(dt, "Asia/Manila")
    assert zoned.utcoffset().total_seconds() == 8 * 3600


def test_iso_roundtrips():
    dt = datetime(2026, 1, 1, tzinfo=UTC)
    assert iso(dt) == dt.isoformat()


def test_truncate():
    assert truncate("hello", 10) == "hello"
    assert truncate("hello world", 8).endswith("…")


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"


def test_json_roundtrip():
    assert loads(dumps({"a": 1})) == {"a": 1}
