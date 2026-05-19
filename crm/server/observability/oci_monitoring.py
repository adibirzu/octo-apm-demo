"""OCI Monitoring publisher for CRM custom MELTS metrics.

The OpenTelemetry metrics endpoint is useful for local scraping, but the OCI
demo dashboards need first-class OCI Monitoring samples. This publisher mirrors
the Shop app's low-cardinality custom metrics and posts them through the
Monitoring ingestion endpoint using the same instance principal auth mode as
OCI Logging.
"""

from __future__ import annotations

import logging
import os
import re
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
_order_count = 0
_order_sync_count = 0
_auth_success_count = 0
_auth_failure_count = 0
_security_event_count = 0
_dashboard_load_count = 0
_last_db_latency_ms = 0.0
_lock = threading.Lock()

PUBLISH_INTERVAL = int(os.getenv("OCI_MONITORING_INTERVAL_SECONDS", "60"))
METRIC_NAMESPACE = os.getenv("OCI_MONITORING_NAMESPACE", "octo_apm_demo")


def increment_requests() -> None:
    global _request_count
    with _lock:
        _request_count += 1


def increment_errors() -> None:
    global _error_count
    with _lock:
        _error_count += 1


def increment_orders() -> None:
    global _order_count
    with _lock:
        _order_count += 1


def increment_order_sync() -> None:
    global _order_sync_count
    with _lock:
        _order_sync_count += 1


def increment_auth_success() -> None:
    global _auth_success_count
    with _lock:
        _auth_success_count += 1


def increment_auth_failure() -> None:
    global _auth_failure_count
    with _lock:
        _auth_failure_count += 1


def increment_security_events() -> None:
    global _security_event_count
    with _lock:
        _security_event_count += 1


def increment_dashboard_loads() -> None:
    global _dashboard_load_count
    with _lock:
        _dashboard_load_count += 1


def set_db_latency(ms: float) -> None:
    global _last_db_latency_ms
    with _lock:
        _last_db_latency_ms = ms


def _collect_and_reset() -> dict[str, float]:
    """Collect current interval counters and reset rate-like values."""
    global _request_count, _error_count, _order_count, _order_sync_count
    global _auth_success_count, _auth_failure_count, _security_event_count, _dashboard_load_count
    with _lock:
        snapshot = {
            "requests": _request_count,
            "errors": _error_count,
            "orders": _order_count,
            "order_sync": _order_sync_count,
            "auth_success": _auth_success_count,
            "auth_failure": _auth_failure_count,
            "security_events": _security_event_count,
            "dashboard_loads": _dashboard_load_count,
            "db_latency_ms": _last_db_latency_ms,
        }
        _request_count = 0
        _error_count = 0
        _order_count = 0
        _order_sync_count = 0
        _auth_success_count = 0
        _auth_failure_count = 0
        _security_event_count = 0
        _dashboard_load_count = 0
    return snapshot


def _build_metric_data(snapshot: dict[str, float], start_time: float) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    dimensions = {
        "serviceName": cfg.otel_service_name,
        "environment": cfg.app_env,
        "runtime": cfg.app_runtime,
        "instanceId": cfg.service_instance_id,
    }

    def _point(name: str, value: float, unit: str = "count") -> dict[str, Any]:
        return {
            "namespace": METRIC_NAMESPACE,
            "name": name,
            "dimensions": dimensions,
            "metadata": {"unit": unit},
            "datapoints": [{"timestamp": now, "value": value}],
        }

    uptime = time.time() - start_time
    return [
        _point("app.health", 1.0),
        _point("app.uptime_seconds", uptime, "seconds"),
        _point("app.requests.rate", snapshot["requests"]),
        _point("app.errors.rate", snapshot["errors"]),
        _point("app.orders.count", snapshot["orders"]),
        _point("app.order_sync.count", snapshot["order_sync"]),
        _point("app.auth.success.count", snapshot["auth_success"]),
        _point("app.auth.failure.count", snapshot["auth_failure"]),
        _point("app.security.events.count", snapshot["security_events"]),
        _point("app.dashboard.loads.count", snapshot["dashboard_loads"]),
        _point("app.db.latency_ms", snapshot["db_latency_ms"], "milliseconds"),
    ]


def _resolve_monitoring_region() -> str:
    explicit = (os.getenv("OCI_MONITORING_REGION") or "").strip().lower()
    if explicit:
        return explicit
    endpoint = (cfg.oci_apm_endpoint or "").strip().lower()
    match = re.search(r"\.([a-z]+-[a-z]+-\d+)\.oci", endpoint)
    if match:
        return match.group(1)
    explicit = (os.getenv("OCI_REGION") or os.getenv("OCI_REGION_ID") or "").strip().lower()
    if explicit:
        return explicit
    return "us-phoenix-1"


