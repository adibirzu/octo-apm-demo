"""OpenTelemetry Metrics — Prometheus scrape endpoint + OTLP export to OCI APM.

Provides HTTP RED metrics, DB query metrics, and runtime metrics.
Business metrics live in business_metrics.py.
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

_meter = None
_initialized = False


def init_metrics():
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

    # Prometheus scrape endpoint
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        readers.append(PrometheusMetricReader())
        logger.info("Prometheus metric reader enabled — /metrics endpoint available")
    except ImportError:
        logger.warning("opentelemetry-exporter-prometheus not installed — /metrics disabled")

    # NOTE: OCI APM does NOT support OTLP metric ingestion (only traces).
    # OTLP metric export is disabled to avoid 404 errors every 15s.
    # Metrics are available via Prometheus /metrics endpoint for Grafana/scraping.

    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)
    _meter = metrics.get_meter("shop.observability", cfg.app_version)
    _initialized = True
    return _meter


def get_meter():
    if _meter is None:
        return init_metrics()
    return _meter


# ── HTTP RED Metrics ─────────────────────────────────────────

class HTTPMetrics:
    def __init__(self):
        self._inited = False
        self.requests_total = None
        self.request_duration = None
        self.requests_in_flight = None

    def _ensure(self):
        if self._inited:
            return
        m = get_meter()
        self.requests_total = m.create_counter(
            "shop.http.requests.total",
            description="Total HTTP requests by route, method, status",
            unit="1",
        )
        self.request_duration = m.create_histogram(
            "shop.http.request.duration",
            description="HTTP request latency in milliseconds",
            unit="ms",
        )
        self.requests_in_flight = m.create_up_down_counter(
            "shop.http.requests.in_flight",
            description="Currently in-flight HTTP requests",
            unit="1",
        )
        self._inited = True

    def record_request(self, route, method, status_code, duration_ms):
        self._ensure()
        attrs = {
            "http.route": route,
            "http.method": method,
            "http.status_code": str(status_code),
            "http.status_class": f"{status_code // 100}xx",
        }
        self.requests_total.add(1, attrs)
        self.request_duration.record(duration_ms, attrs)

    def request_started(self, route, method):
        self._ensure()
        self.requests_in_flight.add(1, {"http.route": route, "http.method": method})

    def request_finished(self, route, method):
        self._ensure()
        self.requests_in_flight.add(-1, {"http.route": route, "http.method": method})


class RuntimeMetrics:
    def __init__(self):
        self._inited = False

    def setup(self):
        if self._inited:
            return
        m = get_meter()
        try:
            import resource as res_mod
            def _rss_callback(options):
                rusage = res_mod.getrusage(res_mod.RUSAGE_SELF)
                rss = rusage.ru_maxrss
                if os.uname().sysname != "Darwin":
                    rss = rss * 1024
                yield metrics.Observation(rss)
            m.create_observable_gauge("shop.process.memory.rss", callbacks=[_rss_callback],
                                      description="Process RSS memory in bytes", unit="By")
        except Exception:
            pass
        try:
            _start = time.time()
            def _uptime_cb(options):
                yield metrics.Observation(time.time() - _start)
            m.create_observable_gauge("shop.process.uptime", callbacks=[_uptime_cb],
                                      description="Process uptime in seconds", unit="s")
        except Exception:
            pass
        self._inited = True


http_metrics = HTTPMetrics()
runtime_metrics = RuntimeMetrics()
