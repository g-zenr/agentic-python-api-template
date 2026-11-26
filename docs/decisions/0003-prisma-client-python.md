# 0003 — Prisma Client Python

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need an async ORM with first-class Python typing and migrations. Options included SQLAlchemy,
Tortoise, and Prisma Client Python. Prisma's schema-first model, generated types, and migration
tooling fit an agentic workflow where the schema is a clear contract.

## Decision
Use Prisma Client Python (`prisma-client-py`, asyncio interface) against PostgreSQL. All data access
goes through repositories that subclass `BaseRepository`, which wraps a Prisma model delegate. The
single client lives in `core/database.py` and is connected/disconnected by the lifespan.

## Consequences
- Services and routers never touch Prisma directly; the repository is the seam.
- To swap the data layer later, reimplement repositories without changing services or routers.
- Migrations are append-only; destructive changes need an ADR.