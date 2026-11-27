# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
Semantic Versioning. The app version is defined ONLY in `pyproject.toml`.

## [0.5.0] - 2026-11-27

### Added
- **API quality suite** (`tests/test_api_quality.py`): every route declares summary+description
  (caught `/metrics` missing both — fixed), the response envelope on success/error/404/405/422,
  security headers, and auth-required behavior.
- **API speed suite** (`tests/test_api_speed.py`, `-m speed`, `make test-speed`/`test-slo`):
  per-request latency SLO `API_SLO_MS` (**1000ms local / 2000ms deployed**, `.env.example` +
  setting) plus an aggregate p95 gate; runs in-process or against `API_BASE_URL`. Speed tests are
  not functional tests — they assert latency, not payloads.
- **ABAC + gradual permissions (ADR-0019)**: per-user, assignable page × action grants.
  - PDP `app/core/authz.py`: effective = role baseline ∪ ALLOW − DENY (deny always wins),
    cached per user (`CacheNS.PERMISSIONS`), invalidated on every grant write and on role change;
    fail-closed (`AUTHZ_FAIL_CLOSED`, enforced in prod) with baseline-degradation otherwise.
  - New `PermissionGrant` model (`permission_grants`) + migration `20261127000000_permission_grants`.
  - New `permissions` feature: `GET /permissions/catalog`, `GET|PUT /permissions/users/{id}`
    (ETag/If-Match + Idempotency-Key + rate limit), `DELETE /permissions/users/{id}/{grant_id}` —
    all gated by the new `permissions:manage` permission and audited (`permission.grants_updated`).
  - ABAC conditions vocabulary (`{"own_only": true}`): self-scoped reads on `/audit` and
    `/audit/activity` (results narrowed to the caller), owner-matched evaluation in `jobs`.
  - Grant expiry honoured by the PDP and purged by the `maintenance.purge_expired` job.
  - Catalog is derived from the `Permission` enum (`resource:action`) — new permissions appear
    in the assignable matrix automatically.

### Fixed
- **H1**: `PUT /permissions/users/{id}` now honors `Idempotency-Key` (`run_once` + replay
  header) — retries no longer double-execute.
