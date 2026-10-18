"""
Telemetry middleware — OpenTelemetry instrumentation.
Sets up tracing and metrics for FastAPI, Redis, and HTTPX.
"""

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = structlog.get_logger(__name__)


def _parse_otlp_headers(raw: str) -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS string into a dict.
    Accepts both `Key=Value,Key2=Value2` and `Key=Value` (single) formats,
    and URL-decodes percent-encoded values (e.g. %20 → space)."""
    import urllib.parse
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            headers[k.strip()] = urllib.parse.unquote(v.strip())
    return headers


def setup_telemetry(app: FastAPI | None = None) -> None:
    """
    Configure OpenTelemetry tracing and metrics. No-op if the OTEL endpoint is unreachable.

    `app` is optional so non-HTTP processes can call this too. That matters: the Celery worker
    never called it, so it had no MeterProvider, and every custom instrument recorded there was a
    permanent no-op — `briefs_delivered` (services/brief_engine.py) and `governor_suppressed`
    (services/event_bus.py) both fire in the worker, so they could never reach Grafana no matter
    how much real traffic ran. Confirmed 2026-08-15: a brief was genuinely delivered and
    `kairos_briefs_delivered_total` still did not exist in Grafana Cloud.
    """
    try:
        import os

        from api.config import settings

        endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
        raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers = _parse_otlp_headers(raw_headers) if raw_headers else {}

        # Grafana Cloud OTLP gateway uses sub-paths for each signal
        traces_endpoint = endpoint.rstrip("/") + "/v1/traces"
        metrics_endpoint = endpoint.rstrip("/") + "/v1/metrics"

        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.OTEL_SERVICE_VERSION,
            "deployment.environment": settings.APP_ENV,
        })

        # --- Traces ---
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(
                endpoint=traces_endpoint,
                headers=headers,
            ))
        )
        trace.set_tracer_provider(tracer_provider)

        # --- Metrics ---
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=metrics_endpoint,
                headers=headers,
            ),
            # Grafana Cloud Free includes 1 data point per series per minute; 15 s billed every series 4x.
            export_interval_millis=60_000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # --- Auto-instrumentors ---
        # FastAPI instrumentation only applies to the API process; the worker has no app.
        if app is not None:
            FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
        RedisInstrumentor().instrument(tracer_provider=tracer_provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)

        log.info("telemetry.setup", endpoint=endpoint, headers_keys=list(headers.keys()))
    except Exception as e:
        log.warning("telemetry.setup_failed", error=str(e), reason="OTEL collector may not be running")
