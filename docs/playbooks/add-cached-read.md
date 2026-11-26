# Playbook: Cache a read

> When to use, prerequisites, numbered steps, a verification checklist, and worked examples.

## When to use
Use this for reads that are hot or expensive and tolerate short staleness (bounded by the TTL).

## Prerequisites
- The read is a service function; you have read [../15-caching.md](../15-caching.md).

## Steps
1. **Choose `CacheNS` and `CacheTTL`** from `app/core/constants.py` (add a `CacheNS` member if none fits).
2. **Decorate the service function**:
   ```python
   @cached(CacheNS.USER, CacheTTL.SHORT, key=lambda user_id: user_id, type_=User)
   async def find(user_id: str) -> User | None: ...
   ```
   For collections, add `scope=lambda ...: user.id` so the whole scope can be invalidated at once.
   `type_` must be a pydantic-serializable type.
3. **List EVERY write path** that affects the value and add `find.invalidate(id)` (single) or
   `list.invalidate_scope(user.id)` (scope) after the write.
4. **Tests**: hit (factory once), miss, invalidation (value recomputed).
5. **README** Business rules (Cache) lists the entries and invalidators.
6. **Verify**: `make lint && make test && make feature-check`.

## Verification checklist
- [ ] `CacheNS`/`CacheTTL` chosen (member added if needed).
- [ ] Function decorated with `key`/`scope`/`type_`.
- [ ] Every write path invalidates; listed in the README.
- [ ] Tests cover hit/miss/invalidation.
- [ ] `make lint && make test && make feature-check` pass.

## Worked examples
- `users.find` — single entry `user:<id>`, invalidated by `update_me`.
- `notes.list_notes` — scoped `notes:<user_id>:v<N>:<page>:<size>`, invalidated by create/update/delete.