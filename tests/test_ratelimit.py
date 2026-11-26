"""Rate limiting: window counting, Retry-After, lockout keyed by email hash, fail-open."""

import pytest

from app.core.cache import cache
from app.core.config import settings
from app.core.constants import RateBucket
from app.core.exceptions import RateLimitedError
from app.core.ratelimit import email_identity, enforce, peek, reset


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)


async def test_window_counts_and_blocks():
    await reset(RateBucket.LOGIN_IP, "1.1.1.1")
    await enforce(RateBucket.LOGIN_IP, "1.1.1.1", limit=2, window=60)
    await enforce(RateBucket.LOGIN_IP, "1.1.1.1", limit=2, window=60)
    with pytest.raises(RateLimitedError) as exc:
        await enforce(RateBucket.LOGIN_IP, "1.1.1.1", limit=2, window=60)
    assert exc.value.retry_after > 0


async def test_lockout_keyed_by_email_hash_identical():
    a = email_identity("User@Example.com")
    b = email_identity("user@example.com")
    assert a == b
    assert a != "user@example.com"  # raw email never used as a key


async def test_reset_clears():
    await enforce(RateBucket.LOGIN_IP, "2.2.2.2", limit=1, window=60)
    await reset(RateBucket.LOGIN_IP, "2.2.2.2")
    assert await peek(RateBucket.LOGIN_IP, "2.2.2.2") == 0


class Boom:
    async def get(self, key):
        raise RuntimeError("down")

    async def set(self, key, value, ttl):
        raise RuntimeError("down")

    async def delete(self, *keys):
        raise RuntimeError("down")

    async def incr(self, key):
        raise RuntimeError("down")

    async def incr_window(self, key, ttl):
        raise RuntimeError("down")

    async def ping(self):
        raise RuntimeError("down")

    async def close(self):
        return None


async def test_backend_failure_fails_open():
    cache.backend = Boom()
    await enforce(RateBucket.LOGIN_IP, "3.3.3.3", limit=1, window=60)  # must not raise
    assert cache.stats["errors"] >= 1
