# Auth feature

> Registration, login, and the shared authentication dependencies.

## Status
`stable`. Since: 0.1.0. Owner files: this folder + the `User` Prisma model (via `users`).

## Purpose
Let clients create accounts and obtain a JWT access token, and provide the `CurrentUser` /
`AdminUser` dependencies every protected route depends on.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /api/v1/auth/register | none | Create an account, return 201 + access token. |
| POST | /api/v1/auth/login | none | Exchange email + password for an access token. |

## Data model
Creates `User` rows (see `users` feature). Stores `email` (lowercased), `password_hash`
(argon2), `name`, and the request `locale`.

## Business rules
- Duplicate email → `409 Conflict` with `Msg.USER_EMAIL_TAKEN`.
- Unknown email AND wrong password raise the **same** `401` with
  `Msg.AUTH_INVALID_CREDENTIALS` (no account enumeration) — but the audit trail records the
  distinct reason (`unknown_email` vs `bad_password`).
- Passwords are hashed with argon2 via `pwdlib`; tokens are signed with `HS256`.
- `get_current_user` loads the user via the cached `users_service.find`, rejects missing/inactive
  users with `Msg.AUTH_TOKEN_INVALID`, and binds the user into the request context.
- `require_role(...)` returns 403 (`Msg.FORBIDDEN`) when the role does not match, and records an
  `access.denied` audit event first.
- **Audit events**: `auth.register`, `auth.login`, `auth.login_failed` (with reason),
  `access.denied` (with required roles). Failed-login metadata stores the attempted email (PII).
- **Cache**: reads users through `users.find` (`user:<id>`); no cache of its own.
- **Jobs**: none.

## Dependencies
- `app/features/users/service.py` (`find`) and `repository.py` (`users_repo`) for persistence.
- `app/core/security.py` (hash/verify/token), `app/core/context.py` (request locale, `bind_user`).
- `app/core/audit/` (`record`).
- Exposes `CurrentUser`, `AdminUser` consumed by `users`, `notes`, `jobs`, `audit` routers.

## Extending
- Add a new dependency factory in `deps.py` following `require_role`.
- New auth endpoints go in `router.py` and delegate to `service.py`; new mutations must audit.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.1.0 | 2026-11-26 | Added | Initial version: register, login, CurrentUser/AdminUser deps |
| 0.2.0 | 2026-11-26 | Changed | Audit register/login/denied; cached user lookup; bind user into context |
| 0.3.0 | 2026-11-26 | Changed | Refresh rotation, RBAC permissions, rate limits, email verification/reset, token_version |
