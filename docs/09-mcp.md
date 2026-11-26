# 09 — MCP

> What the Model Context Protocol server is, how tools are declared, and how to remove it.

## What you will learn
- What MCP is in five sentences.
- How `@mcp_tool` turns a function into a tool.
- Where the endpoint lives and how the API-key gate works.
- How to connect a client and how to remove MCP entirely.

## What MCP is
The Model Context Protocol (MCP) is an open standard that lets AI clients (like Claude Desktop or
Claude Code) call your functions as "tools". A tool is a typed function with a docstring; the
docstring and type hints become its schema. The server speaks JSON-RPC over **streamable HTTP**.
 FastMCP (from the official `mcp` SDK) implements the server. This template mounts it at `/mcp`
 and lets each feature contribute tools from its own `tools.py`.

## Declaring a tool
A feature adds `tools.py` and decorates an async function with `@mcp_tool`:

```python
from app.core.mcp import mcp_tool
from app.shared.utils.time import to_zone, utcnow


@mcp_tool
async def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time in an IANA timezone, e.g. Asia/Manila."""
    return to_zone(utcnow(), timezone).isoformat()
```

At startup, `create_app()` imports every feature's `tools` module (registering the functions) and
calls `attach_tools()`. The tool's name, parameter types, and docstring become its public schema.

## Endpoint and API-key gate
The server is mounted at `settings.mcp_mount_path` (default `/mcp`). When `MCP_API_KEY` is set,
`ApiKeyGate` requires `Authorization: Bearer <key>` on every request (constant-time compare);
otherwise the endpoint is open. Set `MCP_ENABLED=false` to turn the whole thing off.

## Connecting a client
For Claude Desktop / Claude Code, add a server entry pointing at `http://localhost:8000/mcp` (with
the bearer header if `MCP_API_KEY` is set). The client lists tools and calls them like any other.

## Removing MCP entirely
Delete `app/core/mcp.py` and the lines marked `# MCP` in `app/main.py`. No feature code changes;
`tools.py` files simply stop being imported. (See ADR 0000 for the rationale.)

## Common mistakes
- Importing `mcp` in feature routers (tools belong in `tools.py` only).
- Forgetting that the tool docstring IS the description clients see.
- Exposing secrets through a tool.

## See also
- [Playbook: add an MCP tool](playbooks/add-mcp-tool.md)
- [03 — Project structure](03-project-structure.md)
- Feature README: [health](../app/features/health/README.md)