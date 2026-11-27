"""API quality: route metadata, the response envelope, and status-code accuracy.

Complements the speed suite (`test_api_speed.py`): this checks WHAT the API says about itself;
that one checks HOW FAST it answers. Both run on the in-process ASGI app (no network).
"""

import httpx
import pytest
from fastapi.routing import APIRoute

from app.core.constants import ErrorCode
from app.main import app

PUBLIC = {"GET:/api/v1/health/live", "POST:/api/v1/auth/register", "POST:/api/v1/auth/login"}


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def test_every_route_declares_summary_and_description():
    """Golden rule 8: every route is documented for the OpenAPI schema."""
    undocumented = [
        (sorted(r.methods)[0], r.path)
        for r in app.routes
        if isinstance(r, APIRoute) and not (r.summary and r.description)
    ]
    assert not undocumented, f"routes missing summary/description: {undocumented}"


async def test_envelope_on_error_has_success_false_and_stable_code(client):
    r = await client.get("/api/v1/definitely-not-a-route")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["code"] == ErrorCode.NOT_FOUND.value


async def test_envelope_on_success_is_camel_case(client):
    r = await client.get("/api/v1/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "requestId" not in body  # envelope is {success,message,data,meta,cursor}
    assert set(body) <= {"success", "message", "code", "data", "meta", "cursor"}


async def test_validation_error_is_422_with_field_details(client):
    r = await client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == ErrorCode.VALIDATION.value
    assert isinstance(body["data"], list) and body["data"]


async def test_security_headers_present_on_responses(client):
    r = await client.get("/api/v1/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


async def test_protected_route_requires_auth(client):
    """Unauthenticated access to a protected route is 401 with the standard envelope."""
    r = await client.get("/api/v1/users")
    assert r.status_code == 401
    assert r.json()["success"] is False


async def test_404_on_unknown_route_and_405_on_wrong_method(client):
    assert (await client.get("/api/v1/nope")).status_code == 404
    assert (await client.delete("/api/v1/health/live")).status_code == 405


async def test_method_not_allowed_and_unhandled_are_enveloped(client):
    """405 and 500 both render the envelope (never a bare starlette error page)."""
    r = await client.post("/api/v1/health/live")
    assert r.status_code == 405
    assert r.json()["success"] is False


async def test_app_metadata_matches_settings():
    from app.core.config import settings

    assert app.title == settings.app_name
    assert app.version == settings.app_version


async def test_allow_header_includes_all_resource_methods(client):
    response = await client.options("/api/v1/notes")
    assert response.status_code == 405
    assert {"GET", "POST"} <= {m.strip() for m in response.headers["allow"].split(",")}
