"""OpenTelemetry Metrics — the missing third pillar of observability.

Provides both OTLP metric export (to OCI APM) and a Prometheus scrape endpoint.
This module defines all technical and runtime metrics; business metrics live in
business_metrics.py to keep concerns separated.
"""

import logging
import os
import time

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from server.config import cfg

logger = logging.getLogger(__name__)

_meter: metrics.Meter | None = None
_initialized = False


def init_metrics() -> metrics.Meter:
    """Initialize OTel MeterProvider with Prometheus + optional OTLP export."""
    global _meter, _initialized

    if _initialized and _meter:
        return _meter

    resource = Resource.create({
        "service.name": cfg.otel_service_name,
        "service.namespace": cfg.service_namespace,
        "service.version": cfg.app_version,
        "service.instance.id": cfg.service_instance_id,
        "deployment.environment": cfg.app_env,
        "app.runtime": cfg.app_runtime,
        "cloud.provider": "oci",
    })

    readers = []

    # Prometheus scrape endpoint (always enabled)
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        prom_reader = PrometheusMetricReader()
        readers.append(prom_reader)
        logger.info("Prometheus metric reader enabled — /metrics endpoint available")
    except ImportError:
        logger.warning("opentelemetry-exporter-prometheus not installed — /metrics disabled")

    # OTLP export to OCI APM (if configured)
    if cfg.apm_configured:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            otlp_endpoint = f"{cfg.oci_apm_endpoint.rstrip('/')}/20200101/opentelemetry/private/v1/metrics"
            otlp_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    endpoint=otlp_endpoint,
                    headers={"Authorization": f"dataKey {cfg.oci_apm_private_datakey}"},
                ),
                export_interval_millis=15_000,
            )
            readers.append(otlp_reader)
            logger.info("OCI APM OTLP metric exporter configured: %s", otlp_endpoint)
        except ImportError:
            logger.warning("OTLP metric exporter not available")

    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)
    _meter = metrics.get_meter("crm.observability", cfg.app_version)

    _initialized = True
    return _meter


def get_meter() -> metrics.Meter:
    """Return the app meter, initializing if needed."""
    if _meter is None:
        return init_metrics()
    return _meter


# ── HTTP RED Metrics (Rate, Errors, Duration) ─────────────────────

meter = None  # lazy init


def _m():
    global meter
    if meter is None:
        meter = get_meter()
    return meter


class HTTPMetrics:
    """HTTP request metrics — instantiated once at import time, instruments lazily."""

    def __init__(self):
        self._inited = False
        self.requests_total = None
        self.request_duration = None
        self.requests_in_flight = None

    def _ensure(self):
        if self._inited:
            return
        m = _m()
        self.requests_total = m.create_counter(
            "crm.http.requests.total",
            description="Total HTTP requests by route, method, status",
            unit="1",
        )
        self.request_duration = m.create_histogram(
            "crm.http.request.duration",
            description="HTTP request latency in milliseconds",
            unit="ms",
        )
        self.requests_in_flight = m.create_up_down_counter(
            "crm.http.requests.in_flight",
            description="Currently in-flight HTTP requests",
            unit="1",
        )
        self._inited = True

    def record_request(self, route: str, method: str, status_code: int, duration_ms: float):
        self._ensure()
        attrs = {
            "http.route": route,
            "http.method": method,
            "http.status_code": str(status_code),
            "http.status_class": f"{status_code // 100}xx",
        }
        self.requests_total.add(1, attrs)
        self.request_duration.record(duration_ms, attrs)

    def request_started(self, route: str, method: str):
        self._ensure()
        self.requests_in_flight.add(1, {"http.route": route, "http.method": method})

    def request_finished(self, route: str, method: str):
        self._ensure()
        self.requests_in_flight.add(-1, {"http.route": route, "http.method": method})


class DBMetrics:
    """Database query metrics."""

    def __init__(self):
        self._inited = False
        self.query_duration = None
        self.query_total = None
        self.pool_checked_out = None

    def _ensure(self):
        if self._inited:
            return
        m = _m()
        self.query_duration = m.create_histogram(
            "crm.db.query.duration",
            description="Database query latency in milliseconds",
            unit="ms",
        )
        self.query_total = m.create_counter(
            "crm.db.query.total",
            description="Total database queries by operation type",
            unit="1",
        )
        self._inited = True

    def record_query(self, operation: str, duration_ms: float):
        self._ensure()
        attrs = {"db.operation": operation, "db.system": "oracle"}
        self.query_duration.record(duration_ms, attrs)
        self.query_total.add(1, attrs)


class RuntimeMetrics:
    """Process-level runtime metrics collected via observable gauges."""

    def __init__(self):
        self._inited = False

    def setup(self):
        if self._inited:
            return
        m = _m()
        try:
            import resource as res_mod

            def _rss_callback(options):
                rusage = res_mod.getrusage(res_mod.RUSAGE_SELF)
                # maxrss is in KB on Linux, bytes on macOS
                rss_bytes = rusage.ru_maxrss
                if os.uname().sysname == "Darwin":
                    rss_bytes = rss_bytes  # already bytes on macOS
                else:
                    rss_bytes = rss_bytes * 1024  # KB to bytes on Linux
                yield metrics.Observation(rss_bytes)

            m.create_observable_gauge(
                "crm.process.memory.rss",
                callbacks=[_rss_callback],
                description="Process RSS memory in bytes",
                unit="By",
            )
        except Exception:
            logger.debug("Could not set up RSS metric", exc_info=True)

        try:
            _start_time = time.time()

            def _uptime_callback(options):
                yield metrics.Observation(time.time() - _start_time)

            m.create_observable_gauge(
                "crm.process.uptime",
                callbacks=[_uptime_callback],
                description="Process uptime in seconds",
                unit="s",
            )
        except Exception:
            logger.debug("Could not set up uptime metric", exc_info=True)

        self._inited = True


# Singleton instances
http_metrics = HTTPMetrics()
db_metrics = DBMetrics()
runtime_metrics = RuntimeMetrics()
