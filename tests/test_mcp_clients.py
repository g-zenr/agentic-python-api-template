"""MCP scoped clients: hashed-key auth and per-client tool scoping."""

import hashlib

from app.core.config import McpClientConfig, settings
from app.core.mcp import ApiKeyGate, _client_tools


class DummyApp:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True


def _scope(auth: str) -> dict:
    return {"type": "http", "headers": [(b"authorization", auth.encode())]}


async def _call(gate, scope):
    sent = False

    async def send(msg):
        nonlocal sent
        if msg["type"] == "http.response.start":
            sent = True

    async def receive():
        return {"type": "http.request"}

    await gate(scope, receive, send)
    return sent


async def test_valid_key_passes(monkeypatch):
    raw = "secret-key"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(settings, "mcp_clients", [McpClientConfig(name="c", key_sha256=digest)])
    inner = DummyApp()
    gate = ApiKeyGate(inner)
    await _call(gate, _scope(f"Bearer {raw}"))
    assert inner.called is True


async def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(
        settings,
        "mcp_clients",
        [McpClientConfig(name="c", key_sha256=hashlib.sha256(b"right").hexdigest())],
    )
    inner = DummyApp()
    gate = ApiKeyGate(inner)
    rejected = await _call(gate, _scope("Bearer wrong"))
    assert rejected is True and inner.called is False


def test_client_tools_lookup(monkeypatch):
    monkeypatch.setattr(
        settings, "mcp_clients", [McpClientConfig(name="c", key_sha256="h", tools=["a"])]
    )
    assert _client_tools("c") == ["a"]
    assert _client_tools(None) is None