def _publisher_loop(compartment_id: str, start_time: float) -> None:
    try:
        import oci
        from oci.monitoring import MonitoringClient
        from oci.monitoring.models import Datapoint, MetricDataDetails, PostMetricDataDetails

        region = _resolve_monitoring_region()
        ingestion_endpoint = f"https://telemetry-ingestion.{region}.oraclecloud.com"
        auth_mode = cfg.oci_auth_mode.lower()
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            client = MonitoringClient(config={}, signer=signer, service_endpoint=ingestion_endpoint)
        elif auth_mode == "resource_principal":
            signer = oci.auth.signers.get_resource_principals_signer()
            client = MonitoringClient(config={}, signer=signer, service_endpoint=ingestion_endpoint)
        else:
            config = oci.config.from_file()
            client = MonitoringClient(config, service_endpoint=ingestion_endpoint)
        logger.info(
            "OCI Monitoring publisher started - namespace=%s interval=%ds region=%s compartment=%s",
            METRIC_NAMESPACE,
            PUBLISH_INTERVAL,
            region,
            compartment_id[:20] + "...",
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
            metric_details = []
            for metric in _build_metric_data(snapshot, start_time):
                metric_details.append(
                    MetricDataDetails(
                        namespace=metric["namespace"],
                        name=metric["name"],
                        compartment_id=compartment_id,
                        dimensions=metric["dimensions"],
                        metadata=metric["metadata"],
                        datapoints=[
                            Datapoint(
                                timestamp=metric["datapoints"][0]["timestamp"],
                                value=metric["datapoints"][0]["value"],
                            )
                        ],
                    )
                )
            response = client.post_metric_data(PostMetricDataDetails(metric_data=metric_details))
            failed = getattr(response.data, "failed_metrics_count", 0) or 0
            if failed:
                logger.warning("OCI Monitoring partial failure: %d/%d metrics rejected", failed, len(metric_details))
        except Exception as exc:
            logger.warning("OCI Monitoring publish failed: %s", exc)


def start_monitoring() -> None:
    global _running, _thread
    compartment_id = cfg.oci_compartment_id
    if not compartment_id:
        logger.info("OCI Monitoring disabled - OCI_COMPARTMENT_ID not set")
        return
    if _running:
        return
    _running = True
    _thread = threading.Thread(
        target=_publisher_loop,
        args=(compartment_id, time.time()),
        daemon=True,
        name="crm-oci-monitoring-publisher",
    )
    _thread.start()


def stop_monitoring() -> None:
    global _running
    _running = False


# ---------------------------------------------------------------------------
# Plan 07-05 / D-17 — bounded stress-run counter
# ---------------------------------------------------------------------------
#
# `octo_apm_demo/stress_run_count` is the one custom counter that carries the
# `run_id` dimension end-to-end. Cardinality is bounded by the concurrency=1
# guard in the stress-runner pod plus the operator-window duty cycle, so a
# per-point `run_id` dimension is safe here. Do NOT propagate run_id to the
# long-lived gauges in this module — keep it on this counter only
# (RESEARCH §Anti-Pattern §2).

def increment_stress_run(run_id: str, status: str) -> None:
    """Increment octo_apm_demo/stress_run_count by 1, tagged with run_id+status.

    Safe to call from any FastAPI handler — failures are logged at WARNING and
    swallowed so the audit emission never blocks the admin endpoint.
    """
    compartment_id = cfg.oci_compartment_id
    if not compartment_id:
        logger.info(
            "OCI Monitoring increment_stress_run skipped - OCI_COMPARTMENT_ID not set"
        )
        return
    try:
        import oci
        from oci.monitoring import MonitoringClient
        from oci.monitoring.models import (
            Datapoint,
            MetricDataDetails,
            PostMetricDataDetails,
        )

        region = _resolve_monitoring_region()
        ingestion_endpoint = f"https://telemetry-ingestion.{region}.oraclecloud.com"
        auth_mode = cfg.oci_auth_mode.lower()
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            client = MonitoringClient(
                config={}, signer=signer, service_endpoint=ingestion_endpoint
            )
        elif auth_mode == "resource_principal":
            signer = oci.auth.signers.get_resource_principals_signer()
            client = MonitoringClient(
                config={}, signer=signer, service_endpoint=ingestion_endpoint
            )
        else:
            config = oci.config.from_file()
            client = MonitoringClient(config, service_endpoint=ingestion_endpoint)

        now = datetime.now(timezone.utc)
        dimensions = {
            "serviceName": cfg.otel_service_name,
            "environment": cfg.app_env,
            "run_id": str(run_id),
            "status": str(status),
        }
        md = MetricDataDetails(
            namespace=METRIC_NAMESPACE,
            name="stress_run_count",
            compartment_id=compartment_id,
            dimensions=dimensions,
            metadata={"unit": "count"},
            datapoints=[Datapoint(timestamp=now, value=1.0)],
        )
        response = client.post_metric_data(
            PostMetricDataDetails(metric_data=[md])
        )
        failed = getattr(response.data, "failed_metrics_count", 0) or 0
        if failed:
            logger.warning(
                "OCI Monitoring increment_stress_run partial failure: 1 metric rejected"
            )
    except Exception as exc:
        logger.warning("OCI Monitoring increment_stress_run failed: %s", exc)
