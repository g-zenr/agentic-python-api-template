# 0005 — Installed-version adaptations

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
The spec's code was written against `mcp` 1.x (`FastMCP`) and a POSIX assumption for time zones.
The installed SDK is `mcp` 2.x, the environment is Windows (no system tz database), and Ruff's
`B008`/`UP046` rules conflict with the spec's FastAPI idioms. The task allows adapting to the
installed library versions while keeping the architecture and public names.

## Decision
1. **MCP 2.x**: `FastMCP` was renamed to `MCPServer`; `stateless_http`/`json_response`/
   `streamable_http_path` moved from the constructor to `streamable_http_app(...)`. `app/core/mcp.py`
   now uses a thin `_ConfiguredServer(MCPServer)` subclass that injects those options, so the
   public names (`mcp`, `mcp_tool`, `registered_tools`, `attach_tools`, `ApiKeyGate`) and
   `app/main.py` are unchanged.
2. **`tzdata` dependency**: `zoneinfo` needs the IANA database, which is absent on Windows. Added
   `tzdata` to `dependencies` so `to_zone` (and the `get_current_time` MCP tool) work everywhere.
3. **Ruff `B008`**: FastAPI's `Depends`/`Query`/etc. in argument defaults are idiomatic but flagged
   by bugbear. Added `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` listing the FastAPI
   dependency markers. No feature code changed.
4. **pytest-asyncio loop scope**: set `asyncio_default_fixture_loop_scope = "function"` to silence the deprecation warning and pin deterministic behavior.
5. **Ruff `UP046`**: `ApiResponse` now uses PEP 695 type parameters (`class ApiResponse[T]`) instead
   of `Generic[T]`, matching the modern style Ruff enforces on Python 3.12.

## Consequences
- The architecture and all public names are preserved; only `app/core/mcp.py` internals differ.
- The project runs on Windows and POSIX; `make test` stays DB-free.
- `pyproject.toml` gains a `tzdata` dependency, a small `[tool.ruff.lint.flake8-bugbear]`
  block, and a pytest-asyncio loop-scope setting (the only deviations from the literal spec
  `pyproject.toml`).