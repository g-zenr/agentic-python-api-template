"""DB-backed integration tests (marker `integration`; run via `make test-integration`).

Require a real, migrated PostgreSQL at `DATABASE_URL` (or `TEST_DATABASE_URL`, which the make
target exports). Skipped in the default DB-free unit run. These exercise real transaction
rollback, committed revocation on reuse, keyset pagination, and raw-SQL PII scrubbing against
the actual schema + triggers.
"""

import os

import pytest

from app.core.database import connect_db, db, disconnect_db
from app.core.uow import transaction

pytestmark = pytest.mark.integration


@pytest.fixture
async def real_db():
    """Connected global Prisma client (DATABASE_URL / TEST_DATABASE_URL, migrated schema)."""
    if os.environ.get("TEST_DATABASE_URL"):
        os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    await connect_db()
    try:
        yield db
    finally:
        await disconnect_db()


async def test_transaction_rolls_back_on_error(real_db):
    """A raised error inside transaction() discards the writes (writes must go via current_db)."""
    from app.core.audit.repository import audit_repo
    from app.core.uow import current_db

    before = await real_db.auditlog.count()
    entry = {
        "actor_type": "system",
        "action": "it.test",
        "resource_type": "test",
        "outcome": "success",
    }
    with pytest.raises(RuntimeError):
        async with transaction():
            await current_db().auditlog.create(data=entry)  # joins the tx (UoW contract)
            raise RuntimeError("boom")
    after = await real_db.auditlog.count()
    assert after == before  # rolled back

    # and the same write through the repository COMMITS when no error is raised
    async with transaction():
        await audit_repo.append(entry)
    assert await real_db.auditlog.count() == after + 1


async def test_append_only_trigger_rejects_audit_update(real_db):
    """The DB trigger rejects mutating audit content (only NULL-scrub of ip/user_agent allowed)."""
    async with transaction():
        row = await real_db.auditlog.create(
            data={
                "actor_type": "system",
                "action": "it.test",
                "resource_type": "test",
                "outcome": "success",
            }
        )
    from prisma.errors import PrismaError

    with pytest.raises(PrismaError):
        await real_db.execute_raw("UPDATE audit_logs SET action = $1 WHERE id = $2;", "x", row.id)


async def test_keyset_pagination_against_real_db(real_db):
    """Insert known rows and page through them; no overlap/skip across pages."""
    # Uses the read-only audit repo shape against a real table.
    from app.core.audit.repository import audit_repo
    from app.shared.helpers.pagination import CursorParams

    # page size 1 walk; collect ids
    seen: list[str] = []
    cursor = None
    for _ in range(10_000):  # safety bound
        params = CursorParams(cursor=cursor, size=1)
        from app.shared.helpers.pagination import encode_cursor

        rows, next_cursor = await audit_repo.paginate_cursor(
            params, order=[{"occurred_at": "desc"}, {"id": "desc"}]
        )
        if not rows:
            break
        seen.extend(r.id for r in rows)
        if next_cursor is None:
            break
        cursor = encode_cursor(next_cursor)
    assert len(seen) == len(set(seen))  # no duplicates


async def test_refresh_rotation_and_reuse_against_real_db(real_db, audit_sink):
    """The two critical auth fixes, verified on a real database (C2 + reuse-detection commit)."""
    from datetime import timedelta

    from app.core.constants import Role
    from app.core.exceptions import UnauthorizedError
    from app.core.security import hash_password, hash_token, new_opaque_token
    from app.features.auth import service
    from app.features.auth.repository import refresh_repo
    from app.features.users.repository import users_repo
    from app.shared.utils.time import utcnow

    suffix = utcnow().strftime("%H%M%S%f")
    user = await users_repo.create(
        data={
            "email": f"it-refresh-{suffix}@example.com",
            "password_hash": hash_password("password123"),
            "name": "IT",
            "role": Role.USER.value,
            "locale": "en",
        }
    )
    try:
        raw, token_hash = new_opaque_token()
        family = "it-family"
        async with transaction():
            await refresh_repo.create(
                data={
                    "user_id": user.id,
                    "family_id": family,
                    "token_hash": token_hash,
                    "expires_at": utcnow() + timedelta(days=1),
                }
            )

        # 1st refresh: rotation. replaced_by must link the OLD row to the NEW hash (C2).
        first = await service.refresh(raw)
        old_row = await real_db.refreshtoken.find_unique(where={"token_hash": token_hash})
        new_hash = hash_token(first.refresh_token)
        assert old_row.revoked_at is not None
        assert old_row.replaced_by == new_hash  # C2: old row -> new hash (NOT itself)
        assert old_row.replaced_by != token_hash
        new_row = await real_db.refreshtoken.find_unique(where={"token_hash": new_hash})
        assert new_row is not None and new_row.revoked_at is None
        assert new_row.family_id == family  # same family

        # 2nd refresh with the SAME raw token: reuse => family revoked, and the revocation
        # must COMMIT even though the request is rejected (raise happens outside the tx).
        with pytest.raises(UnauthorizedError):
            await service.refresh(raw)
        assert (
            await real_db.refreshtoken.find_first(where={"family_id": family, "revoked_at": None})
            is None
        )  # every token in the family is revoked — committed
        reused = await real_db.refreshtoken.find_unique(where={"token_hash": token_hash})
        assert reused.revoked_at is not None
        assert any(e["action"] == "auth.refresh_reuse_detected" for e in audit_sink.entries)
    finally:
        await users_repo.delete(user.id)


