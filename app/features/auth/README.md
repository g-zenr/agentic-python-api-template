# Auth feature

> Registration, login, and the shared authentication dependencies.

## Status
`stable`. Since: 0.1.0. Owner files: this folder + the `User` Prisma model (via `users`).

## Purpose
Let clients create accounts and obtain a JWT access token, and provide the `CurrentUser` /
`VerifiedUser` dependencies and `require_permission(...)` RBAC check every protected route uses.

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
- `get_current_user` loads the user **uncached** via `users_repo.get`, rejects missing/inactive
  users with `Msg.AUTH_TOKEN_INVALID`, and binds the user into the request context.
- `require_permission(...)` returns 403 (`Msg.FORBIDDEN`) when the role lacks the permission, and
  records an `access.denied` audit event first (`reason=insufficient_permission`, `required`).
- **Audit events**: `auth.register`, `auth.login`, `auth.login_failed` (with reason),
  `access.denied` (with required roles). Failed-login metadata stores the attempted email (PII).
- **Cache**: `get_current_user` reads the user **uncached** (`users_repo.get`); `users.find`
  (`user:<id>`, `CacheTTL.SHORT`=60s) still serves other reads. **H4 eliminated**: `is_active`,
  `role`, `email_verified_at`, `token_version` are always read fresh on the auth path, so a
  deactivation/role/password change takes effect immediately for in-flight requests.
  unacceptable.
- **Jobs**: none.

## Dependencies
- `app/features/users/service.py` (`find`) and `repository.py` (`users_repo`) for persistence.
- `app/core/security.py` (hash/verify/token), `app/core/context.py` (request locale, `bind_user`).
- `app/core/audit/` (`record`).
- Exposes `CurrentUser`, `VerifiedUser`, `require_permission` consumed by `users`, `notes`,
  `jobs`, `audit` routers.

## Extending
- Add a new dependency factory in `deps.py` following `require_permission`.
- New auth endpoints go in `router.py` and delegate to `service.py`; new mutations must audit.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.1.0 | 2026-11-26 | Added | Initial version: register, login, CurrentUser/AdminUser deps |
| 0.2.0 | 2026-11-26 | Changed | Audit register/login/denied; cached user lookup; bind user into context |
| 0.3.0 | 2026-11-26 | Changed | Refresh rotation, RBAC permissions, rate limits, email verification/reset, token_version |
| 0.3.1 | 2026-11-26 | Fixed | Refresh rotation: replaced_by links old row to new token; reuse-detection family revocation committed in its own tx; _issue_pair type; tests |
| 0.4.0 | 2026-11-26 | Changed | Sensitive POSTs rate-limited; FORGOT_ACCOUNT + RESEND_USER wired; require_permission docs; cached-user staleness documented |
| 0.4.1 | 2026-11-27 | Changed | H4 eliminated: get_current_user reads the user uncached (no 60s stale-authorization window) |
