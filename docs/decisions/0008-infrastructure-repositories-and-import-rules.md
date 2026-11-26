# 0008 — Infrastructure repositories and import rules

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Jobs, audit and activity are infrastructure, not business features, but they need data access. We
must keep layering clean and let features stay thin HTTP surfaces over that infrastructure.

## Decision
Infrastructure modules own their repositories: `core/jobs/store.py`, `core/audit/repository.py`,
`core/activity/repository.py`. Features `jobs` and `audit` are thin HTTP surfaces over them.
`core/` never imports `features/`. A feature may import another feature's `service`, `repository`,
`deps` and `schemas` — never its `router`. `main.py` changed in this release to wire infrastructure
(DB, cache, activity, embedded worker, MCP); after this, adding jobs, cached reads or audit events
never requires editing `main.py`.

## Consequences
- Infrastructure is reusable and testable in isolation; features stay small.
- The import rule keeps routers decoupled (no router-to-router imports).
- `main.py` is now stable infrastructure wiring, not a per-feature edit point.