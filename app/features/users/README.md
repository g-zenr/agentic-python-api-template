# Users feature

> Authenticated profile access and an admin-only user listing.

## Status
`stable`. Since: 0.1.0. Owner files: this folder + the `User` Prisma model.

## Purpose
Own the `User` model and expose profile read/update for the current user plus an
administrative listing. Authentication itself lives in the `auth` feature; this feature
owns the persisted user record and its repository.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/v1/users/me | CurrentUser | Return the caller's own profile. |
| PATCH | /api/v1/users/me | CurrentUser | Update the caller's name and/or locale. |
| GET | /api/v1/users | AdminUser | Paginated list of all users (admin only). |

## Data model
`User` (`@@map("users")`): `id`, `email` (unique), `password_hash`, `name`, `role`
(`USER`|`ADMIN`), `locale`, `is_active`, `created_at`, `updated_at`, `notes`, `jobs`.

## Business rules
- `UserOut` never exposes `password_hash`.
- `UserUpdate.locale` must be one of `settings.supported_locales`.
- Unknown id → `404` with `Msg.USER_NOT_FOUND`.
- Successful update → `Msg.USER_UPDATED`.
- The listing route requires `Role.ADMIN` (`AdminUser`).
- **Audit events**: `user.update` (resource `user`, before/after `UserOut` snapshots) on every
  successful `PATCH /users/me`.
- **Cache**: `find(user_id)` is cached under `user:<id>` for `CacheTTL.SHORT`. EVERY code path
  that writes a user row MUST call `find.invalidate(user_id)`; today that is `update_me`.
- **Jobs**: none submitted here.

## Dependencies
- `app/features/auth/deps.py` (`CurrentUser`, `AdminUser`).
- `app/core/cache/` (`@cached`), `app/core/audit/` (`record`).
- `app/core/constants.py` (`Role`, `Limits`, `Tag.USERS`, `CacheNS`, `AuditAction`),
  `app/core/messages.py` (`Msg.USER_*`).

## Extending
- Add queries to `UserRepository` (e.g. `find_by_role`) and call them from `service.py`.
- New user-facing fields: update `UserOut` and the Prisma model together; new write paths must
  invalidate `find`.
- New mutations must call `audit.record(...)`.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.1.0 | 2026-11-26 | Added | Initial version: profile read/update and admin listing |
| 0.2.0 | 2026-11-26 | Changed | Cached `find` (user scope) + `user.update` audit event |
| 0.3.0 | 2026-11-26 | Added | Account delete/export (202), transactional mutations, permission-gated list |
