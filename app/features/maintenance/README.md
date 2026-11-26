# Maintenance feature

> Scheduled retention jobs (log purge, finished-job cleanup). No HTTP surface.

## Status
`stable`. Since: 0.2.0. Owner files: this folder (no Prisma models of its own; purges `Job`,
`AuditLog`, `ActivityLog`).

## Purpose
Run periodic housekeeping so the database does not grow unbounded: delete old activity/audit logs
and old finished jobs, and record each purge in the audit trail.

## Endpoints
none (this feature exposes only scheduled job handlers, no router).

## Data model
Deletes from `ActivityLog`, `AuditLog` (only when `AUDIT_RETENTION_DAYS > 0`), and `Job`
(terminal jobs older than `JOB_RETENTION_DAYS`). No schema of its own.

## Business rules
- **Audit events**: `retention.purge` (resource `log`) with metadata `{activity_deleted, audit_deleted}`.
- **Cache**: none.
- **Jobs**: handles `maintenance.purge_logs` (hourly) and `maintenance.purge_jobs` (daily).
- Both handlers are idempotent; the scheduler's per-bucket dedupe key guarantees one run per bucket
  across any number of workers.
- Deleting audit rows is allowed (only UPDATE is blocked by the DB trigger); the purge itself is audited.

## Dependencies
- `app/core/jobs/` (`job_handler`, `JobContext`), `app/core/audit/`, `app/core/activity/`.
- `app/core/config.py` retention settings.

## Extending
- Add a new scheduled handler here with `@job_handler(..., schedule_every=Schedule.DAILY)` and a
  matching `JobType` member in `core/constants.py`.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.2.0 | 2026-11-26 | Added | Initial version: hourly log purge and daily job purge |