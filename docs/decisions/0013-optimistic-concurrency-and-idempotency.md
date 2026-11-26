# 0013 — Optimistic concurrency and idempotency

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Concurrent edits and retried creates cause lost updates and duplicates.

## Decision
Versioned resources carry `version`; `PATCH` requires `If-Match` (428 if missing, 412 if stale) and
responses set `ETag`. Create endpoints accept `Idempotency-Key`; a stored `(scope,key,request_hash)`
replays the response, mismatches 409, and in-progress 409. Records expire after
`IDEMPOTENCY_TTL_HOURS`.

## Consequences
- Clients must send `If-Match` to update and can safely retry creates.
- One extra table and a small purge job.