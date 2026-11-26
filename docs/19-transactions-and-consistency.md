# 19 — Transactions and consistency

> One database transaction per mutation, with the audit write and job enqueue inside it.

## What you will learn
- The unit of work and `after_commit`.
- Why audit and enqueue join the transaction.
- Pitfalls (unique violations abort a tx, nesting, long transactions).

## Unit of work
`async with transaction():` opens one tx (or joins the outer one). Repositories resolve their
delegate from `current_db()`, so they automatically join the active transaction. `after_commit(cb)`
runs `cb` only after a successful commit (cache invalidation); on error the callbacks are discarded.

## Same-transaction audit and enqueue
Mutations wrap the write + `audit.record(...)` (+ any `enqueue(...)`) in `transaction()`. Inside a
transaction an audit write error ALWAYS propagates (the mutation rolls back). Outside a transaction
the fail-open policy applies (log at ERROR, continue).

## Pitfalls
- A `UniqueViolationError` aborts the whole transaction — use `INSERT ... ON CONFLICT DO NOTHING`
  (the job store does) instead of catch-and-continue.
- Nested `transaction()` joins the outer; it does not create a savepoint.
- Keep transactions short; do slow work in a job, not inline.

## Common mistakes
- Doing I/O (email, HTTP) inside a transaction.
- Registering cache invalidation inline instead of `after_commit`.
- Catching a unique violation mid-transaction.

## See also
- [14 — Audit and activity logging](14-audit-and-activity-logging.md)
- [Playbook: add a transactional mutation](playbooks/add-transactional-mutation.md)
- [ADR 0009](decisions/0009-unit-of-work-and-same-transaction-audit.md)