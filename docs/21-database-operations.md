# 21 — Database operations

> Pool sizing, timeouts, PgBouncer, expand/contract migrations, and backups.

## What you will learn
- How to size the connection pool.
- The timeouts and `DIRECT_DATABASE_URL`.
- PgBouncer notes.
- Expand/contract migrations and backup/PITR.

## Pool sizing
Total connections ≈ `WEB_CONCURRENCY × DB_CONNECTION_LIMIT + worker connections` must stay under
Postgres `max_connections`. `build_database_url()` appends `connection_limit` and `pool_timeout`
unless already present.

## Timeouts
`DB_POOL_TIMEOUT_SECONDS` (wait for a connection), `DB_TX_TIMEOUT_MS` (transaction), and
`STATEMENT_TIMEOUT`/`idle_in_transaction_session_timeout` set by `docker/postgres-init.sql`.

## PgBouncer
Use `DIRECT_DATABASE_URL` for migrations (session mode) and `pgbouncer=true` on the pooled URL so
Prisma disables prepared statements.

## Migrations
Expand/contract: add columns/tables (expand), backfill, switch reads/writes, then drop (contract).
Never edit an applied migration. `make migrate` for dev, `prisma migrate deploy` in prod.

## Backups & PITR
Enable WAL archiving + base backups; test restores (see the runbook). Back up before destructive
migrations.

## Common mistakes
- Too many workers × pool > max_connections.
- Running migrations through PgBouncer.
- Editing old migrations.

## See also
- [07 — Database](07-database.md)
- [11 — Deployment](11-deployment.md)
- `docs/runbooks/backup-restore-pitr.md`