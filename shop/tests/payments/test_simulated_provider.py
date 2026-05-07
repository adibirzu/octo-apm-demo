"""Simulated payment provider and observability metadata tests."""

from __future__ import annotations

from server.modules.payments.simulated_provider import SimulatedPaymentProvider


def test_simulated_provider_approves_normal_payment() -> None:
    provider = SimulatedPaymentProvider(mode="approve", fixed_latency_ms=25)

    intent = provider.create_intent(
        amount_minor_units=12999,
        currency="usd",
        order_id=42,
        customer_email="buyer@example.invalid",
    )
    decision = provider.decide(
        amount_minor_units=12999,
        currency="usd",
        order_id=42,
        customer_email="buyer@example.invalid",
    )

    assert intent.provider == "simulated"
    assert intent.provider_reference.startswith("sim_42_")
    assert decision.status == "authorized"
    assert decision.risk_score < 50
    assert decision.latency_ms == 25
    assert decision.observability_fields()["payment.provider"] == "simulated"


def test_simulated_provider_can_force_declines_for_demo() -> None:
    provider = SimulatedPaymentProvider(mode="decline")

    decision = provider.decide(
        amount_minor_units=9999,
        currency="usd",
        order_id=99,
        customer_email="buyer@example.invalid",
    )

    assert decision.status == "declined"
    assert decision.error_code == "SIM_DECLINED"
    assert decision.risk_score >= 80
