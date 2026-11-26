# Runbook: Deployment and rollback

> Ship safely and roll back quickly.

## Deploy
1. CI green (quality, integration, security, docker).
2. Run migrations (one-shot `migrate` service) — expand first.
3. Roll out `api` and `worker`; watch `/health/ready` and error rate.

## Rollback
1. Re-deploy the previous image (keep the DB schema backward compatible — expand/contract).
2. If a migration is not backward compatible, roll forward with a fix; never edit applied migrations.
3. Confirm `/health/ready` 200 and a smoke test.

## Common mistakes
- Reverting code without a compatible schema.
- Skipping the health gate.

## See also
- [11 — Deployment](../11-deployment.md)
- [21 — Database operations](../21-database-operations.md)