"""API speed tests: per-request latency SLO (NOT functional tests).

SLO: every in-process request must answer within `API_SLO_MS` (default 1000ms = 1s local; set
2000 for a deployed API via `API_SLO_MS=2000`). The suite also asserts aggregate throughput
(p95 across a batch) so a single fast request cannot mask a slow endpoint.

Run against the in-process app by default; point at a deployed API with `API_BASE_URL`
(e.g. `API_BASE_URL=https://api.example.com API_SLO_MS=2000 pytest -m speed`).
"""

import os
import time
from statistics import mean

import httpx
import pytest

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.speed

SLO_MS = settings.api_slo_ms
BASE_URL = os.environ.get("API_BASE_URL")  # unset => in-process ASGI transport


@pytest.fixture
def api():
    """One client for the whole module: a deployed base URL, else the ASGI app."""
    transport = httpx.ASGITransport(app=app) if not BASE_URL else None
    return httpx.AsyncClient(transport=transport, base_url=BASE_URL or "http://test", timeout=10)


async def _timed(api, method: str, path: str, **kw) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = await api.request(method, path, **kw)
    return response, (time.perf_counter() - started) * 1000


async def test_health_live_under_slo(api):
    r, ms = await _timed(api, "GET", "/api/v1/health/live")
    assert r.status_code == 200
    assert ms <= SLO_MS, f"/health/live took {ms:.0f}ms > {SLO_MS}ms SLO"


async def test_health_ready_under_slo(api):
    r, ms = await _timed(api, "GET", "/api/v1/health/ready")
    assert r.status_code in (200, 503)  # 503 without a DB is correct; both must be fast
    assert ms <= SLO_MS, f"/health/ready took {ms:.0f}ms > {SLO_MS}ms SLO"


async def test_protected_route_rejects_fast(api):
    """401 paths must be as fast as the happy path (no slow rejection)."""
    r, ms = await _timed(api, "GET", "/api/v1/users")
    assert r.status_code == 401
    assert ms <= SLO_MS


async def test_validation_rejects_fast(api):
    r, ms = await _timed(api, "POST", "/api/v1/auth/login", json={"email": "bad", "password": "x"})
    assert r.status_code == 422
    assert ms <= SLO_MS


async def test_openapi_and_docs_are_fast(api):
    for path in ("/openapi.json", "/docs"):
        r, ms = await _timed(api, "GET", path)
        assert r.status_code == 200
        assert ms <= SLO_MS, f"{path} took {ms:.0f}ms > {SLO_MS}ms SLO"


async def test_p95_latency_across_mixed_requests_under_slo(api):
    """Aggregate gate: 20 mixed requests, p95 must stay within the SLO."""
    samples: list[float] = []
    for i in range(20):
        method, path = ("GET", "/api/v1/health/live") if i % 2 else ("GET", "/api/v1/users")
        r, ms = await _timed(api, method, path)
        assert r.status_code in (200, 401)
        samples.append(ms)
    p95 = sorted(samples)[int(len(samples) * 0.95) - 1]
    assert p95 <= SLO_MS, f"p95 {p95:.0f}ms > {SLO_MS}ms SLO"
    assert mean(samples) <= SLO_MS, f"mean {mean(samples):.0f}ms > {SLO_MS}ms SLO"


async def test_metrics_endpoint_is_fast(api):
    r, ms = await _timed(api, "GET", "/metrics")
    assert r.status_code == 200
    assert ms <= SLO_MS
