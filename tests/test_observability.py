"""Observability: metrics rendering, /metrics open in dev, health live vs ready (no DB)."""

import httpx

from app.core.metrics import render_metrics
from app.main import app


def test_metrics_render_contains_core_names():
    body, _ = render_metrics()
    text = body.decode()
    assert "http_requests_total" in text


async def test_health_live_ok():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/health/live")
        assert r.status_code == 200
        assert r.json()["success"] is True


async def test_health_ready_503_without_db():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/health/ready")
        assert r.status_code == 503
        assert r.json()["success"] is False


async def test_metrics_open_in_dev():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/metrics")
        assert r.status_code == 200
