# AGENTS.md: rules for AI coding agents

Read this file fully before changing anything. Deep docs live in `docs/` (start at `docs/README.md`).

## Golden rules
1. Never ask the user questions you can answer from `docs/`. If docs are silent, choose the simplest option and record an ADR in `docs/decisions/`.
2. Copy the pattern of `app/features/notes/` for anything new. It is the reference implementation.
3. Layering: router → service → repository → Prisma. Routers: HTTP only. Services: rules + raise `AppError` subclasses. Repositories: queries only.
4. Never raise `HTTPException` in features. Never build `ApiResponse` by hand; use `ok()` / `page_of()`.
5. No literals in feature code:
   - env value → `app/core/config.py` + `.env.example`
   - static constant/enum → `app/core/constants.py`
   - user-facing text → `Msg` in `app/core/messages.py` + EVERY file in `app/core/locales/`
   - reusable logic → `app/shared/helpers/` or `app/shared/utils/`
6. Before writing a helper, search `app/shared/` and `app/core/`. Duplicate logic is a defect.
7. Never edit `app/main.py` to add a feature, job, cached read or audit event: routers, `tools.py` and `jobs.py` are auto-discovered.
8. Type everything. Async everywhere. Every module needs a docstring. Every route needs `summary` + `description`.
9. The app version lives ONLY in `pyproject.toml`.
10. Slow work (> ~1s, external calls, fan-out) NEVER runs inside a request. Add a job handler (`features/<x>/jobs.py`) and return 202 with the polling headers. Handlers are idempotent.
11. Every state-changing service function (create/update/delete/register/login/cancel/request_*) calls `audit.record(...)`. `make feature-check` fails otherwise. Exemption only with `# audit-exempt: <reason>`.
12. Reads that are hot or expensive use `@cached` with TTLs from `CacheTTL`. Every write path that affects a cached value MUST invalidate it, and the feature README lists them. Never cache user-specific data under a key without the user id.
13. New `JobType`, `CacheNS`, `AuditAction`, `AuditResource`, `AuditReason` members go in `app/core/constants.py` and must be referenced (orphans fail the check).
14. A feature may import another feature's `service`, `repository`, `deps` or `schemas`, never its `router`. `core/` never imports `features/`.
15. Every mutation runs in `transaction()` with `audit.record` and any `enqueue` inside it; cache invalidation goes through `after_commit`.
16. Every route declares its protection explicitly: auth dependency, `require_permission` where needed, a rate limit on sensitive POSTs, cursor pagination on large tables.
17. Updatable resources carry `version`; PATCH requires `If-Match`; create endpoints accept `Idempotency-Key`.
18. Never log or store secrets or raw PII: use `Redaction`; store email hashes, not emails, in audit metadata.
19. New prod-critical settings get a line in the production guard in `config.py`.

## Task workflow (follow for EVERY task)
1. **Classify**: ADD a feature, UPDATE a feature, or REMOVE a feature. (Anything else: UPDATE the closest feature.)
2. **Read**: `docs/features.md` (is there already an owner?) → the feature's `README.md` → the matching playbook below.
3. **Execute** the playbook steps in order. Do not skip steps; each names the file to edit.
4. **Document in the same change**: follow the docs touch-map in `docs/12-feature-lifecycle.md`.
5. **Verify**: `make lint && make test && make feature-check`. Fix everything red before reporting done.
6. **Report**: list files changed, the version bump, and the CHANGELOG entry you wrote.

| Task | Playbook | Command |
|---|---|---|
| ADD feature | `docs/playbooks/add-feature.md` | `make feature name=<x>` |
| UPDATE feature | `docs/playbooks/update-feature.md` | `make feature-check name=<x>` |
| REMOVE feature | `docs/playbooks/remove-feature.md` | `make remove-feature name=<x> reason="..." drop_data=true\|false` |
| New endpoint | `docs/playbooks/add-endpoint.md` | n/a |
| New DB model | `docs/playbooks/add-model-and-migration.md` | `make migrate` |
| New message / language | `docs/playbooks/add-message-and-locale.md` | n/a |
| New env var | `docs/playbooks/add-env-var.md` | n/a |
| New MCP tool | `docs/playbooks/add-mcp-tool.md` | n/a |
| Slow / async work | `docs/playbooks/add-background-job.md` | n/a |
| Cache a read | `docs/playbooks/add-cached-read.md` | n/a |
| New audit event | `docs/playbooks/add-audit-event.md` | n/a |
| Protect an endpoint | `docs/playbooks/protect-an-endpoint.md` | n/a |
| Transactional mutation | `docs/playbooks/add-transactional-mutation.md` | n/a |

## Definition of Done (a task is NOT done until all are true)
- [ ] Playbook steps completed in order
- [ ] Feature README updated (Status, Endpoints, Business rules, Data model, Change history row)
- [ ] `docs/features.md` row added / updated / moved to Removed
- [ ] `docs/CHANGELOG.md` entry (Added / Changed / Fixed / Removed; `BREAKING:` prefix when applicable)
- [ ] Version bumped in `pyproject.toml` (and ONLY there)
- [ ] ADR written when the playbook says REQUIRED
- [ ] `Msg` keys present in every locale; orphaned keys and constants removed
- [ ] Every mutation is audited (`audit.record`)
- [ ] No slow work inside requests (jobs + 202 polling)
- [ ] Cached reads have invalidation on every write path, listed in the README
- [ ] `make typecheck` passes
- [ ] Coverage gate (80%) holds
- [ ] Raw SQL / trigger / transaction changes have an integration test
- [ ] New routes are permissioned and rate-limited where sensitive
- [ ] `make lint && make test && make feature-check` all pass

## Commands
`make install` · `make dev` · `make migrate` · `make test` · `make test-speed` · `make test-slo` · `make lint` · `make fmt` · `make docs-check` · `make feature name=<x>` · `make feature-check [name=<x>]` · `make remove-feature name=<x> reason="..." drop_data=<true|false>` · `make worker` · `make typecheck` · `make test-cov` · `make test-integration` · `make security` · `make create-admin email=<x>` · `make mcp-key name=<x>` · `make loadtest`

## Where things live
See `docs/03-project-structure.md`. Quick map: `app/core/` framework · `app/shared/` reusable helpers/utils · `app/features/<x>/` business features · `docs/features.md` feature registry · `prisma/schema.prisma` data model · `scripts/` lifecycle tooling · `tests/` tests.