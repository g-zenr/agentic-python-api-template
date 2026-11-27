# 16 — Security

> Threat model, the production guard, request protection, tokens, RBAC, and secrets.

## What you will learn
- What the production config guard rejects.
- The request protections (headers, body limit, trusted hosts, rate limits).
- The token model (access + rotating refresh + one-time) and RBAC.
- Secret handling and a hardening checklist.

## Production guard
`Settings` raises one `ValueError` listing EVERY unsafe prod setting: weak/short/default JWT secret,
`CORS_ORIGINS=*`, `ALLOWED_HOSTS=*`, empty `DATABASE_URL`, non-redis cache, embedded worker, non-json
logs, console email, non-https `APP_BASE_URL`, MCP enabled with no clients, metrics without a token.
Every new prod-critical setting gets a guard line (AGENTS rule 19).

## Request protection (middleware order)
TrustedHost → BodyLimit → CORS → context (rate limit + security headers).
- **Headers**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP (skip on `/docs`),
  HSTS in prod.
- **Body limit**: `MAX_BODY_BYTES` by Content-Length and streamed bytes → 413.
- **Rate limits** (fixed window, fail-open): global per-IP, plus login/refresh/forgot/register per IP
  and login/forgot per account (email hash). Account lockout counts failed logins only; unknown emails
  behave identically (no enumeration).

## Token model
- **Access** JWT: `sub`, `tv` (token_version), `typ=access`, `exp` (15 min). A `tv` mismatch or a
  bumped `token_version` invalidates all access tokens.
- **Refresh**: opaque, stored as sha256, rotated on every use; reuse of a revoked token revokes the
  whole family (reuse detection).
- **One-time**: email verification / password reset, single use, hashed.

## RBAC + ABAC
`ROLE_PERMISSIONS` is the baseline. Decisions run through the PDP (`app/core/authz.py`, ADR-0019):
effective = baseline UNION ALLOW grants MINUS DENY grants (deny always wins), cached per user
(`permissions:<id>`), invalidated on grant writes. `require_permission(...)` guards routes and
audits denials (reason: `insufficient_permission` | `permission_denied` | `policy_error`).
Grants carry optional ABAC conditions (`{"own_only": true}`): they never satisfy route gates alone,
but authorize self-scoped reads on `/audit` + `/audit/activity` and owner-matched checks in services
(e.g. `jobs`). Admin API: the `permissions` feature (catalog, effective set, replace/revoke) gated by
`permissions:manage`. Evaluation errors deny when `AUTHZ_FAIL_CLOSED` (required in prod).

## Secrets
Secrets come from env (`SecretStr`), never logged; audit metadata is redacted (`Redaction.FIELDS`);
failed-login audit stores `email_hash`, never the email.

## Common mistakes
- Using the default JWT secret in prod (guard rejects).
- Storing raw emails/tokens in audit metadata.
- Forgetting a rate limit on a sensitive POST.

## See also
- [08 — Authentication](08-authentication.md)
- [17 — Observability](17-observability.md)
- [20 — Account lifecycle and privacy](20-account-lifecycle-and-privacy.md)