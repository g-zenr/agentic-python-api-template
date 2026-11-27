# Audit feature

> Read-only HTTP access to the audit trail (`audit_logs`) and the request activity log.

## Status
`stable`. Since: 0.2.0. Owner files: this folder + the `AuditLog` and `ActivityLog` Prisma models
(engines in `app/core/audit/` and `app/core/activity/`).

## Purpose
Expose the durable audit trail ("who changed what") and the high-volume activity log ("every
request") for inspection and compliance. Writes happen in the services via `audit.record(...)` and
middleware; this feature only reads.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/audit | AdminUser (`audit:read`) | Search audit entries (actor, action, resource, outcome, time range). |
| GET | /api/v1/audit/me | CurrentUser | My own audit entries. |
| GET | /api/v1/audit/activity | AdminUser (`activity:read`) | Request activity log (route templates, status, latency). |

## Data model
`AuditLog` (`audit_logs`): `occurred_at, actor_id (no FK), actor_type, action, resource_type,
resource_id, outcome, changes (JSON diff), metadata, request_id, ip, user_agent`.
`ActivityLog` (`activity_logs`): `occurred_at, user_id (no FK), method, path (route TEMPLATE),
status_code, duration_ms, request_id, ip`.

## Business rules
- **Audit events**: none emitted here (read-only); entries are produced by `auth`/`users`/`notes`/
  `jobs`/`maintenance`.
- **Cache**: none (audit must be fresh).
- **Jobs**: none.
- Append-only: `audit_logs` is enforced append-only at the type level (`ReadRepository`, no
  update/delete) and by a DB trigger that rejects `UPDATE`.
- **No foreign key to `users`** on either log: logs outlive user deletion.
- **Privacy**: entries store IP, user agent, and (on failed login) the attempted email; treat as PII.
- Retention: activity kept `ACTIVITY_RETENTION_DAYS`, audit kept `AUDIT_RETENTION_DAYS` (0 = forever),
  purged by the `maintenance` feature.

## Dependencies
- `app/core/audit/repository.py`, `app/core/activity/repository.py`.
- `app/features/auth/deps.py` (`CurrentUser`, `require_permission`).

## Extending
- New searchable filters: add to `AuditQuery`/`ActivityQuery`, apply them in `_audit_where`, and
  pass through to `paginate_cursor`.
- New audit actions are declared in `core/constants.py` (`AuditAction`) and recorded by the owner.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.2.0 | 2026-11-26 | Added | Initial version: read-only audit + activity search endpoints |
| 0.3.1 | 2026-11-26 | Fixed | Cursor pagination: keyset (seek) paging so pages don't repeat/skip; unknown cursor -> 422 |
| 0.4.0 | 2026-11-26 | Changed | `scrub_pii_for_actor` moved to repo; removed dead `search`; `require_permission` docs |