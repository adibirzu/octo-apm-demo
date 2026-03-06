"""OpenTelemetry initialization for MuShop Cloud Native Portal."""

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger(__name__)
_tracer_provider = None


def init_otel(service_name: str = "mushop-cloudnative",
              service_version: str = "1.0.0",
              apm_endpoint: str = "", apm_private_key: str = "",
              sync_engine=None):
    global _tracer_provider

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": "production",
        "service.namespace": "mushop",
    })

    _tracer_provider = TracerProvider(resource=resource)

    if apm_endpoint and apm_private_key:
        otlp_endpoint = f"{apm_endpoint}/20200101/opentelemetry/private/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={"Authorization": f"dataKey {apm_private_key}"},
        )
        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel OTLP exporter → OCI APM (%s)", service_name)
    else:
        _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel console exporter (no APM): %s", service_name)

    trace.set_tracer_provider(_tracer_provider)

    # Instrument SQLAlchemy if sync engine provided
    if sync_engine:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument(engine=sync_engine)
        except Exception:
            pass


def get_tracer(name: str = "mushop") -> trace.Tracer:
    return trace.get_tracer(name)
