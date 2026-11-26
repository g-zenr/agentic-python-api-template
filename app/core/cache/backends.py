"""Cache backends: in-memory (dev/test, per-process) and Redis (production, shared)."""

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Protocol

from app.core.config import settings
from app.core.constants import CachePolicy


class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def incr(self, key: str) -> int: ...
    async def incr_window(self, key: str, ttl: int) -> tuple[int, int]: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class MemoryBackend:
    """TTL + LRU. Scope-version counters and rate windows live in side dicts so LRU never evicts them."""  # noqa: E501

    def __init__(self, max_items: int | None = None, clock: Callable[[], float] = time.monotonic):
        self._data: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._counters: dict[str, int] = {}
        self._windows: dict[str, tuple[int, float]] = {}
        self._max = max_items or settings.cache_memory_max_items
        self._clock = clock

    async def get(self, key: str) -> bytes | None:
        if key in self._counters:
            return str(self._counters[key]).encode()
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= self._clock():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        self._data[key] = (self._clock() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def incr_window(self, key: str, ttl: int) -> tuple[int, int]:
        now = self._clock()
        count, expires = self._windows.get(key, (0, now + ttl))
        if expires <= now:
            count, expires = 0, now + ttl
        count += 1
        self._windows[key] = (count, expires)
        return count, max(0, int(expires - now))

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()
        self._counters.clear()
        self._windows.clear()


class RedisBackend:
    def __init__(self, url: str):
        from redis.asyncio import Redis  # lazy: memory mode needs no Redis

        self._r = Redis.from_url(
            url,
            socket_timeout=CachePolicy.SOCKET_TIMEOUT,
            socket_connect_timeout=CachePolicy.SOCKET_TIMEOUT,
        )

    async def get(self, key: str) -> bytes | None:
        return await self._r.get(key)

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        await self._r.set(key, value, ex=ttl)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._r.delete(*keys)

    async def incr(self, key: str) -> int:
        return int(await self._r.incr(key))

    async def incr_window(self, key: str, ttl: int) -> tuple[int, int]:
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl, nx=True)
            pipe.ttl(key)
            count, _, remaining = await pipe.execute()
        return int(count), max(0, int(remaining))

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self._r.aclose()


def build_backend() -> CacheBackend:
    if settings.cache_backend == "redis":
        return RedisBackend(settings.redis_url)
    return MemoryBackend()
