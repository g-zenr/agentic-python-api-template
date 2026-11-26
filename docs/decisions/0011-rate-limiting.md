# 0011 — Rate limiting

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need to stop abuse (brute force, floods) without a new dependency, and without leaking whether an
account exists.

## Decision
Fixed-window counters on the cache backend (`incr_window`), fail-open on backend errors. Global
per-IP limit plus per-IP and per-account limits on sensitive routes (login/refresh/forgot/register).
Account lockout counts failed logins only and is keyed by the email hash, so unknown emails behave
identically. Rejections increment a metric and set `Retry-After`.

## Consequences
- No broker; the cache is the limiter (Redis in prod).
- Fail-open means a cache outage does not lock users out.
- Fixed windows allow brief bursts at boundaries (acceptable).