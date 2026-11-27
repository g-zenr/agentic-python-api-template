# 0019 — ABAC and gradual (assignable) permissions

- **Status:** Accepted
- **Date:** 2026-11-27

## Context
Access control was a static role→permission matrix (`ROLE_PERMISSIONS`): USER has nothing,
ADMIN has everything. There was no way to grant a specific user access to a specific page
(resource) and action without changing their role, and attribute-based rules (ownership,
resource state, environment) lived scattered in services.

## Decision
Hybrid RBAC + ABAC behind the existing seam. `has_permission`/`require_permission` call sites are
unchanged; the decision moves to a Policy Decision Point (`app/core/authz.py`):

1. **Baseline**: the static role matrix (bootstrap; ADMIN keeps everything).
2. **Grants**: rows in `permission_grants` (user_id, resource, action, effect ALLOW|DENY,
   conditions JSONB, granted_by, expires_at). `resource` = page, `action` = verb; every
   `Permission` member decomposes to `resource:action`. A user's **effective** permission set is
   baseline ∪ ALLOWs − DENYs (a DENY always wins), with `expires_at` honoured.
3. **ABAC conditions**: grants may carry a small typed vocabulary (`{"own_only": true}`) evaluated
   by the PDP when a resource owner is known at decision time; `own_only` grants never satisfy
   route-level gates without resource context. Read-scope routes (`audit`, `activity`) auto-scope
   results to the caller when access came from an `own_only` grant.
4. **Fail-closed**: any policy-evaluation error denies (`AUTHZ_FAIL_CLOSED`, enforced in prod).
5. **Admin API** (`permissions` feature): catalog of pages×actions, effective set per user,
   replace-all grants (Idempotency-Key + If-Match), delete grant — all gated by the new
   `permissions:manage` permission and audited.

Effective sets are cached per user id (`CacheNS.PERMISSIONS`, `CacheTTL.SHORT`) and invalidated
after every grant write.

## Consequences
- No grants ⇒ exactly today's behavior (additive, non-breaking).
- Deny-by-default is preserved; evaluation errors deny rather than fail open.
- Deny/allow decisions and grant changes are auditable (`access.denied`, `permission.grants_updated`).
- The conditions vocabulary is deliberately tiny; new attributes require an ADR, not ad-hoc JSON.
- `own_only` scope on `audit`/`activity` delegates visibility without granting admin-wide read.
