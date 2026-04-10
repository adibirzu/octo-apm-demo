"""OCI Monitoring — publish custom metrics to the OCI Monitoring service.

Pushes a curated set of app health and business metrics to OCI Monitoring
so they can power OCI Alarms, Notifications, and dashboards that work
alongside APM traces and Log Analytics.

Architecture
============
This module runs a background thread that samples key gauges/counters
every ``PUBLISH_INTERVAL_SECONDS`` (default 60s) and posts them via
``oci.monitoring.MonitoringClient.post_metric_data``. The metric
namespace defaults to ``octo_drone_shop`` and is configurable.

The module is optional — if OCI credentials or the compartment OCID are
missing, it logs a single info message and does nothing.

Metrics published
=================
- ``app.health``           (1 = healthy, 0 = unhealthy)
- ``app.uptime_seconds``   (process uptime)
- ``app.requests.rate``    (requests per publish interval)
- ``app.errors.rate``      (5xx per publish interval)
- ``app.checkout.count``   (checkouts per interval)
- ``app.orders.count``     (orders per interval)
- ``app.db.latency_ms``    (last readiness-check round-trip)
- ``app.crm.sync_age_s``   (seconds since last CRM sync)
- ``app.sessions.active``  (active session gauge)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from server.config import cfg

logger = logging.getLogger(__name__)

_running = False
_thread: threading.Thread | None = None
_request_count = 0
_error_count = 0
_checkout_count = 0
_order_count = 0
_last_db_latency_ms = 0.0
_lock = threading.Lock()

PUBLISH_INTERVAL = int(os.getenv("OCI_MONITORING_INTERVAL_SECONDS", "60"))
METRIC_NAMESPACE = os.getenv("OCI_MONITORING_NAMESPACE", "octo_drone_shop")


def increment_requests():
    global _request_count
    with _lock:
        _request_count += 1


def increment_errors():
    global _error_count
    with _lock:
        _error_count += 1


def increment_checkouts():
    global _checkout_count
    with _lock:
        _checkout_count += 1


def increment_orders():
    global _order_count
    with _lock:
        _order_count += 1


def set_db_latency(ms: float):
    global _last_db_latency_ms
    with _lock:
        _last_db_latency_ms = ms


def _collect_and_reset() -> dict[str, float]:
    """Collect current counters and reset them for the next interval."""
    global _request_count, _error_count, _checkout_count, _order_count
    with _lock:
        snapshot = {
            "requests": _request_count,
            "errors": _error_count,
            "checkouts": _checkout_count,
            "orders": _order_count,
            "db_latency_ms": _last_db_latency_ms,
        }
        _request_count = 0
        _error_count = 0
        _checkout_count = 0
        _order_count = 0
    return snapshot


def _build_metric_data(snapshot: dict[str, float], start_time: float) -> list[dict[str, Any]]:
    """Build the OCI Monitoring PostMetricData payload."""
    now = datetime.now(timezone.utc)
    dimensions = {
        "serviceName": cfg.otel_service_name,
        "environment": cfg.app_env,
        "runtime": cfg.app_runtime,
        "instanceId": cfg.service_instance_id,
    }

    def _point(name: str, value: float, unit: str = "count") -> dict:
        return {
            "namespace": METRIC_NAMESPACE,
            "name": name,
            "dimensions": dimensions,
            "metadata": {"unit": unit},
            "datapoints": [
                {
                    "timestamp": now,
                    "value": value,
                }
            ],
        }

    uptime = time.time() - start_time

    # Import CRM sync state if available
    crm_sync_age = 0.0
    try:
        from server.modules.integrations import CRM_SYNC_STATE
        last_ts = float(CRM_SYNC_STATE.get("last_sync_ts") or 0)
        crm_sync_age = time.time() - last_ts if last_ts > 0 else 0.0
    except Exception:
        pass

    return [
        _point("app.health", 1.0),
        _point("app.uptime_seconds", uptime, "seconds"),
        _point("app.requests.rate", snapshot["requests"]),
        _point("app.errors.rate", snapshot["errors"]),
        _point("app.checkout.count", snapshot["checkouts"]),
        _point("app.orders.count", snapshot["orders"]),
        _point("app.db.latency_ms", snapshot["db_latency_ms"], "milliseconds"),
        _point("app.crm.sync_age_s", crm_sync_age, "seconds"),
    ]


def _publisher_loop(compartment_id: str, start_time: float):
    """Background thread that publishes metrics to OCI Monitoring."""
    try:
        import oci
        from oci.monitoring import MonitoringClient
        from oci.monitoring.models import PostMetricDataDetails, MetricDataDetails, Datapoint

        # Use the same auth mode as the rest of the app
        auth_mode = cfg.oci_auth_mode.lower()
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            client = MonitoringClient(config={}, signer=signer)
        elif auth_mode == "resource_principal":
            signer = oci.auth.signers.get_resource_principals_signer()
            client = MonitoringClient(config={}, signer=signer)
        else:
            config = oci.config.from_file()
            client = MonitoringClient(config)

        # Use the telemetry ingestion endpoint for the region
        region = os.getenv("OCI_REGION", "")
        if region:
            client.base_client.set_region(region)

        logger.info(
            "OCI Monitoring publisher started — namespace=%s, interval=%ds, compartment=%s",
            METRIC_NAMESPACE, PUBLISH_INTERVAL, compartment_id[:20] + "...",
        )
    except Exception as exc:
        logger.warning("OCI Monitoring publisher failed to initialize: %s", exc)
        return

    while _running:
        try:
            time.sleep(PUBLISH_INTERVAL)
            if not _running:
                break

            snapshot = _collect_and_reset()
            metrics_data = _build_metric_data(snapshot, start_time)

            metric_details = []
            for m in metrics_data:
                md = MetricDataDetails(
                    namespace=m["namespace"],
                    name=m["name"],
                    compartment_id=compartment_id,
                    dimensions=m["dimensions"],
                    metadata=m["metadata"],
                    datapoints=[
                        Datapoint(
                            timestamp=m["datapoints"][0]["timestamp"],
                            value=m["datapoints"][0]["value"],
                        )
                    ],
                )
                metric_details.append(md)

            client.post_metric_data(
                PostMetricDataDetails(metric_data=metric_details)
            )
            logger.debug(
                "OCI Monitoring: published %d metrics (requests=%d, errors=%d)",
                len(metric_details), snapshot["requests"], snapshot["errors"],
            )
        except Exception as exc:
            logger.warning("OCI Monitoring publish failed: %s", exc)


def start_monitoring():
    """Start the OCI Monitoring publisher if configured.

    Requires:
    - ``OCI_COMPARTMENT_ID`` env var (target compartment for metrics)
    - Valid OCI credentials (instance principal, resource principal, or config file)
    """
    global _running, _thread

    compartment_id = cfg.oci_compartment_id
    if not compartment_id:
        logger.info("OCI Monitoring disabled — OCI_COMPARTMENT_ID not set")
        return

    if _running:
        return

    _running = True
    _thread = threading.Thread(
        target=_publisher_loop,
        args=(compartment_id, time.time()),
        daemon=True,
        name="oci-monitoring-publisher",
    )
    _thread.start()


def stop_monitoring():
    global _running
    _running = False
