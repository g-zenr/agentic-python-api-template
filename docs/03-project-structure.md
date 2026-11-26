# 03 — Project structure

> An annotated map of the repository and how auto-discovery works.

## What you will learn
- What every top-level folder is for.
- The purpose of each file in a feature folder.
- How routers, MCP tools and job handlers are discovered automatically.

## Annotated tree
```
.
├── AGENTS.md                 # rulebook for AI coding agents (start here)
├── CLAUDE.md                 # one line: "See AGENTS.md."
├── README.md                 # quickstart + endpoint table
├── Makefile                  # install/dev/worker/migrate/test/lint/feature tasks
├── Dockerfile                # production image (non-root, uv)
├── docker-compose.yml        # postgres + redis + api + worker
├── pyproject.toml            # single source of truth for the app version
├── .env.example              # every environment variable, documented
├── docs/                     # the documentation book (see docs/README.md)
├── prisma/schema.prisma      # data model (+ migrations/)
├── scripts/                  # feature lifecycle tooling
├── app/
│   ├── main.py               # application factory (infrastructure wiring; never edit per feature)
│   ├── worker.py             # standalone worker entrypoint (`python -m app.worker`)
│   ├── core/                 # framework: config, constants, i18n, security, db, mcp,
│   │                         #   cache/, jobs/, audit/, activity/
│   ├── shared/               # reusable helpers + utils
│   └── features/             # business features (health, auth, users, notes, jobs, audit, maintenance)
└── tests/                    # DB-free test suite + fakes + docs/lifecycle guards
```

## Top-level folders
- **`app/core/`** — the framework. Configuration, static constants, the `Msg` catalog and
  locales, request context, logging, middleware, security, the Prisma client, feature discovery,
  the optional MCP server, and the infrastructure packages `cache/`, `jobs/`, `audit/`,
  `activity/`.
- **`app/shared/`** — reusable, feature-agnostic code: the `ApiResponse` envelope, pagination,
  `ReadRepository`/`BaseRepository`, HTTP/etag helpers, diff/redaction, and small utilities.
- **`app/features/<x>/`** — one folder per business feature. Self-contained and auto-discovered.
  The features are `health`, `auth`, `users`, `notes`, `jobs`, `audit`, `maintenance`.
- **`docs/`** — the book, the feature registry, playbooks, ADRs, glossary, changelog.
- **`prisma/`** — the schema and generated migrations.
- **`scripts/`** — `new_feature.py`, `remove_feature.py`, `check_feature.py`, and shared
  `_features.py` helpers.
- **`tests/`** — the DB-free suite plus `fakes.py` and the docs/lifecycle guards.

## Anatomy of a feature folder
| File | Purpose |
|---|---|
| `README.md` | Status, Purpose, Endpoints, Data model, Business rules, Dependencies, Extending, Change history. |
| `router.py` | Exposes `router = APIRouter(...)`. HTTP only. (Optional: `maintenance` has none.) |
| `service.py` | Business rules; raises `AppError` subclasses; calls `audit.record` on mutations. |
| `repository.py` | Data access; subclasses `BaseRepository`; exports a singleton. |
| `schemas.py` | Request/response models extending `ApiModel`. |
| `deps.py` | (optional) auth/role dependencies. |
| `tools.py` | (optional) MCP tools declared with `@mcp_tool`. |
| `jobs.py` | (optional) background job handlers declared with `@job_handler`. |
| `__init__.py` | Package docstring. |

## How auto-discovery works
`app/core/discovery.py` walks `app/features/` and imports `app.features.<x>.router` (and
`.tools`, and `.jobs`) for every non-underscore folder. `create_app()` includes each discovered
router under `settings.api_prefix`, attaches every registered MCP tool, and imports every
`@job_handler` so `enqueue` can validate the type. A feature with no `router.py`/`tools.py`/
`jobs.py` is simply skipped. **This is why `main.py` never changes when you add a feature, job,
cached read or audit event.**

## Common mistakes
- Adding a feature but forgetting its folder name is a real package (missing `__init__.py`).
- Putting shared code in a feature instead of `app/shared/`.
- Putting infrastructure (queue/audit/cache) inside a feature instead of `app/core/`.

## See also
- [02 — Architecture](02-architecture.md)
- [04 — Conventions](04-conventions.md)
- [Feature registry](features.md)