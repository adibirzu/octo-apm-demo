"""OpenTelemetry initialization for OCTO Drone Shop."""

import logging
import time

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from sqlalchemy import event

from server.config import cfg
from server.observability.correlation import current_trace_context, sql_attributes

logger = logging.getLogger(__name__)
_tracer_provider = None


def init_otel(service_name: str = "octo-crm-apm",
              service_version: str = "1.0.0",
              apm_endpoint: str = "", apm_private_key: str = "",
              sync_engine=None, async_engine=None):
    global _tracer_provider

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": cfg.app_env,
        "service.namespace": cfg.service_namespace,
        "service.instance.id": cfg.service_instance_id,
        "app.name": cfg.app_name,
        "app.brand": cfg.brand_name,
        "app.runtime": cfg.app_runtime,
        "cloud.provider": "oci",
        "oci.demo.stack": cfg.demo_stack_name,
        "db.target": cfg.database_target_label,
    })

    _tracer_provider = TracerProvider(resource=resource)

    if apm_endpoint and apm_private_key:
        otlp_endpoint = f"{apm_endpoint}/20200101/opentelemetry/private/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={"Authorization": f"dataKey {apm_private_key}"},
        )
        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel OTLP exporter -> OCI APM (%s)", service_name)
    else:
        _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel console exporter (no APM): %s", service_name)

    trace.set_tracer_provider(_tracer_provider)

    # Auto-instrument SQLAlchemy for both sync and async execution paths.
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        candidate_engines = []
        if sync_engine is not None:
            candidate_engines.append(sync_engine)
        if async_engine is not None and getattr(async_engine, "sync_engine", None) is not None:
            candidate_engines.append(async_engine.sync_engine)

        seen_ids = set()
        for engine in candidate_engines:
            if id(engine) in seen_ids:
                continue
            seen_ids.add(id(engine))
            try:
                SQLAlchemyInstrumentor().instrument(engine=engine)
            except Exception:
                logger.debug("SQLAlchemy instrumentation already active", exc_info=True)
            _register_sql_span_enrichment(engine)
    except Exception:
        logger.debug("SQLAlchemy instrumentation unavailable", exc_info=True)

    # Auto-instrument httpx — injects W3C traceparent on all outbound HTTP calls
    # This is critical for distributed tracing between OCTO-CRM-APM and CRM
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("httpx instrumented (distributed trace propagation enabled)")
    except Exception:
        pass

    # Inject trace context into Python logging (for log correlation)
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception:
        pass

    if apm_endpoint and apm_private_key and cfg.otlp_log_export_enabled:
        _init_otlp_log_export(resource, apm_endpoint, apm_private_key)


def get_tracer(name: str = "octo-crm-apm") -> trace.Tracer:
    return trace.get_tracer(name)


def _register_sql_span_enrichment(engine) -> None:
    if getattr(engine, "_octo_sql_enrichment_registered", False):
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        span = trace.get_current_span()
        if not span or not span.is_recording():
            return
        context._octo_query_start = time.monotonic()
        attrs = sql_attributes(
            statement,
            connection_name=cfg.oracle_dsn,
            database_target=cfg.database_target_label,
        )
        attrs["db.trace_id"] = current_trace_context()["trace_id"]
        attrs["db.executemany"] = bool(executemany)
        attrs["db.bind_count"] = len(parameters) if isinstance(parameters, (list, tuple, dict)) else 0
        for key, value in attrs.items():
            if value not in ("", None):
                span.set_attribute(key, value)

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        span = trace.get_current_span()
        if not span or not span.is_recording():
            return
        started = getattr(context, "_octo_query_start", None)
        if started is not None:
            span.set_attribute("db.client.execution_time_ms", round((time.monotonic() - started) * 1000, 2))
        rowcount = getattr(cursor, "rowcount", None)
        if rowcount is not None and rowcount >= 0:
            span.set_attribute("db.row_count", int(rowcount))

    setattr(engine, "_octo_sql_enrichment_registered", True)


def _init_otlp_log_export(resource: Resource, apm_endpoint: str, apm_private_key: str) -> None:
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        logs_url = f"{apm_endpoint.rstrip('/')}/20200101/opentelemetry/private/v1/logs"
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=logs_url,
                    headers={"Authorization": f"dataKey {apm_private_key}"},
                )
            )
        )
        set_logger_provider(logger_provider)
        logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
        logger.info("OTel OTLP log exporter -> OCI APM (%s)", logs_url)
    except Exception:
        logger.debug("OTLP log exporter unavailable", exc_info=True)
