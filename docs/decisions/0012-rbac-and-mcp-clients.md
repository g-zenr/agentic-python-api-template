# 0012 — RBAC and scoped MCP clients

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Coarse `AdminUser` is too blunt, and a single MCP key cannot scope which tools a client may call.

## Decision
Permission-based RBAC: `ROLE_PERMISSIONS` maps roles to `Permission`s; `require_permission(...)`
guards routes and audits denials. MCP clients are configured with per-client scoped keys
(`MCP_CLIENTS` = name + key_sha256 + tools); the gate hashes the bearer and matches, and
`attach_tools` enforces each client's tool list.

## Consequences
- New roles/permissions are data, not code branches.
- A leaked MCP key is scoped to its tools and revocable.
- `AdminUser`/`INSUFFICIENT_ROLE` are removed.