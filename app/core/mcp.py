"""Optional MCP (Model Context Protocol) server exposing selected functions as tools.

Targets the installed `mcp` 2.x SDK (`MCPServer`). Per-client scoped keys come from
`MCP_CLIENTS`; `attach_tools` enforces each client's tool list. Public names are unchanged.
"""

import functools
import hashlib
import logging
import secrets
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.context import mcp_client_var
from app.core.metrics import mcp_tool_calls_total

log = logging.getLogger(__name__)


class _ConfiguredServer(MCPServer):
    """Serve streamable HTTP at ``/``; mounted at ``/mcp`` this answers ``/mcp/``."""

    def streamable_http_app(self, **kwargs: Any) -> Any:
        kwargs.setdefault("streamable_http_path", "/")
        kwargs.setdefault("stateless_http", True)
        kwargs.setdefault("json_response", True)
        return super().streamable_http_app(**kwargs)


mcp = _ConfiguredServer(settings.app_name)
_tools: list[Callable[..., Any]] = []


def mcp_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: register `fn` as an MCP tool. Type hints + docstring become the tool schema."""
    _tools.append(fn)
    return fn


def registered_tools() -> list[str]:
    return [fn.__name__ for fn in _tools]


def attach_tools() -> None:
    for fn in _tools:
        mcp.tool()(_scoped(fn))


def _scoped(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        client = mcp_client_var.get()
        allowed = _client_tools(client)
        if allowed is not None and "*" not in allowed and fn.__name__ not in allowed:
            raise PermissionError(f"MCP client '{client}' may not call '{fn.__name__}'")
        mcp_tool_calls_total.labels(client=client or "open", tool=fn.__name__).inc()
        log.info("mcp tool call client=%s tool=%s", client, fn.__name__)
        return await fn(*args, **kwargs)

    return wrapper


def _client_tools(name: str | None) -> list[str] | None:
    if name is None:
        return None
    for client in settings.mcp_clients:
        if client.name == name:
            return client.tools
    return None


class ApiKeyGate:
    """ASGI wrapper: require a scoped bearer key from MCP_CLIENTS (open in dev when none set)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            clients = settings.mcp_clients
            if not clients:
                if settings.env != "prod":
                    await self.app(scope, receive, send)
                    return
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
            sent = dict(scope["headers"]).get(b"authorization", b"").decode()
            raw = sent[7:] if sent.startswith("Bearer ") else ""
            digest = hashlib.sha256(raw.encode()).hexdigest()
            match = next((c for c in clients if secrets.compare_digest(digest, c.key_sha256)), None)
            if match is None:
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
            mcp_client_var.set(match.name)
        await self.app(scope, receive, send)
