"""Permissions service: the assignable catalog, effective sets, and grant administration.

The catalog is DERIVED from the `Permission` enum (`resource:action` decomposition) — adding a
permission adds it to the catalog automatically. All mutations run in a transaction, audit, and
invalidate the user's cached effective set afterwards.
"""

from datetime import UTC, datetime
from typing import Any

from prisma.models import User

from app.core import audit, authz
from app.core.constants import (
    AuditAction,
    AuditReason,
    AuditResource,
    GrantCondition,
    GrantEffect,
    Permission,
    Role,
)
from app.core.exceptions import (
    BadInputError,
    ForbiddenError,
    NotFoundError,
    PreconditionFailedError,
)
from app.core.messages import Msg
from app.core.permissions import ROLE_PERMISSIONS
from app.core.uow import transaction
from app.features.permissions.repository import permission_grant_repo
from app.features.permissions.schemas import (
    CatalogOut,
    EffectiveOut,
    GrantIn,
    GrantOut,
    GrantsIn,
)
from app.features.users.repository import users_repo
from app.shared.helpers.http import etag_for


def catalog() -> CatalogOut:
    """Every assignable page (resource) × action, derived from the Permission enum."""
    resources: dict[str, set[str]] = {}
    for permission in Permission:
        resource, action = permission.value.split(":", 1)
        resources.setdefault(resource, set()).add(action)
    return CatalogOut(
        resources={k: set(v) for k, v in resources.items()},
        permissions=[p.value for p in Permission],
    )


def _validate_grant(grant: GrantIn, cat: CatalogOut) -> None:
    actions = cat.resources.get(grant.resource)
    if actions is None:
        raise BadInputError(Msg.VALIDATION_ERROR, details={"resource": grant.resource})
    if grant.action not in actions:
        raise BadInputError(Msg.VALIDATION_ERROR, details={"action": grant.action})
    if grant.conditions:
        unknown = set(grant.conditions) - {GrantCondition.OWN_ONLY}
        if unknown:
            raise BadInputError(Msg.VALIDATION_ERROR, details={"conditions": sorted(unknown)})
    if grant.expires_at is not None:
        expiry = grant.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise BadInputError(
                Msg.VALIDATION_ERROR, details={"expires_at": "must be in the future"}
            )
    if (
        grant.resource == Permission.PERMISSIONS_MANAGE.value.split(":")[0]
        and grant.action == Permission.PERMISSIONS_MANAGE.value.split(":")[1]
        and grant.effect == GrantEffect.DENY
    ):
        # H2: a DENY on permissions:manage would let one manager lock out another (deny beats
        # the role baseline). Managing this capability stays role-admin-only.
        raise BadInputError(
            Msg.VALIDATION_ERROR, details={"effect": "DENY on permissions:manage"}
        )


def _is_role_admin(user: User) -> bool:
    return Role(str(user.role)) == Role.ADMIN


async def _assert_can_manage_target(actor: User, target_user_id: str) -> User:
    """H2 guards: no self-targeting; modifying a permissions:manage holder requires an
    ADMIN role baseline (a grants-only manager can never lock out another manager/admin)."""
    if actor.id == target_user_id:
        raise ForbiddenError(Msg.FORBIDDEN, details={"target": "self"})
    target = await _target_user(target_user_id)
    if not _is_role_admin(actor):
        holder = await authz.allowed(target, Permission.PERMISSIONS_MANAGE)
        if holder.allowed or holder.reason == AuditReason.POLICY_ERROR:
            raise ForbiddenError(Msg.FORBIDDEN, details={"target": "permissions manager"})
    return target


def _grant_out(row: dict[str, Any]) -> GrantOut:
    return GrantOut.model_validate(row)


def _baseline(role: str) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS.get(Role(role), frozenset()))


async def _target_user(user_id: str) -> User:
    target = await users_repo.get(user_id)
    if target is None:
        raise NotFoundError(Msg.USER_NOT_FOUND)
    return target


async def effective(target: User) -> EffectiveOut:
    """Baseline plus grants for one user (denies shown as DENY grants; own_only in conditions)."""
    rows = await permission_grant_repo.list_for_user(target.id)
    baseline = _baseline(str(target.role))
    denied = {f"{r['resource']}:{r['action']}" for r in rows if r["effect"] == "DENY"}
    allowed = {
        f"{r['resource']}:{r['action']}"
        for r in rows
        if r["effect"] == "ALLOW" and GrantCondition.OWN_ONLY not in (r["conditions"] or {})
    }
    return EffectiveOut(
        baseline=baseline,
        grants=[_grant_out(r) for r in rows],
        effective=sorted((set(baseline) | allowed) - denied),
    )


async def list_effective(target_user_id: str) -> EffectiveOut:
    target = await _target_user(target_user_id)
    return await effective(target)


def grants_etag(user_id: str, state: EffectiveOut) -> str:
    return etag_for(
        user_id, len(state.grants), sorted(g.model_dump_json() for g in state.grants)
    )


async def replace_grants(
    actor: User, target_user_id: str, payload: GrantsIn, *, if_match: str | None = None
) -> EffectiveOut:
    """Replace the target user's grant set. Audited; cached effective set invalidated."""
    cat = catalog()
    for grant in payload.grants:
        _validate_grant(grant, cat)

    async with transaction():
        await permission_grant_repo.lock_user(target_user_id)
        target = await _assert_can_manage_target(actor, target_user_id)
        if if_match is not None and if_match.strip() != grants_etag(
            target.id, await effective(target)
        ):
            raise PreconditionFailedError(Msg.PRECONDITION_FAILED)
        before = await permission_grant_repo.list_for_user(target.id)
        rows = await permission_grant_repo.replace_for_user(
            target.id,
            [g.model_dump(mode="json") for g in payload.grants],
            granted_by=actor.id,
        )
        await audit.record(
            AuditAction.PERMISSION_GRANTS_UPDATED,
            AuditResource.PERMISSION,
            target.id,
            actor_id=actor.id,
            before={"grants": len(before)},
            after={"grants": len(rows)},
        )
        return await effective(target)


async def delete_grant(actor: User, target_user_id: str, grant_id: str) -> None:
    async with transaction():
        await permission_grant_repo.lock_user(target_user_id)
        target = await _assert_can_manage_target(actor, target_user_id)
        row = await permission_grant_repo.get(grant_id)
        if row is None or row["user_id"] != target.id:
            raise NotFoundError(Msg.PERMISSION_NOT_FOUND)
        if not await permission_grant_repo.delete(grant_id):
            raise NotFoundError(Msg.PERMISSION_NOT_FOUND)
        await audit.record(
            AuditAction.PERMISSION_GRANTS_UPDATED,
            AuditResource.PERMISSION,
            target.id,
            actor_id=actor.id,
            metadata={"removed": f"{row['resource']}:{row['action']}"},
        )


async def purge_expired() -> int:
    return await permission_grant_repo.purge_expired()
