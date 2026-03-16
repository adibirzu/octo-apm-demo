"""OpenTelemetry initialization for OCI APM backend tracing."""

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from server.config import cfg

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None
_initialized = False


def init_otel(app=None, sync_engine=None):
    """Initialize OpenTelemetry with OCI APM exporter."""
    global _tracer, _initialized

    if _initialized:
        return _tracer or trace.get_tracer(cfg.otel_service_name, cfg.app_version)

    resource = Resource.create({
        "service.name": cfg.otel_service_name,
        "service.namespace": cfg.service_namespace,
        "service.version": cfg.app_version,
        "service.instance.id": cfg.service_instance_id,
        "deployment.environment": cfg.app_env,
        "app.runtime": cfg.app_runtime,
        "app.brand": cfg.brand_name,
        "cloud.provider": "oci",
        "oci.demo.stack": cfg.demo_stack_name,
        "db.target": cfg.database_target_label,
    })

    provider = TracerProvider(resource=resource)

    if cfg.apm_configured:
        endpoint = f"{cfg.oci_apm_endpoint.rstrip('/')}/20200101/opentelemetry/private/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"dataKey {cfg.oci_apm_private_datakey}"},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OCI APM OTLP exporter configured: %s", cfg.oci_apm_endpoint)
        if cfg.otlp_log_export_enabled:
            _init_otlp_log_export(resource)
    else:
        logger.warning("OCI APM not configured — traces will not be exported")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(cfg.otel_service_name, cfg.app_version)

    # Auto-instrument SQLAlchemy (sync engine for instrumentation hooks)
    if sync_engine is not None:
        try:
            SQLAlchemyInstrumentor().instrument(engine=sync_engine)
        except Exception:
            logger.debug("SQLAlchemy instrumentation already active", exc_info=True)

    # Auto-instrument outbound HTTP calls with peer.service enrichment for topology
    def _httpx_request_hook(span, request):
        """Enrich HTTPX client spans with peer.service for APM topology."""
        if span and span.is_recording() and request:
            host = request.url.host or ""
            span.set_attribute("peer.service", host)
            span.set_attribute("server.address", host)

    try:
        HTTPXClientInstrumentor().instrument(request_hook=_httpx_request_hook)
    except Exception:
        logger.debug("HTTPX instrumentation already active", exc_info=True)

    # Inject trace context into Python logging
    try:
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception:
        logger.debug("Logging instrumentation already active", exc_info=True)

    _initialized = True

    return _tracer


def get_tracer() -> trace.Tracer:
    """Return the app tracer, or a no-op tracer if not initialized."""
    if _tracer is None:
        return trace.get_tracer(cfg.otel_service_name)
    return _tracer


def _init_otlp_log_export(resource: Resource):
    """Send Python logs to OCI APM OTLP logs for span-level drilldown."""
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        logs_url = f"{cfg.oci_apm_endpoint.rstrip('/')}/20200101/opentelemetry/private/v1/logs"
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=logs_url,
                    headers={"Authorization": f"dataKey {cfg.oci_apm_private_datakey}"},
                )
            )
        )
        set_logger_provider(logger_provider)
        root_logger = logging.getLogger()
        root_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
        logger.info("OCI APM OTLP log exporter configured: %s", logs_url)
    except Exception:
        logger.warning("OCI APM OTLP log export could not be enabled", exc_info=True)
