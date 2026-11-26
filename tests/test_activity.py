"""Activity buffer tests: batching, stop-flush, drop-on-full, skip paths, sink failure."""

import pytest

from app.core.activity.buffer import ActivityBuffer
from app.core.config import settings
from app.core.constants import Activity
from app.core.context import RequestContext
from tests.fakes import ListActivitySink


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(settings, "activity_enabled", True)


class FakeRequest:
    def __init__(self, path, method="GET", route_path=None):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.scope = {"route": type("R", (), {"path": route_path})()} if route_path else {}


def _ctx():
    return RequestContext(request_id="r", user_id="u", ip="1.1.1.1")


async def test_record_is_non_blocking():
    buf = ActivityBuffer(sink=ListActivitySink())
    for _ in range(1000):
        buf.record({"x": 1})  # must not raise even beyond maxsize
    assert buf.dropped >= 0


async def test_flush_by_size(monkeypatch):
    monkeypatch.setattr(settings, "activity_batch_size", 2)
    monkeypatch.setattr(settings, "activity_flush_seconds", 10.0)
    sink = ListActivitySink()
    buf = ActivityBuffer(sink=sink)
    for i in range(3):
        buf.record({"i": i})
    batch = await buf._collect()
    assert len(batch) == 2
    await buf._flush(batch)
    assert len(sink.batches) == 1


async def test_stop_flushes_remainder():
    sink = ListActivitySink()
    buf = ActivityBuffer(sink=sink)
    await buf.start()
    buf.record({"a": 1})
    buf.record({"b": 2})
    await buf.stop()
    total = sum(len(b) for b in sink.batches)
    assert total == 2


async def test_full_queue_drops(monkeypatch):
    monkeypatch.setattr(settings, "activity_queue_max", 1)
    buf = ActivityBuffer(sink=ListActivitySink())
    buf.record({"a": 1})
    buf.record({"b": 2})
    buf.record({"c": 3})
    assert buf.dropped >= 1


async def test_skip_paths_are_ignored():
    sink = ListActivitySink()
    buf = ActivityBuffer(sink=sink)
    buf.record_request(FakeRequest("/docs"), _ctx(), 200, 0.0)
    buf.record_request(FakeRequest(f"{settings.api_prefix}/health"), _ctx(), 200, 0.0)
    assert buf._q.empty()


async def test_unmatched_route_uses_placeholder():
    sink = ListActivitySink()
    buf = ActivityBuffer(sink=sink)
    buf.record_request(FakeRequest("/api/v1/notes/123", route_path=None), _ctx(), 200, 0.0)
    entry = buf._q.get_nowait()
    assert entry["path"] == Activity.UNMATCHED


async def test_matched_route_uses_template():
    buf = ActivityBuffer(sink=ListActivitySink())
    buf.record_request(
        FakeRequest("/api/v1/notes/123", route_path="/api/v1/notes/{note_id}"), _ctx(), 200, 0.0
    )
    entry = buf._q.get_nowait()
    assert entry["path"] == "/api/v1/notes/{note_id}"


async def test_sink_failure_drops_and_survives():
    buf = ActivityBuffer(sink=ListActivitySink(fail=True))
    await buf._flush([{"a": 1}, {"b": 2}])
    assert buf.dropped == 2
