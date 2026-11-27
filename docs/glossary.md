# Glossary

> Every project term, defined once.

| Term | Meaning |
|---|---|
| **Feature** | A self-contained folder under `app/features/<x>/` owning one business concept. |
| **Golden feature** | The reference implementation agents copy. Here it is `notes`. |
| **Registry** | `docs/features.md`, the single index of every feature (Active and Removed tables). |
| **Envelope** | The uniform `ApiResponse` shape returned by every endpoint, success or error. |
| **Msg** | The enum of user-facing message keys; text lives in `core/locales/*.json`. |
| **Locale** | A language catalog (e.g. `en.json`, `fil.json`) mapping `Msg` keys to text. |
| **Service** | The layer holding business rules; raises `AppError` subclasses; audits mutations. |
| **Repository** | The data-access layer; subclasses `BaseRepository` (or `ReadRepository`). |
| **Router** | The HTTP layer; declares routes and delegates to the service. |
| **Touch-map** | The table in chapter 12 listing which docs to edit for each kind of change. |
| **ADR** | Architecture Decision Record, under `docs/decisions/`. |
| **MCP** | Model Context Protocol; the optional server exposing feature `tools.py` functions. |
| **Deprecation** | Marking a feature/route obsolete (`deprecated=True`) before removal. |
| **Lifecycle** | The enforced ADD / UPDATE / REMOVE workflow for features. |
| **Auto-discovery** | Importing every feature's `router`/`tools`/`jobs` so `main.py` never changes. |
| **ContextVar** | Per-request state (request id, locale) set by middleware and read anywhere. |
| **Prisma** | The async ORM / query engine (Prisma Client Python) over PostgreSQL. |
| **Job** | A unit of slow work queued in the `jobs` table and run by a worker. |
| **Handler** | An async function registered with `@job_handler` that executes a job type. |
| **Worker** | The process (`python -m app.worker`) that claims and runs jobs. |
| **Polling** | The client pattern of repeatedly calling `GET /jobs/{id}` until terminal. |
| **Idempotency key** | A client-supplied key that makes a repeated `POST` return the same job. |
| **At-least-once** | Delivery guarantee meaning a job may run more than once: handlers must be idempotent. |
| **Audit entry** | A durable "who changed what" record in `audit_logs` (append-only). |
| **Activity entry** | A high-volume per-request record in `activity_logs` (best-effort). |
| **Actor** | Who performed an action: a user, the system, or anonymous. |
| **Request context** | The mutable `RequestContext` carrying request/job identity through a call. |
| **Redaction** | Masking secret fields (`Redaction.FIELDS`) in audit metadata/diffs. |
| **Retention** | How long logs/jobs are kept before the `maintenance` purge deletes them. |
| **Cache namespace** | A `CacheNS` grouping cached entries (e.g. `user`, `notes`). |
| **Scope** | A per-user (or per-entity) cache sub-keyspace invalidated in O(1) via a version counter. |
| **Single-flight** | De-duplicating concurrent cache misses so the factory runs once per key. |
| **TTL jitter** | A +/-10% randomization of cache expiry to avoid synchronized expiry. |
| **RBAC** | Role-Based Access Control: the static role-to-permission matrix that bootstraps decisions. |
| **ABAC** | Attribute-Based Access Control: decisions from subject/resource/action/environment attributes (ADR-0019). |
| **PDP** | Policy Decision Point: `app/core/authz.py`, where allow/deny is decided. |
| **PEP** | Policy Enforcement Point: where decisions are enforced (`require_permission`, service checks). |
| **Permission grant** | A `permission_grants` row: per-user page (resource) x action x effect (ALLOW/DENY) with optional conditions. |
| **Effective permissions** | Role baseline UNION ALLOW grants MINUS DENY grants for a user (deny always wins). |
| **own_only** | A grant condition meaning the permission applies only to resources the subject owns. |
