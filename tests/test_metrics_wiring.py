"""Observability: metrics are actually updated, not just defined."""

import contextlib

import httpx

from app.core.constants import RateBucket
from app.core.exceptions import RateLimitedError
from app.core.metrics import render_metrics
from app.core.ratelimit import enforce
from app.main import app


def _text() -> str:
    body, _ = render_metrics()
    return body.decode()


async def test_http_requests_total_increments():
    before = _text()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/health/live")
    assert r.status_code == 200
    text = _text()
    assert "http_requests_total" in text
    # route TEMPLATE used; a sample line exists for our request with status 200
    assert 'method="GET"' in text
    assert 'status="200"' in text
    assert text != before


async def test_rate_limit_rejection_metric_increments():
    # force a rejection on a tiny limit
    for _ in range(3):
        with contextlib.suppress(RateLimitedError):
            await enforce(RateBucket.LOGIN_IP, "metrics-test", limit=1, window=60)
    assert "rate_limit_rejections_total" in _text()
