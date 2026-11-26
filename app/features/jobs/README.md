# Jobs feature

> Poll and cancel background jobs; the queue engine itself lives in `app/core/jobs/`.

## Status
`stable`. Since: 0.2.0. Owner files: this folder + the `Job` Prisma model (engine in `app/core/jobs/`).

## Purpose
Give clients a uniform way to poll the status of long-running work and to cancel it. Submission
happens in the owning feature (e.g. `POST /notes/export`), which returns `202` with a `Location`
header pointing here. This feature is a thin HTTP surface over `core/jobs/store.py`.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/jobs | CurrentUser | Paginated list of my jobs (optional `status` filter). |
| GET | /api/v1/jobs/{job_id} | CurrentUser | Poll one job. Supports `ETag`/`If-None-Match` (304) and `Retry-After`. |
| POST | /api/v1/jobs/{job_id}/cancel | CurrentUser | Cancel a QUEUED job or request cancellation of a RUNNING one. |

## Data model
Reads the `Job` model (owned by the engine). `JobOut` exposes `id, type, status, progress,
attempts, max_attempts, result, error, created_at, started_at, finished_at, updated_at`. The
stored `error` is a `Msg` key, translated on read.

## Business rules
- **Audit events**: `job.cancel` (with before/after snapshots) on every cancel attempt.
- **Cache**: none (job state must be fresh; polling responses use `Cache-Control: private, no-cache`).
- **Jobs**: this feature submits none; it observes and controls jobs created elsewhere.
- Ownership: a user sees only their own jobs; admins see any. Missing or foreign job → `404`.
- Terminal jobs (`SUCCEEDED`/`FAILED`/`CANCELLED`) cannot be cancelled → `409`.
- While RUNNING/QUEUED, responses carry `Retry-After`; the `ETag` changes only when the job changes.

## Dependencies
- `app/core/jobs/` (store, `enqueue`, `JobRecord`), `app/core/audit/`.
- `app/features/auth/deps.py` (`CurrentUser`).
- `app/shared/helpers/http.py` (ETag, poll headers).

## Extending
- New job types are declared in the owning feature's `jobs.py`; this feature needs no change.
- To add job control (e.g. retry), add a service function + route here.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.2.0 | 2026-11-26 | Added | Initial version: poll (ETag/304) and cancel over the core job engine |