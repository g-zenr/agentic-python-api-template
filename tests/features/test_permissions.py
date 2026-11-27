"""Permissions feature: catalog, effective set, grant replace/revoke, PDP wiring, audits."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import Permission, Role
from app.core.exceptions import BadInputError, ForbiddenError, NotFoundError
from app.features.permissions import service


def _user(role=Role.ADMIN, user_id="admin-1"):
    from prisma.models import User

    return User(
        id=user_id,
        email="a@example.com",
        password_hash="h",
        name="A",
        role=role.value,
        locale="en",
        is_active=True,
        token_version=0,
        email_verified_at=None,
        deleted_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class FakeGrantRepo:
    def __init__(self):
        self.rows: list[dict] = []
        self.replaced: list = []
        self.deleted: list = []
        self.purged = 0

    async def list_for_user(self, user_id):
        return [r for r in self.rows if r["user_id"] == user_id]

    async def get(self, grant_id):
        for r in self.rows:
            if r["id"] == grant_id:
                return r
        return None

    async def replace_for_user(self, user_id, grants, *, granted_by):
        self.replaced.append((user_id, len(grants)))
        self.rows = [r for r in self.rows if r["user_id"] != user_id]
        out = []
        for i, g in enumerate(grants):
            row = {
                "id": f"g{i}",
                "user_id": user_id,
                "resource": g["resource"],
                "action": g["action"],
                "effect": g["effect"],
                "conditions": g["conditions"],
                "granted_by": granted_by,
                "expires_at": g["expires_at"],
                "created_at": datetime(2026, 1, 1),
            }
            self.rows.append(row)
            out.append(row)
        return out

    async def delete(self, grant_id):
        before = len(self.rows)
        self.rows = [r for r in self.rows if r["id"] != grant_id]
        self.deleted.append(grant_id)
        return len(self.rows) < before

    async def purge_expired(self):
        return self.purged


@pytest.fixture
def grant_repo(monkeypatch):
    repo = FakeGrantRepo()
    monkeypatch.setattr(service, "permission_grant_repo", repo)
    return repo


@pytest.fixture
def users_backend(monkeypatch):
    users: dict = {"admin-1": _user(), "u1": _user(Role.USER, "u1")}

    async def get(user_id):
        return users.get(user_id)

    monkeypatch.setattr(service.users_repo, "get", get)
    return users


def test_catalog_derived_from_permission_enum():
    cat = service.catalog()
    assert "users" in cat.resources and "read" in cat.resources["users"]
    assert "permissions" in cat.resources and "manage" in cat.resources["permissions"]
    assert Permission.PERMISSIONS_MANAGE.value in cat.permissions
    assert cat.resources == dict(sorted(cat.resources.items()))


def test_validate_grant_rejects_unknown_page_action_and_condition():
    cat = service.catalog()
    from app.features.permissions.schemas import GrantIn

    with pytest.raises(BadInputError):
        service._validate_grant(GrantIn(resource="nope", action="read"), cat)
    with pytest.raises(BadInputError):
        service._validate_grant(GrantIn(resource="users", action="fly"), cat)
    with pytest.raises(BadInputError):
        service._validate_grant(
            GrantIn(resource="users", action="read", conditions={"wizard": True}), cat
        )
    service._validate_grant(
        GrantIn(resource="users", action="read", conditions={"own_only": True}), cat
    )  # valid


async def test_list_effective_unknown_user(grant_repo, users_backend):
    with pytest.raises(NotFoundError):
        await service.list_effective("ghost")


async def test_effective_combines_baseline_and_grants(grant_repo, users_backend):
    grant_repo.rows = [
        {
            "id": "g1",
            "user_id": "u1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "granted_by": "admin-1",
            "expires_at": None,
            "created_at": datetime(2026, 1, 1),
        },
        {
            "id": "g2",
            "user_id": "u1",
            "resource": "audit",
            "action": "read",
            "effect": "DENY",
            "conditions": None,
            "granted_by": "admin-1",
            "expires_at": None,
            "created_at": datetime(2026, 1, 1),
        },
    ]
    out = await service.list_effective("u1")
    assert out.baseline == []  # USER baseline is empty
    assert Permission.USERS_READ.value in out.effective
    assert Permission.AUDIT_READ.value not in out.effective  # DENY wins
    assert len(out.grants) == 2


async def test_effective_admin_baseline(grant_repo, users_backend):
    grant_repo.rows = []
    out = await service.list_effective("admin-1")
    assert Permission.USERS_READ.value in out.effective
    assert Permission.PERMISSIONS_MANAGE.value in out.effective


async def test_replace_grants_audits_and_invalidates(
    grant_repo, users_backend, audit_sink, monkeypatch
):
    invalidated: list = []

    async def invalidate(user_id):
        invalidated.append(user_id)

    monkeypatch.setattr(service._load_grants, "invalidate", invalidate)
    from app.features.permissions.schemas import GrantIn, GrantsIn

    payload = GrantsIn(
        grants=[
            GrantIn(resource="jobs", action="read_all"),
            GrantIn(
                resource="audit",
                action="read",
                conditions={"own_only": True},
                expires_at=datetime.now(UTC) + timedelta(days=7),
            ),
        ]
    )
    out = await service.replace_grants(_user(), "u1", payload)
    assert "jobs:read_all" in out.effective
    assert "audit:read" not in out.effective  # own_only grants are not route-level effective
    assert grant_repo.replaced == [("u1", 2)]
    assert invalidated == ["u1"]
    assert any(e["action"] == "permission.grants_updated" for e in audit_sink.entries)


async def test_replace_grants_validates_before_write(grant_repo, users_backend, audit_sink):
    from app.features.permissions.schemas import GrantIn, GrantsIn

    with pytest.raises(BadInputError):
        await service.replace_grants(
            _user(), "u1", GrantsIn(grants=[GrantIn(resource="nope", action="read")])
        )
    assert grant_repo.replaced == []  # nothing written on validation failure


async def test_delete_grant_audits_and_invalidates(
    grant_repo, users_backend, audit_sink, monkeypatch
):
    invalidated: list = []

    async def invalidate(user_id):
        invalidated.append(user_id)

    monkeypatch.setattr(service._load_grants, "invalidate", invalidate)
    grant_repo.rows = [
        {
            "id": "g1",
            "user_id": "u1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "granted_by": "admin-1",
            "expires_at": None,
            "created_at": datetime(2026, 1, 1),
        }
    ]
    await service.delete_grant(_user(), "u1", "g1")
    assert grant_repo.deleted == ["g1"] and invalidated == ["u1"]
    assert any(e["action"] == "permission.grants_updated" for e in audit_sink.entries)


async def test_delete_grant_unknown_or_foreign(grant_repo, users_backend):
    grant_repo.rows = [
        {
            "id": "g2",
            "user_id": "admin-1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "granted_by": None,
            "expires_at": None,
            "created_at": datetime(2026, 1, 1),
        }
    ]
    with pytest.raises(NotFoundError):
        await service.delete_grant(_user(), "u1", "missing")
    with pytest.raises(NotFoundError):
        await service.delete_grant(_user(), "u1", "g2")  # belongs to another user


async def test_validate_grant_rejects_past_expiry_and_deny_on_manage():
    cat = service.catalog()
    from app.features.permissions.schemas import GrantIn

    with pytest.raises(BadInputError):
        service._validate_grant(
            GrantIn(resource="users", action="read", expires_at=datetime(2020, 1, 1, tzinfo=UTC)),
            cat,
        )
    naive = GrantIn(resource="users", action="read", expires_at=datetime(2020, 1, 1))
    with pytest.raises(BadInputError):
        service._validate_grant(naive, cat)  # naive datetime treated as UTC and rejected
    with pytest.raises(BadInputError):
        service._validate_grant(
            GrantIn(resource="permissions", action="manage", effect="DENY"), cat
        )


async def test_replace_grants_guards(monkeypatch, grant_repo, users_backend, audit_sink):
    from app.features.permissions.schemas import GrantsIn

    # self-targeting forbidden
    with pytest.raises(ForbiddenError):
        await service.replace_grants(_user(user_id="u1"), "u1", GrantsIn(grants=[]))
    # non-admin actor may not modify a permissions:manage holder
    monkeypatch.setattr(service.authz, "allowed", _allow_all)
    with pytest.raises(ForbiddenError):
        await service.replace_grants(_user(Role.USER, "u2"), "u1", GrantsIn(grants=[]))
    # admin actor may
    out = await service.replace_grants(_user(Role.ADMIN, "admin-1"), "u1", GrantsIn(grants=[]))
    assert out.effective == []

    # delete_grant: same guards
    with pytest.raises(ForbiddenError):
        await service.delete_grant(_user(user_id="u1"), "u1", "g1")
    monkeypatch.setattr(service.authz, "allowed", _allow_all)
    with pytest.raises(ForbiddenError):
        await service.delete_grant(_user(Role.USER, "u2"), "u1", "g1")


async def _allow_all(user, permission):
    from app.core.authz import Decision

    return Decision(True)


async def test_purge_expired(grant_repo):
    grant_repo.purged = 7
    assert await service.purge_expired() == 7


async def test_delete_grant_race_returns_false(monkeypatch, grant_repo, users_backend):
    grant_repo.rows = [
        {
            "id": "g1",
            "user_id": "u1",
            "resource": "users",
            "action": "read",
            "effect": "ALLOW",
            "conditions": None,
            "granted_by": None,
            "expires_at": None,
            "created_at": datetime(2026, 1, 1),
        }
    ]

    async def already_gone(grant_id):
        return False  # a concurrent delete won

    monkeypatch.setattr(grant_repo, "delete", already_gone)
    with pytest.raises(NotFoundError):
        await service.delete_grant(_user(), "u1", "g1")


# --- router handlers (direct) -----------------------------------------------


async def test_router_handlers(monkeypatch):
    from types import SimpleNamespace as NS

    from app.features.permissions import router as perms_router
    from app.features.permissions.schemas import EffectiveOut, GrantsIn

    admin = _user()
    response = NS(headers={}, status_code=None)

    async def list_effective(user_id):
        return EffectiveOut(baseline=[], grants=[], effective=[])

    async def replace_grants(actor, user_id, payload):
        return EffectiveOut(baseline=[], grants=[], effective=["notes:read"])

    async def delete_grant(actor, user_id, grant_id):
        return None

    class FakeIdem:
        def __init__(self):
            self.record = None

        async def create(self, data):
            self.record = NS(id="i1", status_code=None, response=None)
            return self.record

        async def find_first(self, where):
            return self.record

        async def update(self, where, data):
            for k, v in data.items():
                setattr(self.record, k, v)

    monkeypatch.setattr(perms_router.service, "list_effective", list_effective)
    monkeypatch.setattr(perms_router.service, "replace_grants", replace_grants)
    monkeypatch.setattr(perms_router.service, "delete_grant", delete_grant)
    monkeypatch.setattr(
        "app.shared.helpers.idempotency.current_db",
        lambda: NS(idempotencyrecord=FakeIdem()),
    )

    cat = await perms_router.get_catalog()
    assert cat.data.resources

    r = await perms_router.get_effective("u1", response)
    assert r.success and response.headers["etag"].startswith('"')

    payload = GrantsIn(grants=[])
    if_match = response.headers["etag"]
    r = await perms_router.put_grants("u1", payload, NS(headers={}), admin, "idem-1", if_match)
    assert r.success and r.data["effective"] == ["notes:read"]  # idempotent path returns the dict

    with pytest.raises(PreconditionError):
        await perms_router.put_grants("u1", payload, NS(headers={}), admin, "idem-2", None)
    with pytest.raises(StaleError):
        await perms_router.put_grants("u1", payload, NS(headers={}), admin, "idem-3", '"stale"')

    # non-idempotent path (no key): returns the model + sets the ETag header
    resp2 = NS(headers={}, status_code=None)
    r = await perms_router.put_grants("u1", payload, resp2, admin, None, if_match)
    assert r.data.effective == ["notes:read"]
    assert resp2.headers["etag"].startswith('"')

    r = await perms_router.delete_grant("u1", "g1", admin)
    assert r.data == {"id": "g1"}


from app.core.exceptions import PreconditionFailedError as StaleError  # noqa: E402
from app.core.exceptions import PreconditionRequiredError as PreconditionError  # noqa: E402


async def test_router_idempotent_replay_short_circuit(monkeypatch):
    """H1: a repeated Idempotency-Key replays the stored response without re-running the write."""
    from types import SimpleNamespace as NS

    from app.features.permissions import router as perms_router
    from app.features.permissions.schemas import EffectiveOut, GrantsIn

    admin = _user()

    async def list_effective(user_id):
        return EffectiveOut(baseline=[], grants=[], effective=[])

    async def replace_grants(actor, user_id, payload):
        raise AssertionError("must not run on a replay")

    async def fake_run_once(scope, key, payload, fn):
        return 200, {"effective": ["cached"]}, True  # replay

    # the ETag is derived from the current effective set (empty here)
    from app.shared.helpers.http import etag_for

    etag = etag_for("u1", 0, [])

    monkeypatch.setattr(perms_router.service, "list_effective", list_effective)
    monkeypatch.setattr(perms_router.service, "replace_grants", replace_grants)
    monkeypatch.setattr(perms_router, "run_once", fake_run_once)

    r = await perms_router.put_grants(
        "u1", GrantsIn(grants=[]), NS(headers={}), admin, "idem-1", etag
    )
    assert r.data == {"effective": ["cached"]}
    assert r.success


async def test_router_idempotent_replay_sets_header(monkeypatch):
    from types import SimpleNamespace as NS

    from app.features.permissions import router as perms_router
    from app.features.permissions.schemas import EffectiveOut, GrantsIn
    from app.shared.helpers.http import etag_for

    admin = _user()
    response = NS(headers={}, status_code=None)

    async def list_effective(user_id):
        return EffectiveOut(baseline=[], grants=[], effective=[])

    async def fake_run_once(scope, key, payload, fn):
        return 201, {"effective": []}, True  # replay => 201 + Idempotent-Replay header

    monkeypatch.setattr(perms_router.service, "list_effective", list_effective)
    monkeypatch.setattr(perms_router, "run_once", fake_run_once)
    etag = etag_for("u1", 0, [])

    r = await perms_router.put_grants("u1", GrantsIn(grants=[]), response, admin, "idem-1", etag)
    assert response.status_code == 201
    assert response.headers["idempotent-replay"] == "true"
    assert r.success


async def test_router_manage_gate_denies_non_admin(monkeypatch, audit_sink):
    """The dependency gate itself: a grants-less USER is denied permissions:manage."""
    from types import SimpleNamespace as NS

    from app.features.permissions import router as perms_router

    checker = perms_router._manage
    request = NS(scope={"route": NS(path="/api/v1/permissions/catalog")})
    user = _user(Role.USER)

    async def query_raw(sql, *params):
        return []

    monkeypatch.setattr("app.core.authz.current_db", lambda: NS(query_raw=query_raw))
    with pytest.raises(ForbiddenError):
        await checker(user=user, request=request)
