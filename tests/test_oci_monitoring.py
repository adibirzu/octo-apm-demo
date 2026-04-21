from __future__ import annotations

import time

from server.observability import oci_monitoring


def test_collect_and_reset_captures_current_counters() -> None:
    oci_monitoring._request_count = 0
    oci_monitoring._error_count = 0
    oci_monitoring._checkout_count = 0
    oci_monitoring._order_count = 0
    oci_monitoring._last_db_latency_ms = 0.0
    oci_monitoring._low_stock_count = 0

    oci_monitoring.increment_requests()
    oci_monitoring.increment_requests()
    oci_monitoring.increment_errors()
    oci_monitoring.increment_checkouts()
    oci_monitoring.increment_orders()
    oci_monitoring.set_db_latency(42.5)
    oci_monitoring.set_low_stock_count(3)

    snapshot = oci_monitoring._collect_and_reset()

    assert snapshot == {
        "requests": 2,
        "errors": 1,
        "checkouts": 1,
        "orders": 1,
        "db_latency_ms": 42.5,
        "low_stock": 3,
    }
    assert oci_monitoring._request_count == 0
    assert oci_monitoring._error_count == 0
    assert oci_monitoring._checkout_count == 0
    assert oci_monitoring._order_count == 0


def test_build_metric_data_contains_expected_metric_names() -> None:
    snapshot = {
        "requests": 5,
        "errors": 1,
        "checkouts": 2,
        "orders": 4,
        "db_latency_ms": 18.0,
        "low_stock": 7,
    }

    metrics = oci_monitoring._build_metric_data(snapshot, start_time=time.time() - 30)
    metric_names = {metric["name"] for metric in metrics}

    assert metric_names == {
        "app.health",
        "app.uptime_seconds",
        "app.requests.rate",
        "app.errors.rate",
        "app.checkout.count",
        "app.orders.count",
        "app.db.latency_ms",
        "app.crm.sync_age_s",
        "app.inventory.low_stock_products",
    }
    assert all(metric["namespace"] == oci_monitoring.METRIC_NAMESPACE for metric in metrics)


def test_build_metric_data_uses_service_dimensions() -> None:
    metrics = oci_monitoring._build_metric_data(
        {
            "requests": 0,
            "errors": 0,
            "checkouts": 0,
            "orders": 0,
            "db_latency_ms": 0.0,
            "low_stock": 0,
        },
        start_time=time.time() - 5,
    )

    dimensions = metrics[0]["dimensions"]

    assert dimensions["serviceName"] == oci_monitoring.cfg.otel_service_name
    assert dimensions["environment"] == oci_monitoring.cfg.app_env
    assert dimensions["runtime"] == oci_monitoring.cfg.app_runtime
    assert dimensions["instanceId"] == oci_monitoring.cfg.service_instance_id
