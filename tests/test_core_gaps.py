"""Core leftovers: context, database, email, security, ratelimit, exceptions, types, otel fakes."""

import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

import httpx
import pytest

from app.core import context as ctx_mod
from app.core import database as db_mod
from app.core import ratelimit
from app.core.cache import cache
from app.core.constants import RateBucket
from app.core.context import bind_user, request_ctx
from app.core.exceptions import BadInputError, ForbiddenError, UnauthorizedError
from app.core.jobs.types import JobContext, JobRecord, PermanentError
from app.core.messages import Msg
from app.core.security import decode_access_token
from app.main import app
from app.shared.utils.time import date_range, utcnow

# --- context -----------------------------------------------------------------


def test_bind_user_sets_context():
    token = request_ctx.set(None)
    try:
        bind_user("u42")
        rc = request_ctx.get()
        assert rc.user_id == "u42"
        assert rc.actor_type == ctx_mod.ActorType.USER
    finally:
        request_ctx.reset(token)


# --- database ----------------------------------------------------------------


def test_build_database_url_empty_and_existing_params(monkeypatch):
    monkeypatch.setattr(db_mod.settings, "database_url", "")
    assert db_mod.build_database_url() == ""

    monkeypatch.setattr(
        db_mod.settings, "database_url", "postgresql://u:p@h:5432/d?connection_limit=2"
    )
    url = db_mod.build_database_url()
    assert "connection_limit=2" in url  # existing param preserved, not duplicated
    assert url.count("connection_limit") == 1


async def test_connect_disconnect_guards(monkeypatch):
    calls: list[str] = []

    class FakePrisma:
        def is_connected(self):
            return len(calls) % 2 == 1  # connected after one connect

        async def connect(self):
            calls.append("connect")

        async def disconnect(self):
            calls.append("disconnect")

    fake = FakePrisma()
    monkeypatch.setattr(db_mod, "db", fake)
    await db_mod.connect_db()  # not connected -> connects
    await db_mod.connect_db()  # already connected -> no-op
    await db_mod.disconnect_db()  # connected -> disconnects
    await db_mod.disconnect_db()  # already disconnected -> no-op
    assert calls == ["connect", "disconnect"]


# --- email -------------------------------------------------------------------


async def test_console_sender_logs(monkeypatch, caplog):
    from app.core.email import ConsoleSender

    with caplog.at_level(20, logger="app.core.email"):
        await ConsoleSender().send("a@b.c", "S", "B")
    assert any("email to=a@b.c" in r.message for r in caplog.records)


async def test_smtp_sender_uses_settings(monkeypatch):
    import types

    from app.core.email import SmtpSender

    sent: dict = {}
    fake_lib = types.SimpleNamespace(send=None)

    async def _send(**kw):
        sent.update(kw)

    fake_lib.send = _send
    sender = SmtpSender()
    sender._lib = fake_lib
    monkeypatch.setattr(
        "app.core.email.settings.smtp_password",
        type("P", (), {"get_secret_value": lambda s: "pw"})(),  # noqa: E501
    )
    await sender.send("to@x", "Sub", "Body")
    assert sent["hostname"] == "" and sent["username"] is None and sent["password"] == "pw"
    assert sent["message"].startswith("From:")


async def test_get_sender_backends(monkeypatch):
    from app.core import email as email_mod

    monkeypatch.setattr(email_mod.settings, "email_backend", "console")
    email_mod.set_sender(None)
    assert type(email_mod.get_sender()).__name__ == "ConsoleSender"

    monkeypatch.setattr(email_mod.settings, "email_backend", "smtp")
    email_mod.set_sender(None)
    assert type(email_mod.get_sender()).__name__ == "SmtpSender"

    fake = object()
    email_mod.set_sender(fake)
    assert email_mod.get_sender() is fake
    email_mod.set_sender(None)


# --- security ----------------------------------------------------------------


def test_decode_rejects_non_access_and_malformed():
    import jwt

    from app.core.config import settings

    secret = settings.jwt_secret.get_secret_value()
    refresh = jwt.encode({"sub": "u1", "tv": 0, "typ": "refresh"}, secret, settings.jwt_algorithm)
    with pytest.raises(UnauthorizedError):
        decode_access_token(refresh)
    with pytest.raises(UnauthorizedError):
        decode_access_token("not-a-token")
    # missing sub -> KeyError path
    bad = jwt.encode({"typ": "access"}, secret, settings.jwt_algorithm)
    with pytest.raises(UnauthorizedError):
        decode_access_token(bad)


