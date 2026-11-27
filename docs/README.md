# Documentation

Welcome to the Agentic API documentation book: architecture, conventions, background jobs, logging,
caching, security, observability, and the enforced feature lifecycle.

**Reading order.** Humans: read chapters `01` → `21` in order, then the glossary. Coding agents: read
[`../AGENTS.md`](../AGENTS.md) first, then [features.md](features.md), then the playbook for your
task. If something is ambiguous, choose the simplest option and record an ADR.

## Table of contents

### Chapters
- [01 — Overview](01-overview.md)
- [02 — Architecture](02-architecture.md)
- [03 — Project structure](03-project-structure.md)
- [04 — Conventions](04-conventions.md)
- [05 — Configuration and constants](05-configuration-and-constants.md)
- [06 — Localization](06-localization.md)
- [07 — Database](07-database.md)
- [08 — Authentication](08-authentication.md)
- [09 — MCP](09-mcp.md)
- [10 — Testing](10-testing.md)
- [11 — Deployment](11-deployment.md)
- [12 — Feature lifecycle](12-feature-lifecycle.md)
- [13 — Background jobs](13-background-jobs.md)
- [14 — Audit and activity logging](14-audit-and-activity-logging.md)
- [15 — Caching](15-caching.md)
- [16 — Security](16-security.md)
- [17 — Observability](17-observability.md)
- [18 — API conventions](18-api-conventions.md)
- [19 — Transactions and consistency](19-transactions-and-consistency.md)
- [20 — Account lifecycle and privacy](20-account-lifecycle-and-privacy.md)
- [21 — Database operations](21-database-operations.md)

### Reference
- [Feature registry](features.md) — the single index of every feature.
- [Glossary](glossary.md) — every project term defined.
- [Changelog](CHANGELOG.md) — Keep-a-Changelog history.

### Playbooks
- [Add a feature](playbooks/add-feature.md)
- [Update a feature](playbooks/update-feature.md)
- [Remove a feature](playbooks/remove-feature.md)
- [Add an endpoint](playbooks/add-endpoint.md)
- [Add a model and migration](playbooks/add-model-and-migration.md)
- [Add a message and locale](playbooks/add-message-and-locale.md)
- [Add an env var](playbooks/add-env-var.md)
- [Add an MCP tool](playbooks/add-mcp-tool.md)
- [Add a background job](playbooks/add-background-job.md)
- [Cache a read](playbooks/add-cached-read.md)
- [Add an audit event](playbooks/add-audit-event.md)
- [Add a transactional mutation](playbooks/add-transactional-mutation.md)
- [Protect an endpoint](playbooks/protect-an-endpoint.md)

### Runbooks
- [Incident response](runbooks/incident-response.md)
- [Backup, restore and PITR](runbooks/backup-restore-pitr.md)
- [Stuck jobs](runbooks/stuck-jobs.md)
- [Deployment and rollback](runbooks/deployment-rollback.md)
- [SLOs and alerts](runbooks/slo-and-alerts.md)

### Decisions (ADRs)
- [0000 — Template](decisions/0000-template.md)
- [0001 — Feature-based layout](decisions/0001-feature-based-layout.md)
- [0002 — Centralized constants and i18n](decisions/0002-centralized-constants-and-i18n.md)
- [0003 — Prisma Client Python](decisions/0003-prisma-client-python.md)
- [0004 — Response envelope](decisions/0004-response-envelope.md)
- [0005 — PostgreSQL-backed job queue](decisions/0005-postgres-backed-job-queue.md)
- [0006 — Audit and activity split](decisions/0006-audit-and-activity-split.md)
- [0007 — Cache design](decisions/0007-cache-design.md)
- [0008 — Infrastructure repositories and import rules](decisions/0008-infrastructure-repositories-and-import-rules.md)
- [0009 — Unit of work and same-transaction audit](decisions/0009-unit-of-work-and-same-transaction-audit.md)
- [0010 — Token model](decisions/0010-token-model.md)
- [0011 — Rate limiting](decisions/0011-rate-limiting.md)
- [0012 — RBAC and scoped MCP clients](decisions/0012-rbac-and-mcp-clients.md)
- [0013 — Optimistic concurrency and idempotency](decisions/0013-optimistic-concurrency-and-idempotency.md)
- [0014 — Observability stack](decisions/0014-observability-stack.md)
- [0015 — Prisma Client Python status](decisions/0015-prisma-client-python-status.md)
- [0016 — Static typing and CI gates](decisions/0016-static-typing-and-ci-gates.md)
- [0017 — PII retention and audit scrubbing](decisions/0017-pii-retention-and-audit-scrubbing.md)
- [0018 — Installed-version adaptations](decisions/0018-installed-version-adaptations.md)
- [0019 — ABAC and gradual permissions](decisions/0019-abac-and-gradual-permissions.md)