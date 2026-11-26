# 0010 — Token model

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need short-lived access, safe refresh, and single-use email/reset tokens, with global
invalidations and reuse detection.

## Decision
Access JWT (15 min) carries `tv` (token_version); bumping `token_version` invalidates all access
tokens. Refresh tokens are opaque, stored as sha256, rotated per use, and grouped in families; reuse
of a revoked token revokes the family. One-time tokens (verify/reset) are hashed and single-use.

## Consequences
- Logout-all / password change are a single `token_version` bump.
- Reuse detection contains theft to a family.
- Raw tokens are never stored (only hashes).