"""Payment gateway observability API helpers."""

from __future__ import annotations

import json
import asyncio
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth_security import cfg as auth_cfg
from server.modules import observability_dashboard as dashboard_module
from server.modules.observability_dashboard import (
    _payment_gateway_events,
    _payment_gateway_event_summary,
    _safe_filter_value,
    _serialize_payment_gateway_event,
    _scrub_gateway_metadata,
)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Rows":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.params: dict[str, Any] = {}

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        self.params = dict(params or {})
        return _Rows(self.rows)


def test_payment_gateway_event_endpoint_returns_trace_drilldown_for_internal_service(monkeypatch) -> None:
    row = {
        "id": 1,
        "order_id": 42,
        "gateway_name": "octo-payment-gateway-emulator",
        "gateway_provider": "cybersource-compatible-simulator",
        "gateway_request_id": "pgw-42-test",
        "payment_method": "apple_pay",
        "wallet_type": "apple_pay",
        "card_brand": "visa",
        "card_last4": "0002",
        "payment_network": "network-token",
        "step_name": "merchant_authorization_result",
        "step_phase": "merchant_response",
        "step_status": "declined",
        "step_index": 11,
        "latency_ms": 2.1,
        "trace_id": "f" * 32,
        "span_id": "e" * 16,
        "metadata_json": "{}",
        "created_at": datetime(2026, 5, 7, 13, 0, 0),
        "order_status": "payment_pending",
        "order_payment_status": "failed",
        "order_payment_required": 1,
        "order_payment_provider_reference": "pi_declined",
        "order_payment_paid_at": None,
    }
    fake_session = _FakeSession([row])
    monkeypatch.setattr(auth_cfg, "internal_service_key", "shared-key")
    monkeypatch.setattr(dashboard_module, "AsyncSessionLocal", lambda: fake_session)

    app = FastAPI()
    app.include_router(dashboard_module.router)
    response = TestClient(app).get(
        "/api/observability/payment-gateway/events?gateway_request_id=pgw-42-test",
        headers={"X-Internal-Service-Key": "shared-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert fake_session.params["gateway_request_id"] == "pgw-42-test"
    assert body["summary"]["event_count"] == 1
    assert body["summary"]["gateway_request_ids"] == ["pgw-42-test"]
    assert body["events"][0]["step"]["name"] == "merchant_authorization_result"
    assert body["events"][0]["order"]["payment_required"] is True


def test_payment_gateway_event_query_uses_null_filters_for_oracle_empty_strings(monkeypatch) -> None:
    fake_session = _FakeSession([])
    monkeypatch.setattr(dashboard_module, "AsyncSessionLocal", lambda: fake_session)

    events = asyncio.run(
        _payment_gateway_events(order_id=0, trace_id="", gateway_request_id="", limit=3)
    )

    assert events == []
    assert fake_session.params["trace_id"] is None
    assert fake_session.params["gateway_request_id"] is None


def test_payment_gateway_event_serializer_is_token_safe() -> None:
    event = _serialize_payment_gateway_event(
        {
            "id": 17,
            "order_id": 91,
            "gateway_name": "octo-payment-gateway-emulator",
            "gateway_provider": "cybersource-compatible-simulator",
            "gateway_request_id": "pgw-91-test",
            "payment_method": "google_pay",
            "wallet_type": "google_pay",
            "card_brand": "mastercard",
            "card_last4": "5100",
            "payment_network": "network-token",
            "step_name": "verification_antifraud_response",
            "step_phase": "verification",
            "step_status": "completed",
            "step_index": 7,
            "latency_ms": 12.345,
            "trace_id": "1" * 32,
            "span_id": "2" * 16,
            "metadata_json": json.dumps(
                {
                    "payment.wallet.token_hash": "hash-ok",
                    "payment.card.pan": "4111111111111111",
                    "payment.card.cvv": "123",
                    "payment.processor.authorization_code": "SIM-OK",
                    "nested": {"raw_token": "secret", "risk_score": 15},
                }
            ),
            "created_at": datetime(2026, 5, 7, 12, 0, 0),
            "order_status": "paid",
            "order_payment_status": "paid",
            "order_payment_required": 0,
            "order_payment_provider_reference": "pi_test",
            "order_payment_paid_at": datetime(2026, 5, 7, 12, 0, 1),
        }
    )

    assert event["gateway"]["request_id"] == "pgw-91-test"
    assert event["payment"]["method"] == "google_pay"
    assert event["step"]["latency_ms"] == 12.35
    assert event["order"]["payment_required"] is False
    assert event["created_at"] == "2026-05-07T12:00:00"

    serialized = str(event)
    assert "hash-ok" in serialized
    assert "4111111111111111" not in serialized
    assert "'123'" not in serialized
    assert "SIM-OK" not in serialized
    assert "secret" not in serialized


def test_payment_gateway_event_summary_keeps_gateway_correlation_keys() -> None:
    events = [
        {
            "order_id": 12,
            "gateway": {"request_id": "pgw-12-test"},
            "trace": {"trace_id": "a" * 32},
            "payment": {"method": "apple_pay"},
            "step": {"name": "merchant_authorization_result", "status": "completed", "index": 3},
        },
        {
            "order_id": 12,
            "gateway": {"request_id": "pgw-12-test"},
            "trace": {"trace_id": "a" * 32},
            "payment": {"method": "apple_pay"},
            "step": {"name": "gateway_payment_received", "status": "completed", "index": 1},
        },
    ]

    summary = _payment_gateway_event_summary(events)

    assert summary["event_count"] == 2
    assert summary["order_ids"] == [12]
    assert summary["gateway_request_ids"] == ["pgw-12-test"]
    assert summary["trace_ids"] == ["a" * 32]
    assert summary["methods"] == ["apple_pay"]
    assert summary["step_names"] == ["gateway_payment_received", "merchant_authorization_result"]


def test_payment_gateway_metadata_scrubber_handles_invalid_json_and_filter_safety() -> None:
    assert _scrub_gateway_metadata("{bad") == {"metadata_parse_error": "invalid_json"}
    assert _safe_filter_value("pgw-1; DROP TABLE orders", 32) == "pgw-1DROPTABLEorders"