- **H2**: privilege-escalation guards — self-targeting forbidden; modifying a `permissions:manage`
  holder requires an ADMIN role baseline (managers can't lock out managers/admins); DENY on
  `permissions:manage` rejected outright (deny beats the role baseline).
- **M1**: `expires_at` in the past is rejected (naive datetimes treated as UTC).
- **M2**: the role baseline now dominates `own_only` grants in `read_scope` — an own_only grant
  never narrows an ADMIN to self-scoped audit reads.
- **CI-breaking migration drift**: `permission_grants.updated_at` no longer carries a DB default
  (`@updatedAt` generates none), so the `prisma migrate diff --exit-code` drift check passes.
- `make typecheck` passes for the first time: the whole `app/` tree is clean under mypy strict
  (201 errors fixed: precise generics, typed `@cached`/`CachedFn` protocol, repository casts,
  typed `job_handler`/`ActivityBuffer`/middleware ASGI signatures, `Handler.type` renamed to
  `job_type` — it shadowed the builtin `type[...]` annotation).
- Dev `mypy` pinned to `1.17.1`: its compiled wheel is not blocked by locked-down Windows hosts
  (mypy 2.4.1's `librt` DLL was), so `make typecheck`/`make lint` run locally.

### Changed
- `get_current_user` reads the user **uncached** (`users_repo.get`) — H4 stale-authorization
  window eliminated (was 0.4.1; repeated here only because the sections were consolidated).

## [0.4.1] - 2026-11-27

### Fixed
- **H4 eliminated**: `get_current_user` reads the user **uncached** (`users_repo.get`), so
  `is_active`/`role`/`email_verified_at`/`token_version` changes take effect immediately on the
  auth path (no ~60s stale-cache authorization window). `users.find` cache retained for other reads.

### Added
- Coverage raised (81% -> 84%): `app.worker.main` process wiring; the worker loop
  (`run`/`_maintenance`/`_schedule`, queue gauges, stale reap, scheduler dedupe);
  `setup_sentry`/`setup_otel` (no-op / missing-package / init + scrub / disabled branches);
  metrics-wiring tests.

### Removed
- Unused `Header.DEPRECATION` / `Header.SUNSET` / `Header.LINK`.
- Reconciled docs: stale `AdminUser`/`require_role` references in `docs/08`, `docs/02`,
  `docs/playbooks/add-endpoint`, `docs/18`, `docs/playbooks/protect-an-endpoint`, and endpoint
  labels; `deprecate(...)` references replaced with FastAPI `deprecated=True` (helper removed in 0.4.0).
- Documented the `integration` test suite in `docs/10-testing.md` and `docs/03-project-structure.md`.

## [0.4.0] - 2026-11-26

### Added
- **H1 rate limits**: sensitive auth POSTs now rate-limited — `/logout`, `/logout-all`,
  `/change-password`, `/verify-email`, `/resend-verification`; previously-dead `RateBucket`s wired
  (`FORGOT_ACCOUNT` per-account on `forgot_password`, `RESEND_USER` per-user on `resend_verification`).
- **H3 metrics wired** (`app/core/metrics.py`): `http_requests_total`, `http_request_duration_seconds`
  (middleware, route template), `rate_limit_rejections_total` (middleware + `enforce`),
  `cache_operations_total` (hit/miss/error), `activity_dropped_total`, `jobs_processed_total`,
  `job_duration_seconds`, `jobs_queue_depth`, `jobs_oldest_queued_age_seconds` (worker +
  `JobStore.queue_stats`). `/metrics` no longer exposes zeros.
- **L5 integration tests**: `tests/integration/` (marker `integration`; `make test-integration`)
  for real transaction rollback, append-only trigger, keyset paging, and raw-SQL PII scrub.
- **M4 prod guard**: `AUDIT_FAIL_CLOSED`, `REQUIRE_EMAIL_VERIFICATION`, non-default `EMAIL_FROM`.

### Changed
- **M5** `create_admin` raises `BadInputError`/`ConflictError` (not bare `ValueError`) and resets
  `request_ctx`.

### Removed
- **M1** raw SQL moved out of `users.jobs` into `AuditRepository.scrub_pii_for_actor` /
  `ActivityRepository.scrub_ip_for_user`.
- **M3** dead `audit_repo.search` / `activity_repo.search`.
- **L1** dead helpers `slugify`, `iso`, `deprecate`; **L4** unused `_MAX`.
- **L3** stale docs: `AdminUser`/`require_role` -> `CurrentUser`/`VerifiedUser`/`require_permission`;
  documented **H4** cached-user staleness trade-off.

## [0.3.1] - 2026-11-26

### Fixed
- **Cursor pagination (`paginate_cursor`)**: replaced the broken cursor handling (which excluded
  only the cursor id and re-read from the start, returning repeated pages) with proper keyset
  ("seek") pagination ordered after the cursor row; pages no longer overlap/repeat/skip. Unknown
  cursor ids now raise `BadInputError`. Affects `audit` (`/audit`, `/audit/me`, `/audit/activity`).
- **Refresh-token rotation (`auth.refresh`)**: `replaced_by` now links the consumed (old) token
  row to the new token hash instead of pointing the new row at itself; replacement linking uses
  a new `RefreshTokenRepository.mark_replaced` (no raw `.d` access in the service).
- **Refresh-token reuse detection**: family revocation + audit now run in a committed transaction
  and are no longer rolled back by the rejection; the "lost the race to consume" path commits
  revocation before rejecting.
- Corrected `_issue_pair` return type annotation (`tuple[TokenOut, str, str]`).

### Changed
- Coverage gate restored: added keyset-pagination, audit-service, and auth-flow tests
  (register / refresh / reuse / logout / change-password / verify-email / reset-password /
  forgot-password / logout-all); suite green at 80%+ (`make test-cov`).

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