# 04 — Conventions

> How code is named, typed, documented, and structured — and the anti-patterns to avoid.

## What you will learn
- Naming, typing, and async rules.
- The docstring standard.
- Import ordering.
- Error-handling and response rules.
- Anti-patterns, each with a "do this instead".

## Naming
- Features, files, and functions: `snake_case`. Feature folder names match `^[a-z][a-z0-9_]*$`.
- Classes: `PascalCase`. Constants/enums: `PascalCase` members with `UPPER_CASE` values where
  the value is a wire string.
- Schemas end with `In` / `Out` / `Update` / `Create` (e.g. `NoteCreate`, `UserOut`).
- Repository singletons end with `_repo` (e.g. `notes_repo`).

## Typing
- Type everything. Public functions have fully annotated parameters and return types.
- Use PEP 695 generics where the standard library does (`class BaseRepository[M]`).
- Prefer `X | None` over `Optional[X]` (ruff `UP`).

## Async rules
- Async-first: all I/O (DB, HTTP) is `async`. Never call blocking I/O inside `async def`.
- Services and repositories are `async`. Routers are `async`.
- Use `asyncio.gather` for independent queries (see `BaseRepository.paginate`).

## Docstring standard
- **Every module** starts with a docstring: its purpose and its layer.
  ```python
  """Note service: business rules and ownership enforcement."""
  ```
- **Public functions** use Google-style docstrings when the behavior is not obvious from the name.
- **Comments explain WHY, not WHAT.** Do not restate the code.

## Import ordering
Standard library, then third-party, then first-party (`app.*`), each group alphabetized. Ruff
fixes this with `I` (isort). Example:
```python
from datetime import datetime

from fastapi import APIRouter

from app.core.constants import Tag
```

## Error handling
- Services raise `AppError` subclasses (`NotFoundError`, `ConflictError`, …) with a `Msg` key.
- **Never raise `HTTPException` in features.** The handlers translate `AppError` to the envelope.
- Never leak existence: a missing resource and a forbidden one raise the same error
  (see `notes.service._owned`).

## Response rules
- Routers return `ok(...)` or `page_of(...)`; never construct `ApiResponse` by hand.
- Every route declares `response_model=ApiResponse[...]`, `summary`, and `description`.

## Anti-patterns → do this instead
| Anti-pattern | Do this instead |
|---|---|
| `raise HTTPException(...)` in a feature | `raise NotFoundError(Msg.X)` |
| Building `ApiResponse(...)` inline | `return ok(data, Msg.X)` |
| `"Note not found"` literal in a service | `Msg.NOTE_NOT_FOUND` |
| Business logic in `router.py` | move it to `service.py` |
| Copy-pasting a pagination helper | use `app/shared/helpers/` |
| Editing `main.py` for a new feature | add `app/features/<x>/router.py` |
| Slow work inside a request | add a job handler + return 202 (chapter 13) |
| A mutation without `audit.record` | record an audit event (chapter 14) |
| A cache key without the user id | key by user id; never share user data (chapter 15) |
| A handler that is not idempotent | make it idempotent (delivery is at-least-once) |

## Common mistakes
- Inline strings that should be `Msg` keys.
- Duplicated helpers across features.
- Fat routers.

## See also
- [02 — Architecture](02-architecture.md)
- [05 — Configuration and constants](05-configuration-and-constants.md)
- [12 — Feature lifecycle](12-feature-lifecycle.md)