# --- ratelimit ---------------------------------------------------------------


async def test_enforce_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(ratelimit.settings, "rate_limit_enabled", False)
    await ratelimit.enforce(RateBucket.LOGIN_IP, "x")  # no raise, no count


async def test_peek_bad_value_and_reset(monkeypatch):
    async def bad_get(key):
        return b"not-an-int"

    async def ok_delete(key):
        return True

    monkeypatch.setattr(cache.backend, "get", bad_get)
    assert await ratelimit.peek(RateBucket.LOGIN_IP, "x") == 0
    monkeypatch.setattr(cache.backend, "delete", ok_delete)
    await ratelimit.reset(RateBucket.LOGIN_IP, "x")  # no raise


# --- exceptions handlers -----------------------------------------------------


async def test_validation_error_becomes_422_with_field_details():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["code"] == "VALIDATION_ERROR"


async def test_unhandled_exception_becomes_500():
    from fastapi import FastAPI

    from app.core.exceptions import register_exception_handlers

    small = FastAPI()
    register_exception_handlers(small)

    @small.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    transport = httpx.ASGITransport(app=small, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    assert r.json()["code"] == "INTERNAL_ERROR"


def test_bad_input_error_default_msg():
    err = BadInputError()
    assert err.msg == Msg.VALIDATION_ERROR and err.status_code == 422


def test_forbidden_default():
    assert ForbiddenError().status_code == 403


# --- job types ---------------------------------------------------------------


async def test_job_record_from_row_bad_json_and_context():
    now = utcnow()
    rec = JobRecord.from_row(
        {
            "id": "j1",
            "type": "notes.export",
            "status": "QUEUED",
            "payload": "not-json",
            "result": '{"ok": true}',
            "error": None,
            "progress": 0,
            "attempts": 0,
            "max_attempts": 1,
            "user_id": "u1",
            "request_id": None,
            "cancel_requested": False,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
    )
    assert rec.payload == {} and rec.result == {"ok": True}

    store_calls: list[str] = []

    class Store:
        async def set_progress(self, job_id, percent):
            store_calls.append(("progress", job_id, percent))

        async def is_cancel_requested(self, job_id):
            return False

    jc = JobContext(rec, Store())
    assert jc.user_id == "u1"
    await jc.progress(150)  # clamped
    assert store_calls == [("progress", "j1", 100)]
    await jc.raise_if_cancelled()  # no raise


def test_permanent_error_is_app_error():
    err = PermanentError(Msg.JOB_TIMEOUT)
    assert err.status_code == 500


# --- observability: fake OTel SDK -------------------------------------------


def _install_fake_otel(monkeypatch):
    def mod(name, **attrs):
        m = ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    class FakeProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors: list = []

        def add_span_processor(self, p):
            self.processors.append(p)

    class FakeInstrumentor:
        @staticmethod
        def instrument_app(app_):
            getattr(app_.state, "_otel", None)

    otel = mod("opentelemetry")
    mod("opentelemetry.trace", set_tracer_provider=lambda p: None)
    mod(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        OTLPSpanExporter=lambda endpoint=None: SimpleNamespace(endpoint=endpoint),
    )
    mod(
        "opentelemetry.instrumentation.fastapi",
        FastAPIInstrumentor=FakeInstrumentor,
    )
    mod("opentelemetry.sdk.resources", Resource=SimpleNamespace(create=lambda d: d))
    mod("opentelemetry.sdk.trace", TracerProvider=FakeProvider)
    mod(
        "opentelemetry.sdk.trace.export",
        BatchSpanProcessor=lambda e: SimpleNamespace(exporter=e),
    )
    return otel


def test_setup_otel_instruments_with_fake_sdk(monkeypatch):
    from app.core.observability import setup_otel

    _install_fake_otel(monkeypatch)
    monkeypatch.setattr("app.core.observability.settings.otel_enabled", True)
    monkeypatch.setattr(
        "app.core.observability.settings.otel_exporter_otlp_endpoint", "http://collector:4317"
    )
    setup_otel(app)  # imports succeed -> provider + instrumentor run


# --- time util ---------------------------------------------------------------


def test_date_range_single_sided():
    now = datetime.now(UTC)
    assert date_range(None, now) == {"lt": now}
    assert date_range(now, None) == {"gte": now}
    assert date_range(None, None) is None
