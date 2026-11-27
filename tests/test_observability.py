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


# --- Sentry / OpenTelemetry setup (optional packages) -----------------------


def test_setup_sentry_noop_without_dsn(monkeypatch):
    from app.core.observability import setup_sentry

    monkeypatch.setattr("app.core.observability.settings.sentry_dsn", None)
    setup_sentry()  # must not raise


def test_setup_sentry_missing_package_warns(monkeypatch, caplog):
    import sys

    from app.core.observability import setup_sentry

    monkeypatch.setattr(
        "app.core.observability.settings.sentry_dsn", _secret("https://k@example.ingest/1")
    )
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # force ImportError on `import sentry_sdk`
    setup_sentry()  # logs warning, does not raise


def test_setup_sentry_initializes_and_scrubs(monkeypatch):
    import sys
    import types

    from app.core.observability import setup_sentry

    captured: dict = {}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setattr(
        "app.core.observability.settings.sentry_dsn", _secret("https://k@example.ingest/1")
    )
    monkeypatch.setattr("app.core.observability.settings.sentry_traces_sample_rate", 0.5)
    setup_sentry()

    assert captured["send_default_pii"] is False
    assert captured["traces_sample_rate"] == 0.5
    # before_send strips request body + cookies
    event = {"request": {"data": {"x": 1}, "cookies": {"a": "b"}, "url": "/x"}}
    out = captured["before_send"](event, {})
    assert "data" not in out["request"] and "cookies" not in out["request"]


def test_setup_otel_noop_when_disabled(monkeypatch):
    from app.core.observability import setup_otel

    monkeypatch.setattr("app.core.observability.settings.otel_enabled", False)
    setup_otel(app)  # no raise


def test_setup_otel_missing_packages_warns(monkeypatch):
    import sys

    from app.core.observability import setup_otel

    monkeypatch.setattr("app.core.observability.settings.otel_enabled", True)
    # ensure the otel imports fail
    for name in list(sys.modules):
        if name.startswith("opentelemetry"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    setup_otel(app)  # logs warning, does not raise


def _secret(value: str):
    from pydantic import SecretStr

    return SecretStr(value)
