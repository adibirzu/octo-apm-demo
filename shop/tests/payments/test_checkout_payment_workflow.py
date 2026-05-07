"""Checkout payment workflow tests.

The storefront may collect raw card data for the simulator, but the backend
must only persist/log tokenized or masked payment metadata.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.modules.payment_gateway_simulation import authorize_simulated_payment
from server.modules.payments import checkout_workflow


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self) -> None:
        self.inserts: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        if "INSERT INTO payment_transactions" in str(statement):
            self.inserts.append(dict(params or {}))
        return _Rows()


def test_card_payment_context_detects_network_and_never_exposes_pan_or_cvv() -> None:
    context = checkout_workflow.build_payment_context(
        payment_method="credit_card",
        payment_details={
            "card": {
                "number": "4111 1111 1111 1111",
                "expiry": "12/30",
                "cvv": "123",
                "cardholder_name": "Alex Buyer",
                "billing_postal_code": "10001",
            }
        },
        amount_minor_units=129900,
        customer_email="alex@example.invalid",
    )

    assert context.method == "credit_card"
    assert context.provider == "simulated-visa"
    assert context.card_brand == "visa"
    assert context.card_last4 == "1111"
    assert context.card_exp_month == 12
    assert context.card_exp_year == 2030
    assert "invalid_luhn" not in context.risk_reasons

    safe_text = str(context.safe_fields())
    assert "4111111111111111" not in safe_text
    assert "4111 1111 1111 1111" not in safe_text
    assert "123" not in safe_text


def test_wallet_payment_context_hashes_raw_google_pay_token() -> None:
    context = checkout_workflow.build_payment_context(
        payment_method="google_pay",
        payment_details={
            "wallet": {
                "provider": "google_pay",
                "token": "raw-google-pay-token-from-client",
                "network": "MASTERCARD",
                "display_name": "Google Pay Mastercard",
            }
        },
        amount_minor_units=449900,
        customer_email="maya@example.invalid",
    )

    assert context.method == "google_pay"
    assert context.provider == "simulated-google-pay"
    assert context.wallet_type == "google_pay"
    assert context.card_brand == "mastercard"
    assert context.wallet_token_hash
    assert "raw-google-pay-token-from-client" not in str(context.safe_fields())


def test_high_risk_card_declines_and_persists_only_safe_metadata(monkeypatch) -> None:
    db = _FakeDb()

    async def _java_disabled(*args, **kwargs):
        return {"status": "disabled"}

    class _Client:
        async def verify_payment(self, **kwargs):
            return await _java_disabled(**kwargs)

        async def authorize_payment(self, **kwargs):
            return await _java_disabled(**kwargs)

    monkeypatch.setattr("server.modules.payment_gateway_simulation.JavaAppServerClient", _Client)
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.business_metrics.record_payment_authorization",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.cfg.payment_gateway_simulation_enabled",
        True,
    )

    result = asyncio.run(
        authorize_simulated_payment(
            order_id=77,
            total=1250.0,
            currency="usd",
            customer_email="buyer@example.invalid",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440000",
            payment_method="credit_card",
            payment_details={
                "card": {
                    "number": "4111 1111 1111 1112",
                    "expiry": "01/20",
                    "cvv": "12",
                    "cardholder_name": "Alex Buyer",
                }
            },
            db=db,
        )
    )

    assert result["status"] == "declined"
    assert result["provider"] == "simulated-visa"
    assert result["payment_gateway"]["gateway"] == "octo-payment-gateway-emulator"
    assert result["payment_gateway"]["final_step"]["name"] == "merchant_authorization_result"
    assert result["payment_gateway"]["verification"]["status"] == "disabled"
    assert any(
        step["name"] == "gateway_card_tokenization"
        for step in result["payment_gateway"]["steps"]
    )
    assert any(
        step["name"] == "verification_antifraud_request"
        for step in result["payment_gateway"]["steps"]
    )
    assert {"invalid_luhn", "expired_card", "invalid_cvv"}.issubset(set(result["risk_reasons"]))
    assert db.inserts
    persisted = db.inserts[-1]
    assert persisted["order_id"] == 77
    assert persisted["provider"] == "simulated-visa"
    assert persisted["card_last4"] == "1112"
    assert persisted["card_exp_month"] == 1
    assert persisted["card_exp_year"] == 2020
    persisted_text = str(persisted)
    assert "4111111111111112" not in persisted_text
    assert "4111 1111 1111 1112" not in persisted_text
    assert "'12'" not in persisted_text


def test_decline_test_card_is_rejected_by_antifraud_verification(monkeypatch) -> None:
    db = _FakeDb()

    class _Client:
        async def verify_payment(self, **kwargs):
            return {
                "status": "ok",
                "data": {
                    "verification_provider": "octo-antifraud-verification-app",
                    "decision": "declined",
                    "risk_score": 95,
                    "error_code": "ANTIFRAUD_DECLINED",
                    "latency_ms": 44,
                },
                "latency_ms": 44,
            }

        async def authorize_payment(self, **kwargs):
            return {
                "status": "ok",
                "data": {
                    "decision": "approved",
                    "risk_score": 12,
                    "latency_ms": 37,
                    "authorization_code": "SIM-OK",
                },
                "latency_ms": 37,
            }

    monkeypatch.setattr("server.modules.payment_gateway_simulation.JavaAppServerClient", _Client)
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.business_metrics.record_payment_authorization",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.cfg.payment_gateway_simulation_enabled",
        True,
    )

    result = asyncio.run(
        authorize_simulated_payment(
            order_id=88,
            total=250.0,
            currency="usd",
            customer_email="buyer@example.invalid",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440088",
            payment_method="credit_card",
            payment_details={
                "card": {
                    "number": "4000000000000002",
                    "expiry": "12/30",
                    "cvv": "123",
                    "cardholder_name": "Alex Buyer",
                }
            },
            db=db,
        )
    )

    assert result["status"] == "declined"
    assert result["decision_source"] == "java-antifraud-verification-app"
    assert result["error_code"] == "ANTIFRAUD_DECLINED"
    assert "issuer_decline_test_card" in result["risk_reasons"]
    assert result["payment_gateway"]["verification"]["decision"] == "declined"
    assert result["payment_gateway"]["final_step"]["status"] == "declined"
