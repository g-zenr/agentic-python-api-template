# 05 — Configuration and constants

> Where every literal goes: environment, constants, messages, or shared logic.

## What you will learn
- The four homes for a value and how to choose.
- How settings are loaded and accessed.
- Why the app version lives only in `pyproject.toml`.

## The decision table
| Kind of value | Home | Example |
|---|---|---|
| Deployment / secret / toggle (from env) | `app/core/config.py` + `.env.example` | `database_url`, `jwt_secret`, `mcp_enabled` |
| Static, non-localized literal or enum | `app/core/constants.py` | `Pagination.MAX_SIZE`, `Role.ADMIN`, `Tag.NOTES` |
| Text shown to a user | `Msg` in `app/core/messages.py` + every `locales/*.json` | `Msg.NOTE_NOT_FOUND` |
| Reusable logic | `app/shared/helpers/` or `app/shared/utils/` | `ok()`, `BaseRepository`, `utcnow()` |
| Job type | `JobType` in `app/core/constants.py` | `JobType.NOTES_EXPORT` |
| Cache namespace | `CacheNS` in `app/core/constants.py` | `CacheNS.USER` |
| Audit action/resource/reason | `AuditAction`/`AuditResource`/`AuditReason` | `AuditAction.NOTE_CREATE` |

## Settings (`config.py`)
`Settings` is a `pydantic-settings` `BaseSettings`. It is the **only** module that reads
environment variables. Access it via the cached `get_settings()` / the module-level `settings`.

```python
from app.core.config import settings

settings.api_prefix  # "/api/v1"
settings.jwt_secret.get_secret_value()
```

Add a new env var by adding a field to `Settings` **and** a line to `.env.example` (see the
`add-env-var` playbook). Never read `os.environ` anywhere else.

## Constants (`constants.py`)
Static, non-environment, non-localized literals live here as classes/enums: `Header`,
`Pagination`, `Role`, `ErrorCode`, `Limits`, `Tag`. If a value is ever shown to a user, it is a
message, not a constant.

## Messages (`messages.py` + locales)
User-facing text is a `Msg` member whose value is a dotted key, translated in every locale JSON.
See [06 — Localization](06-localization.md).

## The version
The app version is written **only** in `pyproject.toml`. `Settings.app_version` reads it from
installed metadata, falling back to parsing `pyproject.toml`. Never hardcode a version elsewhere.

## Common mistakes
- Reading `os.getenv` outside `config.py`.
- Putting a user-facing string in `constants.py`.
- Hardcoding the version in a second place.

## See also
- [06 — Localization](06-localization.md)
- [04 — Conventions](04-conventions.md)
- [Playbook: add an env var](playbooks/add-env-var.md)