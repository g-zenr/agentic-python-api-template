"""Cache tests: TTL, LRU, scope counters, single-flight, fail-open, jitter (no Redis)."""

import asyncio

from app.core.cache import Cache, cached
from app.core.cache.backends import MemoryBackend
from app.core.constants import CacheNS, CacheTTL


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


async def test_set_get_and_ttl_expiry():
    clock = Clock()
    cache = Cache(MemoryBackend(clock=clock))
    await cache.backend.set("k", b"1", 10)
    assert await cache.backend.get("k") == b"1"
    clock.advance(11)
    assert await cache.backend.get("k") is None


async def test_lru_eviction():
    backend = MemoryBackend(max_items=2)
    await backend.set("a", b"1", 100)
    await backend.set("b", b"2", 100)
    await backend.get("a")  # touch a
    await backend.set("c", b"3", 100)  # evicts b (least recently used)
    assert await backend.get("a") == b"1"
    assert await backend.get("b") is None
    assert await backend.get("c") == b"3"


async def test_scope_counters_not_evicted():
    backend = MemoryBackend(max_items=1)
    await backend.incr("ver")  # counter
    await backend.set("a", b"1", 100)
    await backend.set("b", b"2", 100)  # evicts a from data, counters untouched
    assert await backend.get("ver") == b"1"


async def test_get_or_set_single_flight():
    cache = Cache(MemoryBackend())
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return 42

    results = await asyncio.gather(*[cache.get_or_set("x", factory, 60, int) for _ in range(20)])
    assert calls == 1
    assert results == [42] * 20
    assert cache.stats["misses"] == 1


async def test_cached_hit_and_invalidate():
    calls = 0

    @cached(CacheNS.USER, CacheTTL.SHORT, key=lambda i: i, type_=int)
    async def get(i):
        nonlocal calls
        calls += 1
        return i * 2

    assert await get(3) == 6
    assert await get(3) == 6
    assert calls == 1
    await get.invalidate(3)
    assert await get(3) == 6
    assert calls == 2


async def test_invalidate_scope_makes_old_unreachable():
    calls = 0

    @cached(CacheNS.NOTES, CacheTTL.SHORT, key=lambda u, p: p, type_=int, scope=lambda u, p: u)
    async def read(u, p):
        nonlocal calls
        calls += 1
        return p

    await read("u1", 1)
    await read("u1", 1)
    assert calls == 1
    await read.invalidate_scope("u1")
    await read("u1", 1)  # scope version bumped -> recompute
    assert calls == 2


async def test_none_not_cached_unless_cache_none():
    cache = Cache(MemoryBackend())
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return None

    assert await cache.get_or_set("n", factory, 60, int) is None
    assert await cache.get_or_set("n", factory, 60, int) is None
    assert calls == 2  # None not cached

    calls = 0
    assert await cache.get_or_set("n2", factory, 60, int | None, cache_none=True) is None
    assert await cache.get_or_set("n2", factory, 60, int | None, cache_none=True) is None
    assert calls == 1  # cached


class BoomBackend:
    async def get(self, key):
        raise RuntimeError("down")

    async def set(self, key, value, ttl):
        raise RuntimeError("down")

    async def delete(self, *keys):
        raise RuntimeError("down")

    async def incr(self, key):
        raise RuntimeError("down")

    async def close(self):
        return None


async def test_backend_error_degrades_to_miss():
    cache = Cache(BoomBackend())
    value = await cache.get_or_set("k", lambda: _ret(7), 60, int)
    assert value == 7
    assert cache.stats["errors"] >= 1


async def _ret(v):
    return v


async def test_invalid_cached_json_is_miss():
    cache = Cache(MemoryBackend())
    await cache.backend.set("k", b"not-json", 60)
    value = await cache.get_or_set("k", lambda: _ret(5), 60, int)
    assert value == 5


def test_jitter_within_ten_percent():
    for _ in range(50):
        jittered = Cache._jitter(100)
        assert 89 <= jittered <= 111