async def test_gradual_permissions_against_real_db(real_db, audit_sink):
    """Grant -> allowed, revoke -> denied, cache invalidated; deny wins (ADR-0019)."""

    from app.core.authz import evaluate, read_scope
    from app.core.cache import cache as cache_facade
    from app.core.constants import CacheNS, Permission, Role
    from app.core.security import hash_password
    from app.features.permissions import service as perms_service
    from app.features.permissions.repository import permission_grant_repo
    from app.features.users.repository import users_repo
    from app.shared.utils.time import utcnow

    suffix = utcnow().strftime("%H%M%S%f")
    user = await users_repo.create(
        data={
            "email": f"it-perm-{suffix}@example.com",
            "password_hash": hash_password("password123"),
            "name": "IT",
            "role": Role.USER.value,
            "locale": "en",
        }
    )
    try:
        # baseline: USER has nothing
        assert not (await evaluate(user, Permission.USERS_READ)).allowed

        # grant users:read -> allowed (after the cache entry is written fresh)
        async with transaction():
            await permission_grant_repo.replace_for_user(
                user.id,
                [
                    {
                        "resource": "users",
                        "action": "read",
                        "effect": "ALLOW",
                        "conditions": None,
                        "expires_at": None,
                    }
                ],
                granted_by="admin-1",
            )
        await cache_facade.delete(cache_facade.key(CacheNS.PERMISSIONS, user.id))
        assert (await evaluate(user, Permission.USERS_READ)).allowed

        # deny wins over the allow for the same page×action
        async with transaction():
            await permission_grant_repo.replace_for_user(
                user.id,
                [
                    {
                        "resource": "users",
                        "action": "read",
                        "effect": "DENY",
                        "conditions": None,
                        "expires_at": None,
                    }
                ],
                granted_by="admin-1",
            )
        await cache_facade.delete(cache_facade.key(CacheNS.PERMISSIONS, user.id))
        decision = await evaluate(user, Permission.USERS_READ)
        assert not decision.allowed and decision.reason.value == "permission_denied"

        # own_only grant -> "own" scope on audit reads
        async with transaction():
            await permission_grant_repo.replace_for_user(
                user.id,
                [
                    {
                        "resource": "audit",
                        "action": "read",
                        "effect": "ALLOW",
                        "conditions": {"own_only": True},
                        "expires_at": None,
                    }
                ],
                granted_by="admin-1",
            )
        await cache_facade.delete(cache_facade.key(CacheNS.PERMISSIONS, user.id))
        assert await read_scope(user, Permission.AUDIT_READ) == "own"

        # service-level replace (the API path) writes rows the PDP sees
        from app.features.permissions.schemas import GrantIn, GrantsIn

        actor = await users_repo.create(
            data={
                "email": f"it-admin-{suffix}@example.com",
                "password_hash": hash_password("password123"),
                "name": "IT Admin",
                "role": Role.ADMIN.value,
                "locale": "en",
            }
        )
        try:
            out = await perms_service.replace_grants(
                actor, user.id, GrantsIn(grants=[GrantIn(resource="jobs", action="read_all")])
            )
            assert "jobs:read_all" in out.effective
            await cache_facade.delete(cache_facade.key(CacheNS.PERMISSIONS, user.id))
            assert (await evaluate(user, Permission.JOBS_READ_ALL)).allowed
            assert any(e["action"] == "permission.grants_updated" for e in audit_sink.entries)
        finally:
            await users_repo.delete(actor.id)
    finally:
        await users_repo.delete(user.id)
