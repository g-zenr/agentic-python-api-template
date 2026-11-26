# 0015 — Prisma Client Python status

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need a typed async ORM with migrations; we must record the installed version and the escape hatch.

## Decision
Use Prisma Client Python (installed `prisma==0.15.0`) against PostgreSQL. Pinned in `pyproject.toml`.
The `JobStore`/repository seams and the `BaseRepository` abstraction are the escape hatch: to move to
SQLAlchemy + Alembic, reimplement the repositories (and the raw-SQL job store) without touching
services or routers. Blast radius: `app/core/database.py`, `app/core/jobs/store.py`, and the
repositories; services/routers/features are unaffected.

## Consequences
- Schema-first contract; migrations are append-only.
- A future ORM swap is localized to the data layer.
- Pin the version; re-check release recency when upgrading.