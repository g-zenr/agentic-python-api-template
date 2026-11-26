# 0017 — PII retention and audit scrubbing

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Audit/activity logs hold PII (ip, user_agent, attempted email). We must retain them for security but
erase on account deletion.

## Decision
Failed-login audit stores `email_hash` (never the email). Account erase scrubs `ip`/`user_agent` to
NULL in `audit_logs` and `ip` in `activity_logs` via raw SQL; the `audit_logs_guard` trigger allows
exactly that (NULL scrubbing) and blocks all other UPDATEs. Retention: activity `ACTIVITY_RETENTION_DAYS`,
audit `AUDIT_RETENTION_DAYS` (0 = forever), audit PII `AUDIT_PII_RETENTION_DAYS`.

## Consequences
- Audit rows survive user deletion (pseudonymous `actor_id`).
- Only NULL-scrubbing is permitted; the trigger enforces it.
- PII is minimized and time-bounded.