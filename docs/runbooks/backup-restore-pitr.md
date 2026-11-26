# Runbook: Backup, restore and PITR

> How to back up, restore, and run a restore drill.

## Back up
- Enable WAL archiving + scheduled base backups (managed Postgres or `pg_basebackup`).
- Back up before any destructive migration.

## Restore
1. Provision a new Postgres instance.
2. Restore the base backup, then replay WAL to the target time (PITR).
3. Point `DATABASE_URL` at the restored instance; run `prisma migrate deploy`.
4. Verify `/health/ready` and a smoke query.

## Restore drill checklist
- [ ] Restore into an isolated instance.
- [ ] `prisma migrate deploy` applies cleanly.
- [ ] `/health/ready` is 200.
- [ ] A known row count matches.
- [ ] Record the measured RTO.

## Common mistakes
- Never testing restores.
- Restoring over production without a fresh backup.

## See also
- [21 — Database operations](../21-database-operations.md)