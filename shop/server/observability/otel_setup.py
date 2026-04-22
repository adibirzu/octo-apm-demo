"""OpenTelemetry initialization for OCTO Drone Shop.

When running with the shared platform libraries available, delegates core OTel setup (resource building,
APM exporters, process metrics) to shared.observability_lib. Falls back to
local implementation for standalone use.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from opentelemetry import trace
from sqlalchemy import event

if TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource

from server.config import cfg
from server.observability.correlation import current_trace_context, sql_attributes

logger = logging.getLogger(__name__)
_tracer_provider = None


def _try_shared_init(service_name: str, service_version: str,
                     apm_endpoint: str, apm_private_key: str) -> bool:
    """Try to initialize via shared.observability_lib when the shared library is available."""
    try:
        from shared.observability_lib import init_observability
        return init_observability(
            service_name=service_name,
            service_version=service_version,
            apm_endpoint=apm_endpoint or None,
            apm_data_key=apm_private_key or None,
            extra_attributes={
                "service.namespace": cfg.service_namespace,
                "service.instance.id": cfg.service_instance_id,
                "deployment.environment": cfg.app_env,
                "app.name": cfg.app_name,
                "app.brand": cfg.brand_name,
                "app.runtime": cfg.app_runtime,
                "cloud.provider": "oci",
                "oci.demo.stack": cfg.demo_stack_name,
                "db.target": cfg.database_target_label,
            },
        )
    except ImportError:
        return False


def _standalone_init(service_name: str, service_version: str,
                     apm_endpoint: str, apm_private_key: str):
    """Standalone OTel initialization (no shared library available)."""
    global _tracer_provider

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    import os as _os, platform as _platform, sys as _sys
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
        "process.runtime.name": _platform.python_implementation().lower(),
        "process.runtime.version": _platform.python_version(),
        "process.pid": _os.getpid(),
        "process.executable.name": _os.path.basename(_sys.executable),
        "host.name": _os.getenv("HOSTNAME", _platform.node()),
        "host.arch": _platform.machine(),
        "os.type": _platform.system().lower(),
        "os.description": f"{_platform.system()} {_platform.release()}",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
    })

    _tracer_provider = TracerProvider(resource=resource)

    if apm_endpoint and apm_private_key:
        base_url = apm_endpoint.rstrip('/').split('/20200101')[0]
        otlp_endpoint = f"{base_url}/20200101/opentelemetry/private/v1/traces"
        metrics_endpoint = f"{base_url}/20200101/opentelemetry/v1/metrics"
        auth_headers = {"Authorization": f"dataKey {apm_private_key}"}

        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=auth_headers)
        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel OTLP exporter -> OCI APM (%s)", service_name)

        try:
            from opentelemetry import metrics as otel_metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(endpoint=metrics_endpoint, headers=auth_headers)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            otel_metrics.set_meter_provider(meter_provider)
            _register_process_metrics_standalone(otel_metrics.get_meter(service_name + ".runtime"))
            logger.info("OCI APM metrics exporter configured (App Servers enabled)")
        except Exception as exc:
            logger.warning("OCI APM metrics export failed: %s", exc)
    else:
        _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel console exporter (no APM): %s", service_name)

    trace.set_tracer_provider(_tracer_provider)

    if apm_endpoint and apm_private_key and cfg.otlp_log_export_enabled:
        _init_otlp_log_export(resource, apm_endpoint, apm_private_key)


def _register_process_metrics_standalone(meter):
    """Register process runtime metrics (standalone fallback)."""
    import os, threading
    try:
        import psutil
        from opentelemetry import metrics as otel_metrics

        proc = psutil.Process(os.getpid())

        def _cpu_cb(_options):
            yield otel_metrics.Observation(proc.cpu_percent(interval=None) / 100.0)
        def _mem_cb(_options):
            yield otel_metrics.Observation(proc.memory_info().rss)
        def _thread_cb(_options):
            yield otel_metrics.Observation(threading.active_count())

        meter.create_observable_gauge("process.runtime.cpython.cpu.utilization", callbacks=[_cpu_cb], unit="1")
        meter.create_observable_gauge("process.runtime.cpython.memory", callbacks=[_mem_cb], unit="By")
        meter.create_observable_gauge("process.runtime.cpython.thread_count", callbacks=[_thread_cb], unit="{thread}")
    except ImportError:
        logger.info("psutil not installed — process metrics skipped")


def init_otel(service_name: str = "octo-crm-apm",
              service_version: str = "1.0.0",
              apm_endpoint: str = "", apm_private_key: str = "",
              sync_engine=None, async_engine=None):
    """Initialize OpenTelemetry with OCI APM exporter.

    Tries shared.observability_lib first (shared-platform context), then falls
    back to standalone initialization.
    """
    global _tracer_provider

    # Core OTel setup: try shared library, fall back to standalone
    if not _try_shared_init(service_name, service_version, apm_endpoint, apm_private_key):
        _standalone_init(service_name, service_version, apm_endpoint, apm_private_key)

    # App-specific instrumentation (always runs regardless of init path)
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

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("httpx instrumented (distributed trace propagation enabled)")
    except Exception:
        pass

    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception:
        pass


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
