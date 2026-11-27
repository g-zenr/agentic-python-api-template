"""Cache facade. The cache is NEVER a source of truth: every backend error degrades to a miss.

Key layout:  <prefix>:<ns>:<parts...>            (plain entry; invalidate with delete)
             <prefix>:<ns>:<scope>:v<N>:<parts>  (scoped entry; invalidate whole scope in O(1))
"""

import asyncio
import functools
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from pydantic import TypeAdapter, ValidationError

from app.core.cache.backends import CacheBackend, build_backend
from app.core.config import settings
from app.core.constants import CacheNS, CacheTTL
from app.core.metrics import cache_operations_total

log = logging.getLogger(__name__)


class CachedFn(Protocol):
    """A `@cached`-decorated function: callable, plus explicit invalidation hooks."""

    def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[Any]: ...

    async def invalidate(self, *args: Any, **kwargs: Any) -> None: ...

    async def invalidate_scope(self, value: object) -> None: ...


class Cache:
    def __init__(self, backend: CacheBackend):
        self.backend = backend
        self.stats = {"hits": 0, "misses": 0, "errors": 0}
        self._locks: dict[str, asyncio.Lock] = {}

    def key(self, ns: CacheNS, *parts: object) -> str:
        return ":".join((settings.cache_prefix, ns.value, *map(str, parts)))

    async def scoped_key(self, ns: CacheNS, scope: object, *parts: object) -> str:
        raw = await self._safe(self.backend.get(self.key(ns, scope, "ver")))
        return self.key(ns, scope, f"v{int(raw) if raw else 0}", *parts)

    async def invalidate_scope(self, ns: CacheNS, scope: object) -> None:
        await self._safe(self.backend.incr(self.key(ns, scope, "ver")))

    async def delete(self, key: str) -> None:
        await self._safe(self.backend.delete(key))

    async def rate_hit(self, bucket: str, identity: str, limit: int, window: int) -> int:
        """Count one hit; return retry-after seconds (0 when allowed). Fail-open on backend errors."""  # noqa: E501
        key = self.key(CacheNS.RATE, bucket, identity)
        result = await self._safe(self.backend.incr_window(key, window))
        if result is None:
            return 0
        count, remaining = result
        return remaining if count > limit else 0

    async def rate_peek(self, bucket: str, identity: str) -> int:
        key = self.key(CacheNS.RATE, bucket, identity)
        raw = await self._safe(self.backend.get(key))
        try:
            return int(raw) if raw else 0
        except (ValueError, TypeError):
            return 0

    async def rate_reset(self, bucket: str, identity: str) -> None:
        await self._safe(self.backend.delete(self.key(CacheNS.RATE, bucket, identity)))

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: int,
        type_: Any = Any,
        *,
        cache_none: bool = False,
    ) -> Any:
        adapter: TypeAdapter[Any] = TypeAdapter(type_)
        hit, value = await self._read(key, adapter)
        if hit:
            return value
        lock = self._locks.setdefault(key, asyncio.Lock())  # single-flight per key (per process)
        try:
            async with lock:
                hit, value = await self._read(key, adapter)  # double-check after waiting
                if hit:
                    return value
                self.stats["misses"] += 1
                value = await factory()
                if value is not None or cache_none:
                    seconds = ttl if value is not None else CacheTTL.NEGATIVE
                    await self._safe(
                        self.backend.set(key, adapter.dump_json(value), self._jitter(seconds))
                    )
                return value
        finally:
            if not lock.locked():
                self._locks.pop(key, None)

    async def _read(self, key: str, adapter: TypeAdapter[Any]) -> tuple[bool, Any]:
        raw = await self._safe(self.backend.get(key))
        if raw is None:
            cache_operations_total.labels(result="miss").inc()
            return False, None
        try:
            value = adapter.validate_json(raw)
        except ValidationError:  # schema changed since it was cached
            await self.delete(key)
            cache_operations_total.labels(result="miss").inc()
            return False, None
        self.stats["hits"] += 1
        cache_operations_total.labels(result="hit").inc()
        return True, value

    async def _safe(self, awaitable: Awaitable[Any]) -> Any:
        try:
            return await awaitable
        except Exception:
            self.stats["errors"] += 1
            cache_operations_total.labels(result="error").inc()
            log.warning("cache backend error (treated as miss)", exc_info=True)
            return None

    @staticmethod
    def _jitter(ttl: int) -> int:
        return max(1, int(ttl * (1 + random.uniform(-CacheTTL.JITTER, CacheTTL.JITTER))))


cache = Cache(build_backend())


async def close_cache() -> None:
    await cache.backend.close()


def cached(
    ns: CacheNS,
    ttl: int,
    *,
    key: Callable[..., object],
    type_: Any = Any,
    scope: Callable[..., object] | None = None,
    cache_none: bool = False,
) -> Callable[[Callable[..., Awaitable[Any]]], CachedFn]:
    """Cache an async function. `key`/`scope` receive the function's own arguments.

    The wrapped function gains `.invalidate(*args)` (exact entry) and `.invalidate_scope(value)`.
    Only values a pydantic TypeAdapter(type_) can round-trip may be returned.
    """

    def wrap(fn: Callable[..., Awaitable[Any]]) -> CachedFn:
        async def build_key(*a: Any, **kw: Any) -> str:
            parts = key(*a, **kw)
            parts = parts if isinstance(parts, tuple) else (parts,)
            if scope is None:
                return cache.key(ns, *parts)
            return await cache.scoped_key(ns, scope(*a, **kw), *parts)

        @functools.wraps(fn)
        async def inner(*a: Any, **kw: Any) -> Any:
            return await cache.get_or_set(
                await build_key(*a, **kw),
                lambda: fn(*a, **kw),
                ttl,
                type_,
                cache_none=cache_none,
            )

        async def invalidate(*a: Any, **kw: Any) -> None:
            await cache.delete(await build_key(*a, **kw))

        async def invalidate_scope(scope_value: object) -> None:
            await cache.invalidate_scope(ns, scope_value)

        inner.invalidate = invalidate  # type: ignore[attr-defined]
        inner.invalidate_scope = invalidate_scope  # type: ignore[attr-defined]
        return cast(CachedFn, inner)

    return wrap
