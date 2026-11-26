# 0014 — Observability stack

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need logs, metrics, traces, and health that work in dev without extra installs and in prod with
backends.

## Decision
Stdlib JSON logging with redaction; `prometheus-client` metrics at `/metrics` (token-guarded) and a
worker metrics port; optional Sentry and OpenTelemetry (lazy imports, `[observability]` extra);
`/health/live` and `/health/ready` with a shutdown flag.

## Consequences
- Base install has no hard dependency on Sentry/OTel.
- Metrics use route templates (no high-cardinality raw paths).
- Readiness fails fast during shutdown.