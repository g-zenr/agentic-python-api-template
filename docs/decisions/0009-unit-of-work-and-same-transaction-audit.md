# 0009 — Unit of work and same-transaction audit

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Mutations, their audit entries, and any enqueued jobs must be consistent. A crash between the write
and the audit write must not leave an unaudited change.

## Decision
One `transaction()` per mutation; repositories resolve their delegate from `current_db()` so they
join it. `audit.record` and `enqueue` run inside the transaction. Cache invalidation runs via
`after_commit`. Inside a transaction an audit error always propagates (rolls back); outside it the
fail-open policy applies. This closes the "no outbox" gap for the common case (a transactional
outbox remains out of scope for truly external side effects).

## Consequences
- Mutations are atomic with their audit trail.
- Repositories are constructed by model name and are transaction-aware.
- Long transactions are a hazard; keep them short and push slow work to jobs.