"""Test configuration: force a test environment before any application import.

The whole suite is database-free and Redis-free: `connect_db` only runs inside the app lifespan,
which `httpx.ASGITransport` does not trigger. We set a dummy `DATABASE_URL` and the memory cache.
"""

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MCP_ENABLED", "true")
os.environ.setdefault("CACHE_BACKEND", "memory")
os.environ.setdefault("WORKER_EMBEDDED", "false")
os.environ.setdefault("ACTIVITY_ENABLED", "false")
os.environ.setdefault("AUDIT_FAIL_CLOSED", "false")

import pytest  # noqa: E402

from app.core import audit  # noqa: E402
from app.core.audit.repository import audit_repo  # noqa: E402
from app.core.cache import cache  # noqa: E402
from app.core.cache.backends import MemoryBackend  # noqa: E402
from app.core.jobs import set_store  # noqa: E402
from tests.fakes import FakeJobStore, ListAuditSink  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Give every test a clean in-memory cache backend."""
    cache.backend = MemoryBackend()
    cache.stats = {"hits": 0, "misses": 0, "errors": 0}
    cache._locks.clear()
    yield


@pytest.fixture
def audit_sink():
    """Install a list audit sink and yield it."""
    sink = ListAuditSink()
    audit.set_sink(sink)
    yield sink
    audit.set_sink(audit_repo)


@pytest.fixture
def fake_store():
    """Install a FakeJobStore and yield it."""
    store = FakeJobStore()
    set_store(store)
    yield store
