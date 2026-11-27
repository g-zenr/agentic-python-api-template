"""Application factory. NEVER edit this to add a feature: routers and tools are auto-discovered.

Infrastructure (DB, cache, activity, embedded worker, MCP, metrics, observability) is wired here.
Adding a job, cached read or audit event never requires editing this file.
"""

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from app.core.activity import activity
from app.core.cache import close_cache
from app.core.config import settings
from app.core.database import connect_db, disconnect_db
from app.core.discovery import feature_modules
from app.core.exceptions import register_exception_handlers
from app.core.jobs import Worker, get_store
from app.core.logging import configure_logging
from app.core.mcp import ApiKeyGate, attach_tools, mcp  # MCP (remove with core/mcp.py)
from app.core.metrics import render_metrics
from app.core.middleware import install_middleware
from app.core.observability import setup_otel, setup_sentry
from app.shared.schemas import ApiResponse

log = logging.getLogger(__name__)


async def _shutdown_worker(stop: asyncio.Event, task: asyncio.Task[None]) -> None:  # INFRA
    stop.set()
    await task


def _metrics_guard(request: Request) -> bool:
    token = settings.metrics_token
    if token is None:
        return True
    sent = request.headers.get("authorization", "")
    return secrets.compare_digest(sent, f"Bearer {token.get_secret_value()}")


def create_app() -> FastAPI:
    configure_logging()
    setup_sentry()
    feature_modules("jobs")  # INFRA: the API must know every @job_handler to validate enqueue
    if settings.env == "prod" and settings.cache_backend == "memory":  # INFRA
        log.warning(
            "cache backend is 'memory' in prod: it is per-process and cannot be "
            "invalidated across processes; use redis"
        )
    mcp_app = None
    if settings.mcp_enabled:  # MCP
        feature_modules("tools")  # MCP: importing registers every @mcp_tool
        attach_tools()  # MCP
        mcp_app = mcp.streamable_http_app()  # MCP: build before lifespan starts

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            await connect_db()
            stack.push_async_callback(disconnect_db)
            stack.push_async_callback(close_cache)  # INFRA
            await activity.start()  # INFRA
            stack.push_async_callback(activity.stop)  # INFRA: flush before DB disconnect
            if settings.worker_embedded:  # INFRA
                stop = asyncio.Event()
                task = asyncio.create_task(Worker(get_store()).run(stop))
                stack.push_async_callback(_shutdown_worker, stop, task)  # INFRA
            if settings.mcp_enabled:  # MCP
                await stack.enter_async_context(mcp.session_manager.run())  # MCP
            try:
                yield
            finally:
                app.state.shutting_down = True  # INFRA: readiness fails fast during shutdown

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None if settings.env == "prod" else "/docs",
        redoc_url=None,
        responses={
            code: {"model": ApiResponse[object], "description": description}
            for code, description in (
                (400, "Bad request"), (401, "Unauthorized"), (403, "Forbidden"),
                (404, "Not found"), (405, "Method not allowed"), (409, "Conflict"),
                (412, "Precondition failed"), (413, "Payload too large"),
                (422, "Validation failed"), (428, "Precondition required"),
                (429, "Too many requests"), (500, "Internal server error"),
                (503, "Service unavailable"),
            )
        },
    )
    app.state.shutting_down = False
    install_middleware(app)
    register_exception_handlers(app)
    for module in feature_modules("router"):
        app.include_router(module.router, prefix=settings.api_prefix)
    if settings.metrics_enabled:  # INFRA

        @app.get(
            "/metrics",
            include_in_schema=False,
            summary="Prometheus metrics",
            description="Render Prometheus metrics; token-guarded when METRICS_TOKEN is set.",
        )  # INFRA
        async def metrics(request: Request) -> Response:
            if not _metrics_guard(request):
                return Response("unauthorized", status_code=401)
            body, content_type = render_metrics()
            return Response(body, media_type=content_type)

    if mcp_app is not None:  # MCP
        gate: Any = ApiKeyGate(mcp_app)
        app.mount(settings.mcp_mount_path, gate)  # MCP
    setup_otel(app)
    return app


app = create_app()
