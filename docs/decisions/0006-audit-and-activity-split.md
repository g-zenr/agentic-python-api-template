# 0006 — Audit and activity split

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need two very different logs: a durable "who changed what" trail for compliance, and a
high-volume "every request" stream for ops. Mixing them would either lose audit durability or
overload the request path.

## Decision
Keep them separate:
- **Audit** (`audit_logs`): written synchronously via `audit.record(...)` in services, durable,
  append-only (type-level `ReadRepository` + DB trigger blocking `UPDATE`), kept long
  (`AUDIT_RETENTION_DAYS`, 0 = forever).
- **Activity** (`activity_logs`): written by middleware into a best-effort batched buffer, high
  volume, kept short (`ACTIVITY_RETENTION_DAYS`).
Neither has an FK to `users`, so logs outlive users. A mutable `RequestContext` (ContextVar) lets
dependencies enrich the entry and middleware read it after `call_next`; jobs build their own.
Failure policy is **fail-open** (log the entry as JSON at ERROR, continue); `AUDIT_FAIL_CLOSED`
raises. A transactional outbox is out of scope for now (documented gap).

## Consequences
- Audit is trustworthy and queryable; activity is cheap and disposable.
- Append-only is enforced twice (type + trigger).
- The fail-open default means an audit outage never breaks a request; the fallback log line is the
  recovery path.
- PII (IP, user agent, attempted email) is stored — treat as sensitive.
- No outbox yet: a crash between the DB write and the audit write can drop an entry (logged).