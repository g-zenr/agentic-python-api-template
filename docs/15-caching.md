# 15 — Caching

> A fail-open cache facade with short TTLs, user-scoped keys, and explicit invalidation.

## What you will learn
- The principles that keep a cache safe.
- Key layout, backends, and the `@cached` decorator.
- The TTL table, stampede protection, jitter, and negative caching.
- The invalidation table and the multi-process caveat.

## Principles
- The cache is **never a source of truth**: any backend error degrades to a miss.
- **Short TTLs** bound staleness; invalidation handles correctness.
- **User-scoped keys**: never cache user-specific data under a key without the user id.
- **Fail-open**: a Redis outage slows things down, it does not break the API.

## Key layout and backends
```
<prefix>:<ns>:<parts...>            # plain entry; invalidate with delete
<prefix>:<ns>:<scope>:v<N>:<parts>  # scoped entry; invalidate the whole scope in O(1)
```
Backends: `MemoryBackend` (dev/test, per-process, TTL + LRU with a separate counter dict so scope
versions are never evicted) and `RedisBackend` (prod, shared). `CACHE_BACKEND` selects one.

## Using `@cached`
```python
@cached(CacheNS.USER, CacheTTL.SHORT, key=lambda user_id: user_id, type_=User)
async def find(user_id: str) -> User | None: ...


@cached(
    CacheNS.NOTES,
    CacheTTL.SHORT,
    type_=tuple[list[Note], int],
    key=lambda user, params: (params.page, params.size),
    scope=lambda user, params: user.id,
)
async def list_notes(user, params): ...
```
The wrapped function gains `.invalidate(*args)` (exact entry) and `.invalidate_scope(value)`.
Only values a pydantic `TypeAdapter(type_)` can round-trip may be returned; a schema change that
no longer validates is treated as a miss.

## TTLs, stampede, jitter, negative caching
| Constant | Seconds | Use |
|---|---|---|
| `CacheTTL.NEGATIVE` | 15 | caching a `None` result |
| `CacheTTL.SHORT` | 60 | user/notes reads |
| `CacheTTL.MEDIUM` | 300 | less volatile data |
| `CacheTTL.LONG` | 3600 | rarely changing data |

- **Single-flight**: concurrent misses for one key run the factory once (per process).
- **Jitter**: TTLs get ±10% (`CacheTTL.JITTER`) to avoid synchronized expiry.
- **Negative caching**: `None` is cached for `CacheTTL.NEGATIVE` only when `cache_none=True`.

## Invalidation table
| Write path | Invalidates |
|---|---|
| `users.update_me` | `user:<id>` (`find.invalidate`) |
| `notes.create` / `update` / `delete` | `notes:<user_id>` scope (`list_notes.invalidate_scope`) |

Every new write path that affects a cached value MUST invalidate it, and the feature README lists it.

## HTTP caching
Responses default to `Cache-Control: no-store` (set by middleware). Job polling overrides with
`private, no-cache` and uses `ETag`/`If-None-Match` (304). See chapter 13.

## Multi-process caveat
The memory backend is per-process, so in production with more than one process use Redis
(`CACHE_BACKEND=redis`). The compose Redis uses `volatile-lru` so scope-version counters (which
have no TTL) are never evicted. In `prod` with the memory backend, startup logs a warning.

## Common mistakes
- Caching user data under a key without the user id (cross-user leak).
- A write path that forgets to invalidate (stale reads until TTL).
- Treating the cache as authoritative.
- Using the memory backend across multiple processes.

## See also
- [Playbook: cache a read](playbooks/add-cached-read.md)
- [05 — Configuration and constants](05-configuration-and-constants.md)
- [ADR 0007](decisions/0007-cache-design.md)