from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.modules import observability_dashboard
from server.modules.observability_dashboard import _customer_observability_dashboard


def _customer_demo_payload() -> dict:
    return _customer_observability_dashboard(
        app_health={
            "entities": {
                "customers": 18,
                "orders": 42,
                "products": 12,
                "tickets": 3,
            },
            "activity": {
                "orders_24h": 5,
                "open_tickets": 2,
                "total_revenue": 12345.67,
            },
        },
        db_health={
            "status": "connected",
            "latency_ms": 12.4,
            "atp_ocid": "ocid1.autonomousdatabase.oc1.example",
            "connection_name": "octoatp_low",
            "pool": {"size": 4, "max_overflow": 8},
        },
        integration_health={
            "drone_shop": {
                "configured": True,
                "source_name": "backend.internal.example",
            },
        },
        security={
            "audit": {"entries_24h": 4},
            "waf": {
                "detection_enabled": True,
                "header_monitoring": ["x-oci-waf-score"],
            },
            "owasp_coverage": ["A01", "A03"],
        },
        order_sync={
            "enabled": True,
            "source": "internal-sync",
            "stats": {
                "total_sync_operations": 20,
                "successful": 19,
                "failed": 1,
                "success_rate_pct": 95.0,
            },
            "orders": {
                "backlog": 1,
            },
        },
        pillars={
            "apm": {"configured": True, "rum_configured": True},
            "logging": {"configured": True},
            "metrics": {"configured": True},
            "data_insights": {"configured": True},
        },
    )


def test_customer_demo_payload_uses_live_business_data_without_raw_backend_details() -> None:
    payload = _customer_demo_payload()

    assert payload["demo"]["badge"] == "Demo project"
    assert "OCI Observability" in payload["demo"]["name"]
    assert payload["scorecards"][0]["value"] == 18
    assert payload["scorecards"][2]["value"] == 12345.67
    assert payload["service_health"]["data_service"]["status"] == "Available"

    payload_text = str(payload).lower()
    blocked_terms = [
        "ocid1.",
        "trace_id",
        "traceparent",
        "octoatp",
        "connection_name",
        "max_overflow",
        "x-oci",
        "backend.internal",
        "internal-sync",
    ]
    for term in blocked_terms:
        assert term not in payload_text


def test_customer_demo_preserves_zero_success_rate() -> None:
    payload = _customer_observability_dashboard(
        app_health={"entities": {}, "activity": {}},
        db_health={"status": "connected", "latency_ms": 9},
        integration_health={"drone_shop": {"configured": True}},
        security={"audit": {}, "waf": {}, "owasp_coverage": []},
        order_sync={
            "enabled": True,
            "stats": {
                "total_sync_operations": 2,
                "successful": 0,
                "failed": 2,
                "success_rate_pct": 0.0,
            },
            "orders": {},
        },
        pillars={},
    )

    experience_card = next(item for item in payload["scorecards"] if item["id"] == "experience")
    assert experience_card["value"] == 0.0
    assert experience_card["tone"] == "danger"
    assert payload["hero"]["status"] == "Watch"


def test_observability_template_is_customer_friendly() -> None:
    root = Path(__file__).parents[1]
    template = (root / "server/templates/observability.html").read_text()

    assert "OCI Observability Demo" in template
    assert "Demo project" in template
    assert "Live customer data" in template

    template_text = template.lower()
    blocked_terms = [
        "trace_id",
        "traceparent",
        "ocid",
        "pool size",
        "client_identifier",
        "waf headers",
        "db management",
        "opsi",
    ]
    for term in blocked_terms:
        assert term not in template_text


def test_base_template_does_not_publish_database_connection_context() -> None:
    root = Path(__file__).parents[1]
    base_template = (root / "server/templates/base.html").read_text()
    rum_script = (root / "server/static/js/rum-advanced.js").read_text()

    assert "OCI Observability demo project" in base_template
    assert "atpConnectionName" not in base_template
    assert "atp_connection_name" not in rum_script


def test_observability_360_endpoint_returns_customer_demo_contract(monkeypatch) -> None:
    async def app_health() -> dict:
        return {
            "entities": {"customers": 1, "orders": 2, "products": 3, "tickets": 4},
            "activity": {"orders_24h": 1, "open_tickets": 0, "total_revenue": 99.0},
        }

    async def db_health() -> dict:
        return {
            "status": "connected",
            "latency_ms": 8,
            "atp_ocid": "ocid1.autonomousdatabase.oc1.example",
            "connection_name": "octoatp_low",
        }

    async def integration_health() -> dict:
        return {"drone_shop": {"configured": True, "source_name": "backend.internal.example"}}

    async def security() -> dict:
        return {
            "audit": {"entries_24h": 1},
            "waf": {"detection_enabled": True, "header_monitoring": ["x-oci-waf-score"]},
            "owasp_coverage": ["A01"],
        }

    async def order_sync() -> dict:
        return {
            "enabled": True,
            "source": "internal-sync",
            "stats": {
                "total_sync_operations": 2,
                "successful": 2,
                "failed": 0,
                "success_rate_pct": 100.0,
            },
            "orders": {"backlog": 0},
        }

    monkeypatch.setattr(observability_dashboard, "_app_health_summary", app_health)
    monkeypatch.setattr(observability_dashboard, "_db_health_summary", db_health)
    monkeypatch.setattr(observability_dashboard, "_integration_health_summary", integration_health)
    monkeypatch.setattr(observability_dashboard, "_security_summary", security)
    monkeypatch.setattr(observability_dashboard, "_order_sync_health", order_sync)
    monkeypatch.setattr(observability_dashboard, "push_log", lambda *args, **kwargs: None)

    app = FastAPI()
    app.include_router(observability_dashboard.router)
    response = TestClient(app).get("/api/observability/360")

    assert response.status_code == 200
    payload = response.json()
    assert payload["demo"]["badge"] == "Demo project"
    assert payload["scorecards"][0]["value"] == 1
    assert "service_health" in payload
    assert "correlation" not in payload
    assert "pillars" not in payload

    payload_text = response.text.lower()
    assert "ocid1." not in payload_text
    assert "traceparent" not in payload_text
    assert "connection_name" not in payload_text
    assert "backend.internal" not in payload_text
    assert "x-oci" not in payload_text
