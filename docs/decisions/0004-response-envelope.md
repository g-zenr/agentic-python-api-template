# 0004 — Response envelope

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Inconsistent response shapes (bare objects, ad-hoc error bodies) make clients and agents guess.
We want one predictable shape for success and error, in camelCase.

## Decision
Every endpoint returns `ApiResponse[T]` (`success`, `message`, `code`, `data`, `meta`), serialized
camelCase. Success uses `ok()` / `page_of()`; errors are produced by the `AppError` handlers in
`core/exceptions.py`. Features never build the envelope by hand and never raise `HTTPException`.

## Consequences
- Clients parse one shape; errors carry a stable `code` and a localized `message`.
- Routers stay declarative; services raise typed errors with `Msg` keys.
- Pagination metadata is uniform via `meta`.