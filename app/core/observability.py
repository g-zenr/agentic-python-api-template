"""Optional observability: Sentry and OpenTelemetry (lazy imports; base install works without)."""

import logging
from typing import Any

from app.core.config import settings
from app.core.constants import Redaction

log = logging.getLogger(__name__)


def setup_sentry() -> None:
    dsn = settings.sentry_dsn
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning(
            "SENTRY_DSN set but sentry-sdk is not installed (pip install '.[observability]')"
        )  # noqa: E501
        return

    def before_send(event: dict[str, Any], hint: object) -> dict[str, Any]:
        request = event.get("request", {})
        request.pop("data", None)
        request.pop("cookies", None)
        return event

    sentry_sdk.init(
        dsn=dsn.get_secret_value(),
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=before_send,
    )


def setup_otel(app: object) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning("OTEL_ENABLED set but the otel packages are not installed")
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )  # noqa: E501
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


REDACTION_FIELDS = Redaction.FIELDS
