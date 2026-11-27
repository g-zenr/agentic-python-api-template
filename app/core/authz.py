"""Policy Decision Point (PDP): hybrid RBAC + ABAC permission decisions.

Effective access = role baseline ∪ ALLOW grants − DENY grants (a DENY always wins), with
`expires_at` honoured and optional ABAC conditions on grants. Grants are read directly from the
database; backend errors degrade to baseline-only decisions, or deny outright
when `AUTHZ_FAIL_CLOSED` is set (required in production). Call sites stay unchanged:
`require_permission` and the services consult this module instead of the raw role matrix.

`Permission` members decompose to `resource:action` ("users:read" -> page "users", verb "read"),
which is exactly the shape of a grant row: page × action per user.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from app.core.config import settings
from app.core.constants import (
    AuditReason,
    GrantCondition,
    Permission,
    Role,
)
from app.core.permissions import has_permission as role_has_permission
from app.core.uow import current_db

log = logging.getLogger(__name__)

EMPTY_GRANTS: dict[str, list[str]] = {"allow": [], "deny": [], "scoped_own": []}


@dataclass(frozen=True)
class Decision:
    """Outcome of one permission evaluation. `reason` is set only on deny (for the audit)."""

    allowed: bool
    reason: AuditReason | None = None


class Subject(BaseModel):
    """Minimal subject attributes the PDP needs (kept pydantic so rows/models both fit)."""

    id: str
    role: str


async def _load_grants(user_id: str) -> dict[str, list[str]]:
    """Load the user's grant rows as {allow, deny, scoped_own} sets of `resource:action` keys."""
    rows = await current_db().query_raw(
        "SELECT resource, action, effect::text AS effect, conditions, expires_at "
        "FROM permission_grants "
        "WHERE user_id = $1 AND (expires_at IS NULL OR expires_at > now());",
        user_id,
    )
    grants: dict[str, set[str]] = {"allow": set(), "deny": set(), "scoped_own": set()}
    for row in rows:
        key = f"{row['resource']}:{row['action']}"
        if row["effect"] == "DENY":
            grants["deny"].add(key)
            continue
        grants["allow"].add(key)
        conditions = row["conditions"]
        if isinstance(conditions, str):  # jsonb may come back as a string
            try:
                conditions = json.loads(conditions)
            except (ValueError, TypeError):
                conditions = None
        if isinstance(conditions, dict) and conditions.get(GrantCondition.OWN_ONLY):
            grants["scoped_own"].add(key)
    return {k: sorted(v) for k, v in grants.items()}


def _subject(user: Any) -> Subject:
    return Subject(id=user.id, role=str(user.role))


async def _grants_for(user_id: str) -> dict[str, list[str]]:
    """Grants with the fail-open/closed policy applied: errors degrade or deny, never cached."""
    try:
        return cast("dict[str, list[str]]", await _load_grants(user_id))
    except Exception:
        if settings.authz_fail_closed:
            log.warning("authz grants unavailable; denying (fail-closed)", exc_info=True)
            return dict(EMPTY_GRANTS, error=["1"])
        log.warning("authz grants unavailable; degrading to role baseline", exc_info=True)
        return dict(EMPTY_GRANTS)


async def evaluate(
    user: Any, permission: Permission, *, resource_owner_id: str | None = None
) -> Decision:
    """Decide one permission for one subject."""
    key = permission.value
    subject = _subject(user)
    grants = await _grants_for(subject.id)
    if "error" in grants:  # grants backend unavailable and AUTHZ_FAIL_CLOSED is set
        return Decision(False, AuditReason.POLICY_ERROR)
    if key in grants["deny"]:
        return Decision(False, AuditReason.PERMISSION_DENIED)
    if role_has_permission(Role(subject.role), permission):
        return Decision(True)
    if key in grants["allow"]:
        if key not in grants["scoped_own"]:
            return Decision(True)
        if resource_owner_id is not None and resource_owner_id == subject.id:
            return Decision(True)  # own-scope grant matches the resource owner
    return Decision(False, AuditReason.INSUFFICIENT_PERMISSION)


async def allowed(user: Any, *permissions: Permission) -> Decision:
    """ALL permissions must be allowed (matches the previous `all(has_permission(...))`)."""
    for permission in permissions:
        decision = await evaluate(user, permission)
        if not decision.allowed:
            return decision
    return Decision(True)


async def read_scope(user: Any, permission: Permission) -> str | None:
    """For read-scope routes: "all", "own" (own_only grant), or None (denied).

    `own_only` grants never satisfy route-level gates by themselves (no resource context there),
    but they do authorize self-scoped reads: the route narrows the query to the caller. The role
    baseline dominates: an own_only grant never narrows a role that already has the permission.
    """
    grants = await _grants_for(user.id)
    key = permission.value
    if "error" in grants or key in grants["deny"]:
        return None
    if role_has_permission(Role(str(user.role)), permission):
        return "all"
    if key in grants["allow"] and key in grants["scoped_own"]:
        return "own"
    return "all" if key in grants["allow"] else None
