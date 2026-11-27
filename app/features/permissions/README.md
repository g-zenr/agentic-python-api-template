# Permissions feature

> Gradual (assignable) permissions: per-user page × action grants with ABAC conditions, plus the
> catalog that drives admin UIs. The decision engine itself lives in `app/core/authz.py` (ADR-0019).

## Status
`experimental`. Since: 0.5.0. Owner files: this folder + the `PermissionGrant` Prisma model.

## Purpose
Let an administrator assign exactly which pages (resources) and actions a user may perform —
without changing roles — and expose the assignable catalog. Static roles stay the baseline;
grants extend or deny on top (DENY always wins). Attribute conditions (`own_only`) attach ABAC
semantics to a grant.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/permissions/catalog | permissions:manage | Assignable page × action matrix (derived from the Permission enum). |
| GET | /api/v1/permissions/users/{user_id} | permissions:manage | Effective set: baseline + grants (+ ETag). |
| PUT | /api/v1/permissions/users/{user_id} | permissions:manage | Replace the user's grant set (Idempotency-Key + If-Match). |
| DELETE | /api/v1/permissions/users/{user_id}/{grant_id} | permissions:manage | Revoke one grant. |

## Data model
`PermissionGrant` (`@@map("permission_grants")`): `id`, `user_id` (FK → users, cascade),
`resource` (page), `action` (verb), `effect` (`ALLOW`/`DENY`), `conditions` (JSONB, ADR-0019
vocabulary: `{"own_only": true}`), `granted_by` (no FK, like audit `actor_id`), `expires_at`
(nullable; expired grants are invisible to the PDP and purged by maintenance),
`created_at`, `updated_at`. Unique `(user_id, resource, action)`.

## Business rules
- **Deny-by-default**: no baseline and no ALLOW grant ⇒ 403.
- **DENY wins** over baseline and ALLOW for the same page×action.
- **Evaluation errors deny** when `AUTHZ_FAIL_CLOSED` (required in prod); otherwise they degrade
  to baseline-only (cache-facade philosophy).
- `own_only` grants never satisfy route-level gates alone; they authorize self-scoped reads
  (`/audit`, `/audit/activity` narrow to the caller) and owner-matched resource checks (`jobs`).
- Catalog is derived from `Permission` (`resource:action`) — new permissions appear automatically.
- Grant payloads are validated against the catalog; unknown condition keys are rejected (ADR-0019
  vocabulary only).
- **Audit events**: `permission.grants_updated` (actor = granting admin, resource = target user)
  on replace and revoke.
- **Cache**: effective grants cached per user (`permissions:<user_id>`, `CacheTTL.SHORT`);
  invalidated after every grant write (and on role change in `create_admin`).

## Dependencies
- `app/core/authz.py` (the PDP this feature administers; grants loader is cached here).
- `app/features/users/repository.py` (`users_repo`) for target lookup.
- `app/features/auth/deps.py` (`require_permission`).
- `app/core/audit/` (`record`), `app/core/uow/` (`transaction`, `after_commit`).

## Extending
- New assignable capability: add a `Permission` member (`page:action`) — catalog follows.
- New ABAC condition: add to `GrantCondition` + the PDP + an ADR (never ad-hoc JSON keys).
- Bulk assignment for roles: add a `role` subject column (needs migration + ADR).

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.5.0 | 2026-11-27 | Added | Catalog, effective set, grant replace/revoke API; PermissionGrant model; own_only scope on audit/activity; jobs owner-aware evaluation |
| 0.5.0 | 2026-11-27 | Fixed | Idempotency-Key honored on PUT; self-target/manager-lockout/DENY-manage guards; past expiry rejected; baseline dominates own_only |
