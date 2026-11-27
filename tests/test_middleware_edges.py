"""Middleware edges: body-size limits (ASGI), security headers in prod, and the 429 path."""

import httpx

from app.core.middleware import BodyLimitMiddleware, _BodyTooLarge
from app.main import app


def _scope(method="POST", headers=None, path="/x"):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in dict(headers or {}).items()]
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": hdrs,
        "query_string": b"",
    }


def _ok_downstream():
    async def downstream(scope, receive, send):
        await receive()  # a real app reads the body before responding
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok"})

    return downstream


async def _run(mw, scope, body: bytes = b""):
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await mw(scope, receive, send)  # ASGI: (scope, receive, send)
    return sent


async def test_body_limit_non_http_scope_passthrough():
    calls: list = []
    scope = {"type": "lifespan"}

    async def downstream(scope, receive, send):
        calls.append(scope["type"])

    mw = BodyLimitMiddleware(downstream, max_bytes=10)
    await mw(scope, None, None)  # non-http scope: straight passthrough to the app
    assert calls == ["lifespan"]


async def test_body_limit_rejects_by_content_length():
    sent = await _run(
        BodyLimitMiddleware(_ok_downstream(), max_bytes=10),
        _scope(headers={"Content-Length": "100"}),
    )
    assert sent[0]["status"] == 413


async def test_body_limit_rejects_by_streamed_bytes():
    sent = await _run(
        BodyLimitMiddleware(_ok_downstream(), max_bytes=5), _scope(), body=b"1234567"
    )  # no content-length, streamed over
    assert sent[0]["status"] == 413


async def test_body_limit_allows_under_limit():
    sent = await _run(BodyLimitMiddleware(_ok_downstream(), max_bytes=100), _scope(), body=b"hello")
    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"ok"


async def test_streamed_over_limit_swallows_marker():
    async def downstream(scope, receive, send):
        raise _BodyTooLarge  # the marker propagates from the receive side

    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"abcd", "more_body": False}

    async def send(message):
        sent.append(message)

    mw = BodyLimitMiddleware(downstream, max_bytes=3)
    await mw(_scope(), receive, send)
    assert sent[0]["status"] == 413


async def test_security_headers_strict_transport_in_prod(monkeypatch):
    monkeypatch.setattr("app.core.middleware.settings.env", "prod")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/health/live")
    assert r.headers["strict-transport-security"].startswith("max-age=")


async def test_rate_limit_429_path(monkeypatch):
    from app.core import middleware

    async def rate_hit(bucket, identity, limit, window):
        return 42  # over the limit => retry-after

    monkeypatch.setattr(middleware.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(middleware.cache, "rate_hit", rate_hit)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/definitely-not-a-route")  # health/docs are exempt
    assert r.status_code == 429
    assert r.headers["retry-after"] == "42"


def test_security_headers_dev_has_no_sts():
    from app.core.middleware import _security_headers

    assert "strict-transport-security" not in _security_headers()
