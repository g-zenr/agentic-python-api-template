# Runbook: Incident response

> Triage, mitigate, and communicate during an incident.

## Steps
1. **Detect**: alerts in `deploy/prometheus/alerts.yml` (5xx, latency, readiness, queue age).
2. **Triage**: check `/health/ready`, `jobs_queue_depth`, and recent JSON logs by `request_id`.
6. **Mitigate**: scale workers, roll back (see `deployment-rollback.md`), or disable a feature.
7. **Communicate**: post status; record the timeline.
8. **Review**: blameless postmortem; file follow-ups.

## Common mistakes
- Restarting without capturing logs.
- Dropping the queue (jobs are durable; let the reaper recover stuck ones).

## See also
- [stuck-jobs.md](stuck-jobs.md)
- [slo-and-alerts.md](slo-and-alerts.md)