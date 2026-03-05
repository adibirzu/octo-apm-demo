"""OpenTelemetry initialization for OCI APM backend tracing."""

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from server.config import cfg

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None


def init_otel(app=None, sync_engine=None):
    """Initialize OpenTelemetry with OCI APM exporter."""
    global _tracer

    resource = Resource.create({
        "service.name": f"{cfg.otel_service_name}-{cfg.app_runtime}",
        "service.version": "1.0.0",
        "deployment.environment": cfg.app_env,
        "app.runtime": cfg.app_runtime,
    })

    provider = TracerProvider(resource=resource)

    if cfg.apm_configured:
        endpoint = f"{cfg.oci_apm_endpoint}/20200101/opentelemetry/private/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"dataKey {cfg.oci_apm_private_datakey}"},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OCI APM OTLP exporter configured: %s", cfg.oci_apm_endpoint)
    else:
        logger.warning("OCI APM not configured — traces will not be exported")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("enterprise-crm-portal", "1.0.0")

    # Auto-instrument SQLAlchemy (sync engine for instrumentation hooks)
    if sync_engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=sync_engine)

    # Auto-instrument outbound HTTP calls
    HTTPXClientInstrumentor().instrument()

    # Inject trace context into Python logging
    LoggingInstrumentor().instrument(set_logging_format=True)

    return _tracer


def get_tracer() -> trace.Tracer:
    """Return the app tracer, or a no-op tracer if not initialized."""
    if _tracer is None:
        return trace.get_tracer("enterprise-crm-portal")
    return _tracer
