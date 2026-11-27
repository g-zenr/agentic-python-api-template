"""HTTP middleware: trusted hosts, body-size limit, request context, activity, security headers."""

import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.activity import activity
from app.core.cache import cache
from app.core.config import settings
from app.core.constants import CacheControl, ErrorCode, Header, RateBucket
from app.core.context import RequestContext, locale_var, request_ctx, request_id_var
from app.core.exceptions import error_response
from app.core.i18n import resolve_locale, t
from app.core.messages import Msg
from app.core.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    rate_limit_rejections_total,
)
from app.shared.helpers.http import client_ip


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Pure-ASGI body-size limit: rejects by Content-Length and by streamed byte count."""

    def __init__(self, app: Callable[..., Awaitable[None]], max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[None]],
    ) -> None:  # noqa: E501
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope["headers"]}
        cl = headers.get(b"content-length")
        if cl is not None and cl.isdigit() and int(cl) > self.max_bytes:
            await self._reject(scope, send)
            return
        total = 0

        async def rcv() -> dict[str, Any]:
            nonlocal total
            message: dict[str, Any] = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, rcv, send)
        except _BodyTooLarge:
            await self._reject(scope, send)

    async def _reject(self, scope: dict[str, Any], send: Callable[..., Awaitable[None]]) -> None:
        response = error_response(413, ErrorCode.PAYLOAD_TOO_LARGE, t(Msg.PAYLOAD_TOO_LARGE))
        await response(scope, receive=None, send=send)  # type: ignore[arg-type]


def _security_headers() -> dict[str, str]:
    headers = {
        Header.CONTENT_TYPE_OPTIONS: "nosniff",
        Header.FRAME_OPTIONS: "DENY",
        Header.REFERRER_POLICY: "no-referrer",
        Header.CSP: "default-src 'none'; frame-ancestors 'none'",
    }
    if settings.env == "prod":
        headers[Header.STS] = "max-age=31536000; includeSubDomains"
    return headers


async def context_middleware(request: Request, call_next: Callable[..., Awaitable[Any]]) -> Any:
    rid = request.headers.get(Header.REQUEST_ID) or uuid4().hex
    request_id_var.set(rid)
    locale_var.set(resolve_locale(request.headers.get(Header.LOCALE)))
    ctx = RequestContext(
        request_id=rid, ip=client_ip(request), user_agent=request.headers.get(Header.USER_AGENT)
    )
    request_ctx.set(ctx)

    path = request.url.path
    started = time.perf_counter()
    if settings.rate_limit_enabled and not _is_exempt(path):
        retry = await cache.rate_hit(
            RateBucket.GLOBAL_IP.value,
            ctx.ip or "unknown",
            settings.rate_limit_global_per_minute,
            60,
        )
        if retry:
            rate_limit_rejections_total.labels(bucket=RateBucket.GLOBAL_IP.value).inc()
            _record_http_metrics(request, "429", started)
            return error_response(
                429,
                ErrorCode.RATE_LIMITED,
                t(Msg.RATE_LIMITED),
                headers={Header.RETRY_AFTER: str(retry)},
            )

    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    finally:
        activity.record_request(request, ctx, status, started)
        _record_http_metrics(request, str(status), started)
    response.headers[Header.REQUEST_ID] = rid
    response.headers.setdefault(Header.CACHE_CONTROL, CacheControl.NO_STORE)
    for key, value in _security_headers().items():
        response.headers.setdefault(key, value)
    return response


def _record_http_metrics(request: Request, status: str, started: float) -> None:
    """Emit http_requests_total + http_request_duration_seconds using the route TEMPLATE."""
    route = request.scope.get("route")
    template = getattr(route, "path", request.url.path)
    method = request.method
    http_requests_total.labels(method=method, route=template, status=status).inc()
    http_request_duration_seconds.labels(method=method, route=template).observe(
        time.perf_counter() - started
    )


def _is_exempt(path: str) -> bool:
    if path.startswith(f"{settings.api_prefix}/health") or path in (
        "/metrics",
        "/docs",
        "/openapi.json",
    ):  # noqa: E501
        return True
    return any(
        path == p or path.startswith(p) for p in ("/docs", "/openapi.json", "/mcp", "/metrics")
    )  # noqa: E501


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(context_middleware)
