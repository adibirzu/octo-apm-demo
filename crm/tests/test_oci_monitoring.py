from __future__ import annotations

import time
from dataclasses import replace

from server.observability import oci_monitoring


def test_collect_and_reset_captures_crm_counters() -> None:
    oci_monitoring._request_count = 0
    oci_monitoring._error_count = 0
    oci_monitoring._order_count = 0
    oci_monitoring._order_sync_count = 0
    oci_monitoring._auth_success_count = 0
    oci_monitoring._auth_failure_count = 0
    oci_monitoring._security_event_count = 0
    oci_monitoring._dashboard_load_count = 0
    oci_monitoring._last_db_latency_ms = 0.0

    oci_monitoring.increment_requests()
    oci_monitoring.increment_errors()
    oci_monitoring.increment_orders()
    oci_monitoring.increment_order_sync()
    oci_monitoring.increment_auth_success()
    oci_monitoring.increment_auth_failure()
    oci_monitoring.increment_security_events()
    oci_monitoring.increment_dashboard_loads()
    oci_monitoring.set_db_latency(25.5)

    snapshot = oci_monitoring._collect_and_reset()

    assert snapshot == {
        "requests": 1,
        "errors": 1,
        "orders": 1,
        "order_sync": 1,
        "auth_success": 1,
        "auth_failure": 1,
        "security_events": 1,
        "dashboard_loads": 1,
        "db_latency_ms": 25.5,
    }
    assert oci_monitoring._request_count == 0
    assert oci_monitoring._order_sync_count == 0


def test_build_metric_data_contains_melts_metric_names() -> None:
    snapshot = {
        "requests": 5,
        "errors": 1,
        "orders": 2,
        "order_sync": 3,
        "auth_success": 4,
        "auth_failure": 1,
        "security_events": 2,
        "dashboard_loads": 7,
        "db_latency_ms": 12.5,
    }

    metrics = oci_monitoring._build_metric_data(snapshot, start_time=time.time() - 30)
    metric_names = {metric["name"] for metric in metrics}

    assert metric_names == {
        "app.health",
        "app.uptime_seconds",
        "app.requests.rate",
        "app.errors.rate",
        "app.orders.count",
        "app.order_sync.count",
        "app.auth.success.count",
        "app.auth.failure.count",
        "app.security.events.count",
        "app.dashboard.loads.count",
        "app.db.latency_ms",
    }
    assert all(metric["namespace"] == "octo_apm_demo" for metric in metrics)


def test_build_metric_data_uses_low_cardinality_dimensions() -> None:
    metrics = oci_monitoring._build_metric_data(
        {
            "requests": 0,
            "errors": 0,
            "orders": 0,
            "order_sync": 0,
            "auth_success": 0,
            "auth_failure": 0,
            "security_events": 0,
            "dashboard_loads": 0,
            "db_latency_ms": 0.0,
        },
        start_time=time.time() - 5,
    )

    dimensions = metrics[0]["dimensions"]

    assert set(dimensions) == {"serviceName", "environment", "runtime", "instanceId"}
    assert dimensions["serviceName"] == oci_monitoring.cfg.otel_service_name


def test_resolve_monitoring_region_prefers_monitoring_override(monkeypatch) -> None:
    monkeypatch.setenv("OCI_MONITORING_REGION", "us-ashburn-1")
    monkeypatch.setenv("OCI_REGION", "eu-frankfurt-1")

    assert oci_monitoring._resolve_monitoring_region() == "us-ashburn-1"


def test_resolve_monitoring_region_prefers_apm_endpoint_over_cluster_region(monkeypatch) -> None:
    monkeypatch.delenv("OCI_MONITORING_REGION", raising=False)
    monkeypatch.setenv("OCI_REGION", "eu-frankfurt-1")
    monkeypatch.setattr(
        oci_monitoring,
        "cfg",
        replace(
            oci_monitoring.cfg,
            oci_apm_endpoint="https://example.apm-agt.us-phoenix-1.oci.oraclecloud.com",
        ),
    )

    assert oci_monitoring._resolve_monitoring_region() == "us-phoenix-1"
