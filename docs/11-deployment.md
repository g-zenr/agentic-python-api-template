# 11 — Deployment

> Containers, environment checklist, migrations in production, and a hardening list.

## What you will learn
- How the Docker image and compose stack fit together.
- The production environment checklist.
- How migrations run on deploy.
- A production hardening checklist.

## Containers
- **`Dockerfile`** — `python:3.12-slim`, installs `uv`, syncs dependencies
  (`--frozen --no-dev`), copies the source, runs `prisma generate`, drops to a non-root user, and
  on start runs `prisma migrate deploy` then `uvicorn`.
- **`docker-compose.yml`** — a `db` service (`postgres:16-alpine` with a `pg_isready`
  healthcheck and a named volume) and an `api` service built from the Dockerfile, reading
  `.env` with `DATABASE_URL` pointed at `db`, waiting for the database to be healthy, exposing
  port 8000.

```bash
docker compose up -d db     # start postgres only (local dev)
docker compose up -d        # start db + api
docker compose down         # stop
```

## Environment checklist (production)
- [ ] `ENV=prod` (disables `/docs`).
- [ ] `DATABASE_URL` set to the managed Postgres instance.
- [ ] `JWT_SECRET` a long random string (never the default).
- [ ] `CORS_ORIGINS` restricted to known origins.
- [ ] `MCP_ENABLED` / `MCP_API_KEY` set deliberately.

## Migrations in production
The container runs `prisma migrate deploy` on startup, applying any pending migrations. For
zero-downtime, run migrations as a separate step before rolling out new code. Never edit an
applied migration; add a new one.

## Hardening checklist
- [ ] Run as non-root (the Dockerfile already does).
- [ ] Terminate TLS at a reverse proxy; set `X-Forwarded-*` appropriately.
- [ ] Restrict CORS; require the MCP API key if MCP is exposed.
- [ ] Set `log_level` to `INFO` or lower in prod; ensure secrets are not logged.
- [ ] Add health/readiness probes against `/api/v1/health`.
- [ ] Back up the database before any destructive migration.

## Worker, Redis, retention
- Run at least one worker: `make worker` (`python -m app.worker`); scale horizontally. Set
  `WORKER_EMBEDDED=false` in production.
- Use Redis for the cache in production (`CACHE_BACKEND=redis`); the compose Redis uses
  `volatile-lru` so scope-version counters are never evicted.
- Retention: `ACTIVITY_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS` (0 = forever),
  `JOB_RETENTION_DAYS`; the `maintenance` feature purges on a schedule.
- Set `TRUST_PROXY_HEADERS=true` only behind a trusted proxy (it reads `X-Forwarded-For`).
- Health check: `GET /api/v1/health` (no DB); the compose `api` service health-checks it.

## Common mistakes
- Committing `.env` (it is gitignored).
- Using the default `JWT_SECRET` in production.
- Editing old migrations.

## See also
- [05 — Configuration and constants](05-configuration-and-constants.md)
- [07 — Database](07-database.md)
- [README](../README.md)