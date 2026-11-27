# Playbook: Protect an endpoint

> When to use, prerequisites, numbered steps, a checklist, and a worked example.

## When to use
Use this for any new route so its protection is explicit and consistent.

## Prerequisites
- Read [../16-security.md](../16-security.md) and [../18-api-conventions.md](../18-api-conventions.md).

## Steps
1. **Auth**: add `CurrentUser` (or `VerifiedUser`) — or leave public for register/login.
2. **Permission**: add `dependencies=[Depends(require_permission(Permission.X))]` when role-gated.
   Grants (ADR-0019) extend/deny per user automatically; for read-scope routes (audit, activity) use
   `authz.read_scope` in the handler so `own_only` grants narrow results to the caller.
3. **Rate limit**: add `dependencies=[Depends(by_ip(RateBucket.Y))]` on sensitive POSTs; add
   account-level limits in the service for login/forgot.
4. **Idempotency**: accept `IdempotencyKey` on creates and wrap with `run_once`.
5. **Concurrency**: versioned resources take `IfMatch` and require `If-Match` on PATCH.
6. **Deprecation**: pass `deprecated=True` when sunsetting.
7. **Verify**: `make lint && make test && make feature-check`.

## Verification checklist
- [ ] Auth dependency set.
- [ ] Permission dependency (if role-gated).
- [ ] Rate limit on sensitive routes.
- [ ] Idempotency/`If-Match` where applicable.
- [ ] Tests updated; `make lint && make test && make feature-check` pass.

## Worked example
`POST /notes` uses `VerifiedUser` + `IdempotencyKey`; `PATCH /notes/{id}` uses `VerifiedUser` +
`IfMatch`.