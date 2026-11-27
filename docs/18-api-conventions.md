# 18 — API conventions

> The envelope, error codes, versioning/deprecation, pagination, idempotency, and concurrency.

## What you will learn
- The response envelope and error-code table.
- Deprecation policy (FastAPI `deprecated=True`).
- Offset vs cursor pagination, sort/filter.
- Idempotency and optimistic concurrency (`If-Match`).
- Rate-limit and polling headers.

## Envelope and errors
Every response is `ApiResponse` (camelCase). Errors carry a stable `code`:
`INTERNAL_ERROR, VALIDATION_ERROR, NOT_FOUND, UNAUTHORIZED, FORBIDDEN, CONFLICT, RATE_LIMITED,
PAYLOAD_TOO_LARGE, SERVICE_UNAVAILABLE, PRECONDITION_FAILED, PRECONDITION_REQUIRED`.

## Versioning & deprecation
The API is under `/api/v1`. To deprecate, set `deprecated=True`. Keep for at least one minor
version before removal.

## Pagination
- **Offset** (`page`/`size`) for small sets.
- **Cursor** (`cursor`/`size`, opaque base64url) for large append-only tables (audit/activity) — no
  `COUNT(*)`. `nextCursor` is null at the end.

## Sort & filter
`?sort=-created_at,title` (allow-listed, max 3 fields) and `?q=` (title search) on notes; both are
part of the cache key.

## Idempotency & concurrency
- Create endpoints accept `Idempotency-Key`; a replay returns the stored response with
  `Idempotent-Replay: true`; a reused key with a different body → 409.
- Updatable resources carry `version`; `PATCH` requires `If-Match` (missing → 428, stale → 412);
  responses set `ETag`.

## Rate-limit & polling headers
`429` includes `Retry-After`. Async creation returns `202` + `Location` + `Retry-After`; poll
`GET /jobs/{id}` with `If-None-Match` (304 when unchanged).

## Common mistakes
- Hand-building the envelope.
- Cursor pagination on small sets (use offset).
- Forgetting `If-Match` on a versioned PATCH.

## See also
- [13 — Background jobs](13-background-jobs.md)
- [04 — Conventions](04-conventions.md)
- [19 — Transactions and consistency](19-transactions-and-consistency.md)