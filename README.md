# Agentic API

A production-ready, **feature-based** FastAPI + Prisma + PostgreSQL template designed for agentic
coding. AI coding agents (OpenCode, Claude Code, …) read the docs, learn every convention, and add,
update, or remove features correctly — without asking questions.

## Quickstart
```bash
cp .env.example .env
docker compose up -d db redis
make install
make migrate
make dev            # API (embedded worker for dev)
make worker         # or run the worker separately
```
Then open http://localhost:8000/docs.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/health/live | none | Liveness (no deps). `/health` is a hidden alias. |
| GET | /api/v1/health/ready | none | Readiness (DB + cache). |
| POST | /api/v1/auth/register | none | Create an account, get tokens. |
| POST | /api/v1/auth/login | none | Log in, get tokens. |
| POST | /api/v1/auth/refresh | none | Rotate refresh token. |
| POST | /api/v1/auth/logout · /logout-all · /change-password | none/Bearer | Session management. |
| POST | /api/v1/auth/verify-email · /forgot-password · /reset-password | none | Account recovery. |
| GET | /api/v1/users/me | Bearer | Your profile. |
| PATCH | /api/v1/users/me | Bearer | Update your profile. |
| DELETE | /api/v1/users/me | Bearer | Delete (anonymize) your account. |
| POST | /api/v1/users/me/export | Bearer | Export your data (202). |
| GET | /api/v1/users | users:read | List users. |
| POST | /api/v1/notes | Bearer | Create a note (Idempotency-Key). |
| GET | /api/v1/notes | Bearer | List notes (?sort, ?q). |
| POST | /api/v1/notes/export | Bearer | Export notes (202). |
| GET/PATCH/DELETE | /api/v1/notes/{id} | Bearer | Get/update (If-Match)/delete. |
| GET | /api/v1/jobs · /jobs/{id} · POST /jobs/{id}/cancel | Bearer | Poll/cancel jobs. |
| GET | /api/v1/audit · /audit/me · /audit/activity | audit/activity:read | Logs (cursor). `own_only` grants narrow to your own rows. |
| GET | /api/v1/permissions/catalog | permissions:manage | Assignable page × action matrix (ABAC, ADR-0019). |
| GET/PUT | /api/v1/permissions/users/{id} | permissions:manage | Effective grants / replace grant set (If-Match + Idempotency-Key). |
| DELETE | /api/v1/permissions/users/{id}/{grant_id} | permissions:manage | Revoke one grant. |
| GET | /metrics | metrics token | Prometheus metrics. |

MCP (optional) is served at `/mcp` with per-client scoped keys (`MCP_CLIENTS`).

## For coding agents
Start at **[AGENTS.md](AGENTS.md)**. The full documentation book is at
**[docs/README.md](docs/README.md)**; the feature registry is **[docs/features.md](docs/features.md)**.

## Testing
`make test` runs a fully **database-free, Redis-free** suite. `make lint` runs ruff + `mypy` +
the feature audit. `make test-integration` runs the real DB/Redis suite. See
[docs/10-testing.md](docs/10-testing.md).

## Docker / Postgres
If Docker or Postgres is unavailable, skip `docker compose` and `make migrate`; the unit suite does
not need a database.

> **Note on locked-down Windows hosts:** an OS Application Control / Device Guard policy can block
> the Prisma schema engine (`schema-engine-windows.exe`) and some
> `.venv/Scripts/*.exe` shims. When that happens: run the API with
> `uv run python -m uvicorn app.main:app`; the migration SQL is committed under
> `prisma/migrations/` so `prisma migrate deploy` works on a normal host (or apply the SQL via
> `psql` inside the `db` container). Dev `mypy` is pinned to 1.17.1, whose compiled wheel is NOT
> blocked, so `make typecheck` runs locally. The end-to-end flow (register → login →
> refresh → notes CRUD → export job → audit → `/health/ready` → `/metrics`) was verified against a
> PostgreSQL container with equivalent SQL.