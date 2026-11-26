# 17 — Observability

> Logs, metrics, tracing, health semantics, and how to debug a slow request.

## What you will learn
- The JSON log format and redaction.
- The Prometheus metric catalog.
- Tracing/Sentry setup.
- Health (live vs ready) and shutdown behavior.

## Logging
`LOG_FORMAT=json` emits one object per line: `ts, level, logger, msg, request_id, user_id, job_id,
trace_id, exc`. A redaction filter masks `Redaction.FIELDS` and any `Bearer` token in messages.
Request bodies are never logged.

## Metrics (`/metrics`, token-guarded)
`http_requests_total{method,route,status}`, `http_request_duration_seconds{method,route}`,
`cache_operations_total{result}`, `rate_limit_rejections_total{bucket}`, `activity_dropped_total`,
`jobs_processed_total{type,outcome}`, `job_duration_seconds{type}`, `jobs_queue_depth{status}`,
`jobs_oldest_queued_age_seconds`, `mcp_tool_calls_total{client,tool}`. The worker exposes its own
registry on `WORKER_METRICS_PORT`.

## Tracing & Sentry
`OTEL_ENABLED` instruments FastAPI with an OTLP exporter; `SENTRY_DSN` enables Sentry with
`send_default_pii=False` and a `before_send` that drops bodies.

## Health
- `/health/live` — always 200 (process up).
- `/health/ready` — 200 when DB (`SELECT 1` under a timeout) and cache (`ping`) are up, else 503 with
  per-check detail; returns 503 immediately while `app.state.shutting_down`.
- `/health` — hidden alias of live.

## Debugging a slow request
1. Find the request by `request_id` in logs.
2. Check `http_request_duration_seconds` for the route.
3. Inspect `/audit/activity` for the route template + duration.
4. If a job is involved, check `jobs_oldest_queued_age_seconds` and queue depth.

## Common mistakes
- Logging PII or secrets.
- Using the memory cache across processes (per-process metrics differ).
- Hitting `/health/live` for readiness (use `/ready`).

## See also
- [11 — Deployment](11-deployment.md)
- [16 — Security](16-security.md)
- `deploy/prometheus/alerts.yml`