# Notes feature

> GOLDEN REFERENCE FEATURE. The cleanest, most complete example agents copy for new features.

## Status
`stable`. Since: 0.1.0. Owner files: this folder + the `Note` Prisma model.

## Purpose
Demonstrate the full feature pattern end to end: a fully authenticated, ownership-scoped CRUD
over a per-user resource, now including audit, caching, and a background export job. When in
doubt about how to structure a new feature, copy this folder.

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /api/v1/notes | CurrentUser | Create a note owned by the caller (201). |
| GET | /api/v1/notes | CurrentUser | Paginated list of the caller's notes, newest first. |
| POST | /api/v1/notes/export | CurrentUser | Export all my notes asynchronously (202 + Location). |
| GET | /api/v1/notes/{note_id} | CurrentUser | Fetch one of the caller's notes. |
| PATCH | /api/v1/notes/{note_id} | CurrentUser | Partially update one of the caller's notes. |
| DELETE | /api/v1/notes/{note_id} | CurrentUser | Delete one of the caller's notes. |

## Data model
`Note` (`@@map("notes")`): `id`, `user_id` (FK → `User`, `onDelete: Cascade`), `title`,
`body` (default `""`), `created_at`, `updated_at`. Indexed on `(user_id, created_at)`.

## Business rules
- Every route requires `CurrentUser`.
- **Ownership**: all id-scoped operations go through `_owned(user, note_id)`. A missing note
  and a note owned by someone else raise the SAME `404` (`Msg.NOTE_NOT_FOUND`) — existence is
  never leaked across users.
- `title` ≤ `Limits.TITLE_MAX`; `body` ≤ `Limits.BODY_MAX` (default `""`).
- Create → `Msg.NOTE_CREATED`; update → `Msg.NOTE_UPDATED`; delete → `Msg.DELETED`.
- **Audit events**: `note.create`, `note.update`, `note.delete` (with before/after `NoteOut`
  diffs), and `note.export_request` (resource `job`).
- **Cache**: `list_notes` is cached under `notes:<user_id>:v<N>:<page>:<size>`. Create, update
  and delete invalidate the whole `notes:<user_id>` scope (`invalidate_scope`).
- **Jobs**: `notes.export` (page through the user's notes, build markdown, report progress). The
  same `Idempotency-Key` returns the same job. Large results are capped by `RESULT_MAX_BYTES`.

## Dependencies
- `app/features/auth/deps.py` (`CurrentUser`), `app/features/jobs/` (`submit`, `JobOut`).
- `app/core/cache/` (`@cached`), `app/core/audit/` (`record`), `app/core/jobs/` (`job_handler`).
- `app/shared/helpers/http.py` (poll headers), `repository.py` (`BaseRepository`).

## Extending
- This is the template. For a new resource, replicate: `schemas.py` → `repository.py` →
  `service.py` (with an `_owned`-style guard, `audit.record` on mutations, `@cached` on hot reads)
  → `router.py` → optional `jobs.py`.
- Keep the router free of logic; push rules into `service.py`.

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| 0.1.0 | 2026-11-26 | Added | Initial version: full ownership-scoped CRUD (golden reference) |
| 0.2.0 | 2026-11-26 | Added | Audit on mutations, cached scoped list, async `notes.export` job + `POST /notes/export` |
| 0.3.0 | 2026-11-26 | Added | If-Match optimistic concurrency, Idempotency-Key, sort/q, ETag, VerifiedUser |
