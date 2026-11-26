"""Health endpoint tests: success envelope, i18n message, and 404 error envelope."""

import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_ok(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "up"
    assert resp.headers["x-request-id"]
    assert resp.headers["cache-control"] == "no-store"


async def test_health_filipino_message(client):
    resp = await client.get("/api/v1/health", headers={"Accept-Language": "fil"})
    assert resp.json()["message"] == "Maayos ang serbisyo"


async def test_unknown_route_returns_error_envelope(client):
    resp = await client.get("/api/v1/nope")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "NOT_FOUND"
