# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
Semantic Versioning. The app version is defined ONLY in `pyproject.toml`.

## [0.3.0] - 2026-11-26

### Added
- Production hardening: prod config guard, security headers, body-size limit, trusted hosts,
  fixed-window rate limiting (global + login/refresh/forgot/register) with account lockout.
- Token model: short-lived access tokens with `token_version`, rotating refresh tokens with
  reuse detection, one-time tokens for email verification and password reset; `logout`,
  `logout-all`, `change-password`, `verify-email`, `forgot/reset-password`.
- RBAC (`require_permission`, `Permission`), per-client scoped MCP keys (`MCP_CLIENTS`),
  `scripts/mcp_key.py`, `scripts/create_admin.py`.
- Account lifecycle: `DELETE /users/me` (anonymize + scheduled erase), `POST /users/me/export`
  (202 job); `account.erase`/`account.export` handlers; audit PII scrubbing.
- Unit of work (`transaction()`, `after_commit`); repositories join the active transaction and
  are constructed by model name; audit writes inside a transaction propagate.
- API conventions: cursor pagination (audit/activity), sort/filter on notes, optimistic
  concurrency (`If-Match`/`version`), idempotency (`Idempotency-Key`), deprecation helper.
- Observability: JSON logging with redaction, Prometheus `/metrics` (token-guarded), Sentry and
  OpenTelemetry hooks, `/health/live` + `/health/ready`.
- CI (quality/integration/security/docker), dependabot, pre-commit, LICENSE, CONTRIBUTING,
  SECURITY, k6 loadtest, Prometheus alerts, runbooks, and `make typecheck/test-cov/security`.

### Changed
- `AdminUser`/`INSUFFICIENT_ROLE` replaced by permission-based RBAC; failed-login audit stores
  `email_hash`, never the email; `MCP_API_KEY` replaced by `MCP_CLIENTS`; access TTL 15 min.
- Migrations are a single `production_hardening` migration applied after all schema changes;
  audit trigger now allows scrubbing `ip`/`user_agent` to NULL only.

## [0.2.0] - 2026-11-26

### Added
- Background jobs: PostgreSQL-backed queue (`jobs` table, `FOR UPDATE SKIP LOCKED`), a standalone
  worker (`python -m app.worker`) plus an embedded dev worker, at-least-once delivery with
  retries/backoff/heartbeat/stale-reaper, a scheduler with bucketed dedupe, and the `jobs` feature
  (`GET /jobs`, `GET /jobs/{id}` with ETag/304 + `Retry-After`, `POST /jobs/{id}/cancel`).
- `POST /notes/export` (202 + `Location` + `Retry-After`) backed by the idempotent `notes.export` job.
- Audit logging (`audit_logs`, append-only by type + DB trigger) with `audit.record(...)` and the
  `audit` feature (`GET /audit`, `/audit/me`, `/audit/activity`).
- Activity logging (`activity_logs`, batched best-effort writer) via middleware.
- Core cache facade (`app/core/cache`) with memory + Redis backends, scoped invalidation,
  single-flight, jitter, and negative caching; `@cached` used by `users.find` and `notes.list_notes`.
- `maintenance` feature with scheduled `purge_logs` (hourly) and `purge_jobs` (daily) handlers.
- Redis service in docker-compose; `make worker` target.
- Docs: chapters 13 (background jobs), 14 (audit & activity), 15 (caching); playbooks
  add-background-job / add-cached-read / add-audit-event; ADRs 0005-0008.

### Changed
- `auth`, `users`, `notes` now emit audit events; `users.find` and `notes.list_notes` are cached;
  `notes` gained the async export job.
- `BaseRepository` split into `ReadRepository` (read-only) and `BaseRepository` (read+write);
  infrastructure logs use `ReadRepository` for type-enforced append-only.
- Middleware now records request activity and sets `Cache-Control: no-store` by default
  (job polling overrides with `private, no-cache`).
- `scripts/check_feature.py` now also fails on orphaned `JobType`/`CacheNS`/`Audit*` members,
  unaudited mutations, and JobType/handler mismatches.

## [0.1.0] - 2026-11-26

### Added
- Feature-based FastAPI + Prisma + PostgreSQL template designed for agentic coding.
- Core framework: centralized config, constants, `Msg` messages with `en`/`fil` locales,
  request context (id + locale), structured logging, typed error envelope, argon2 + JWT security.
- Shared helpers: `ApiResponse` envelope, pagination, generic `BaseRepository`, time/text/json utils.
- Auto-discovery of feature routers and MCP tools; `main.py` never changes per feature.
- Features: `health` (liveness + `get_current_time` MCP tool), `auth` (register/login +
  `CurrentUser`/`AdminUser`), `users` (profile + admin listing), `notes` (golden-reference CRUD).
- Optional MCP server (streamable HTTP at `/mcp`) with API-key gate.
- Feature lifecycle tooling: `scripts/new_feature.py`, `remove_feature.py`, `check_feature.py`,
  playbooks, and the `docs/features.md` registry.
- Documentation book under `docs/` and agent rulebook in `AGENTS.md`.
- Test suite: docs, lifecycle, i18n, mcp, health, and feature tests (DB-free).
- Docker + docker-compose for local Postgres and the API.