# Runbook: SLOs and alerts

> Service-level objectives, the error budget, and what each alert means.

## SLOs
- **Availability**: 99.5% of requests succeed (non-5xx) over 28 days.
- **Latency**: p95 < 500 ms for API routes.
- **Readiness**: `/health/ready` 200.

## Error budget
100% − 99.5% = 0.5% (≈ 3.6 h/month). If the budget is exhausted, freeze features and prioritize
reliability.

## Alerts (`deploy/prometheus/alerts.yml`)
| Alert | Meaning |
|---|---|
| High 5xx ratio | server errors spiking |
| High p95 latency | slow requests |
| Readiness failing | DB/cache down |
| Oldest queued high | workers behind |
| Failed jobs growing | handler failures |
| Activity dropped rising | buffer overload |
| Cache error rate | cache backend issues |

## Common mistakes
- Ignoring the error budget.
- Alerting on raw paths (use route templates).

## See also
- [17 — Observability](../17-observability.md)
- [incident-response.md](incident-response.md)