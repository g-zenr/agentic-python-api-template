# 0005 — PostgreSQL-backed job queue

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Slow work must run outside the request. Options: a dedicated broker (Redis/Celery/arq), a hosted
queue, or the database we already run. We want durability, inspectability, and no new operational
surface for a template.

## Decision
Use PostgreSQL as the queue: a `jobs` table claimed with `FOR UPDATE SKIP LOCKED`. Delivery is
**at-least-once**, so handlers MUST be idempotent. Slow endpoints return `202` + `Location` +
`Retry-After` and clients poll `GET /jobs/{id}` (ETag/304). Workers are `python -m app.worker`
(scale horizontally); `WORKER_EMBEDDED=true` runs one inside the API for dev. Scheduling uses
per-bucket dedupe keys so exactly one job per bucket exists. The `JobStore` protocol is the escape
hatch to swap the data layer later.

## Consequences
- No broker to operate; the queue is transactional with the data and inspectable via SQL.
- At-least-once means handlers must be idempotent (documented and tested).
- Polling (not websockets) keeps the contract simple and cache-friendly.
- Very high throughput would eventually favor a dedicated broker; the protocol allows that swap.