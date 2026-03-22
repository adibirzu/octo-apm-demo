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


def _register_process_metrics(meter):
    """Register process runtime metrics for OCI APM App Servers page."""
    import os, threading
    try:
        import psutil
        proc = psutil.Process(os.getpid())

        def _cpu_cb(_options):
            from opentelemetry.sdk.metrics import Observation
            yield Observation(proc.cpu_percent(interval=None) / 100.0)

        def _mem_cb(_options):
            from opentelemetry.sdk.metrics import Observation
            yield Observation(proc.memory_info().rss)

        def _thread_cb(_options):
            from opentelemetry.sdk.metrics import Observation
            yield Observation(threading.active_count())

        meter.create_observable_gauge("process.runtime.cpython.cpu.utilization", callbacks=[_cpu_cb], unit="1")
        meter.create_observable_gauge("process.runtime.cpython.memory", callbacks=[_mem_cb], unit="By")
        meter.create_observable_gauge("process.runtime.cpython.thread_count", callbacks=[_thread_cb], unit="{thread}")
    except ImportError:
        logger.info("psutil not installed — process metrics skipped (pip install psutil)")


def init_otel(app=None, sync_engine=None):
    """Initialize OpenTelemetry with OCI APM exporter."""
    global _tracer, _initialized

    if _initialized:
        return _tracer or trace.get_tracer(cfg.otel_service_name, cfg.app_version)

    import os, platform, sys
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
        # Process/OS attributes for OCI APM App Servers page
        "process.runtime.name": platform.python_implementation().lower(),
        "process.runtime.version": platform.python_version(),
        "process.pid": os.getpid(),
        "process.executable.name": os.path.basename(sys.executable),
        "host.name": os.getenv("HOSTNAME", platform.node()),
        "host.arch": platform.machine(),
        "os.type": platform.system().lower(),
        "os.description": f"{platform.system()} {platform.release()}",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
    })

    provider = TracerProvider(resource=resource)

    if cfg.apm_configured:
        base_url = cfg.oci_apm_endpoint.rstrip('/').split('/20200101')[0]
        traces_endpoint = f"{base_url}/20200101/opentelemetry/private/v1/traces"
        metrics_endpoint = f"{base_url}/20200101/opentelemetry/v1/metrics"
        auth_headers = {"Authorization": f"dataKey {cfg.oci_apm_private_datakey}"}

        exporter = OTLPSpanExporter(endpoint=traces_endpoint, headers=auth_headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OCI APM OTLP trace exporter configured: %s", cfg.oci_apm_endpoint)

        # Metrics export for OCI APM App Servers page
        try:
            from opentelemetry import metrics as otel_metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(endpoint=metrics_endpoint, headers=auth_headers)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            otel_metrics.set_meter_provider(meter_provider)

            # Register process runtime metrics (CPU, memory, threads)
            _register_process_metrics(otel_metrics.get_meter(cfg.otel_service_name + ".runtime"))
            logger.info("OCI APM metrics exporter configured (App Servers enabled)")
        except Exception as exc:
            logger.warning("OCI APM metrics export could not be enabled: %s", exc)
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
