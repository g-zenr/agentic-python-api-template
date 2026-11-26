# 0007 — Cache design

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Hot reads (user profile, a user's notes) hit the database repeatedly. We need caching that is safe
(never a source of truth), correct (explicit invalidation), and simple (one facade).

## Decision
One facade (`app/core/cache`) over two backends: `MemoryBackend` (dev/test, per-process, TTL + LRU)
and `RedisBackend` (prod, shared). Keys are `<prefix>:<ns>:<parts>` or, for collections,
`<prefix>:<ns>:<scope>:v<N>:<parts>` where `invalidate_scope` bumps a counter in O(1). Every
backend error degrades to a miss (fail-open). `@cached` adds single-flight per key, ±10% TTL
jitter, and negative caching (`None` for `CacheTTL.NEGATIVE`). Short TTLs bound staleness.

## Consequences
- Correctness comes from invalidation on every write path (listed in feature READMEs); TTLs are a
  backstop.
- The memory backend is per-process: in `prod` use Redis (`volatile-lru` so version counters are
  never evicted); startup warns if memory is used in prod.
- User-specific data MUST be keyed by user id (security rule).
- A schema change that no longer validates is treated as a miss (self-healing).