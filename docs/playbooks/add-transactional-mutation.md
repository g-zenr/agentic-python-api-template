# Playbook: Add a transactional mutation

> When to use, prerequisites, numbered steps, a checklist, and a worked example.

## When to use
Use this for any state change that must be atomic with its audit entry (and any job it enqueues).

## Prerequisites
- Read [../19-transactions-and-consistency.md](../19-transactions-and-consistency.md).

## Steps
1. **Open a transaction** in the service: `async with transaction():`.
2. **Do the write** via the repository (it joins the transaction automatically).
3. **Audit inside** the transaction: `await audit.record(...)` with before/after snapshots.
4. **Enqueue inside** if the mutation schedules work (atomic with the write).
5. **Invalidate cache after commit**: `await after_commit(lambda: cached_fn.invalidate(...))`.
6. **Test** with the list sink and a stubbed repository; run `make lint && make test`.

## Verification checklist
- [ ] Mutation wrapped in `transaction()`.
- [ ] `audit.record` inside the transaction.
- [ ] Cache invalidation via `after_commit`.
- [ ] Tests updated.
- [ ] `make lint && make test && make feature-check` pass.

## Worked example
`notes.update` opens a transaction, updates with `update_versioned`, audits the diff, and invalidates
the notes scope after commit.