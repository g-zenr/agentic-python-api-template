# Runbook: Stuck jobs

> Diagnose and recover jobs stuck in RUNNING or piling up in QUEUED.

## Inspect
```sql
SELECT id, type, attempts, heartbeat_at FROM jobs
WHERE status = 'RUNNING' AND heartbeat_at < now() - interval '120 seconds';
SELECT status, count(*) FROM jobs GROUP BY status;
SELECT type, count(*) FROM jobs WHERE status = 'FAILED' GROUP BY type;
```

## Recover
- The worker reaper requeues stale RUNNING jobs automatically (`JOB_STALE_SECONDS`).
- To force: set `heartbeat_at` far in the past; the next reap requeues it.
- Failed jobs stay FAILED after `max_attempts`; inspect the `error` (a Msg key) and logs.

## Common mistakes
- Deleting stuck jobs (lose work).
- Raising `max_attempts` blindly.

## See also
- [13 — Background jobs](../13-background-jobs.md)
- [incident-response.md](incident-response.md)