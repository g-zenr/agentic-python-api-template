"""Prometheus metrics (defined once; updated by middleware, cache, worker, and jobs)."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route", "status"], registry=REGISTRY
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP latency", ["method", "route"], registry=REGISTRY
)
cache_operations_total = Counter(
    "cache_operations_total", "Cache ops", ["result"], registry=REGISTRY
)
rate_limit_rejections_total = Counter(
    "rate_limit_rejections_total", "Rate limit rejections", ["bucket"], registry=REGISTRY
)
activity_dropped_total = Counter(
    "activity_dropped_total", "Dropped activity entries", [], registry=REGISTRY
)
jobs_processed_total = Counter(
    "jobs_processed_total", "Jobs processed", ["type", "outcome"], registry=REGISTRY
)
job_duration_seconds = Histogram(
    "job_duration_seconds", "Job duration", ["type"], registry=REGISTRY
)
jobs_queue_depth = Gauge("jobs_queue_depth", "Queue depth by status", ["status"], registry=REGISTRY)
jobs_oldest_queued_age_seconds = Gauge(
    "jobs_oldest_queued_age_seconds", "Oldest queued job age", [], registry=REGISTRY
)
mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total", "MCP tool calls", ["client", "tool"], registry=REGISTRY
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
