# Health feature

> Liveness probe plus a time MCP tool; the smallest possible feature.

## Status
`stable`. Since: 0.1.0. Owner files: this folder (no Prisma models).

## Purpose
Provide an unauthenticated endpoint that reports the service is up, and expose the current
time as an MCP tool so agents can verify connectivity and clock/timezone behavior.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/health | none | Returns `{status, version}` inside the standard envelope. Touches no database. |

MCP tools (see `tools.py`):
| Tool | Description |
|---|---|
| `get_current_time` | Current date/time in an IANA timezone (default `UTC`). |

## Data model
None. This feature stores nothing.

## Business rules
- The endpoint must never touch the database, so it works even when Postgres is down.
- The response `version` comes from `Settings.app_version` (read from `pyproject.toml`).

## Dependencies
- `app/core/config.py` (version), `app/core/constants.py` (`Tag.HEALTH`),
  `app/core/messages.py` (`Msg.HEALTH_OK`).
- `app/shared/utils/time.py` for the MCP tool.

## Extending
- Add more MCP tools in `tools.py` with `@mcp_tool`; they are auto-registered at startup.
- Do not add database access here; richer readiness belongs in a dedicated feature.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.1.0 | 2026-11-26 | Added | Initial version: health endpoint and get_current_time MCP tool |
| 0.3.0 | 2026-11-26 | Added | /health/live and /health/ready (DB+cache), hidden /health alias |
