"""Payment gateway simulation orchestration.

This module keeps payment simulator details out of the checkout route while
emitting attributes that are useful in APM, Log Analytics, and Monitoring:
provider, decision, risk score, amount bucket, latency, and the downstream Java
sidecar outcome.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from opentelemetry import trace

from server.config import cfg
from server.modules.java_app_server import JavaAppServerClient
from server.modules.payments.checkout_workflow import (
    PaymentContext,
    build_payment_context,
    persist_payment_transaction,
)
from server.modules.payments.gateway_emulator import (
    emit_final_gateway_decision,
    emulate_payment_gateway_authorization,
    persist_payment_gateway_events,
)
from server.modules.payments.simulated_provider import SimulatedPaymentDecision, SimulatedPaymentProvider
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer


def _amount_bucket(amount_minor_units: int) -> str:
    if amount_minor_units < 10_000:
        return "lt_100"
    if amount_minor_units < 100_000:
        return "100_999"
    if amount_minor_units < 1_000_000:
        return "1k_9k"
    return "gte_10k"


def _merge_java_decision(
    local: SimulatedPaymentDecision,
    java_result: dict[str, Any],
) -> SimulatedPaymentDecision:
    if java_result.get("status") != "ok":
        return local
    data = java_result.get("data") or {}
    decision = str(data.get("decision") or "").lower()
    if decision not in {"approved", "declined", "timeout"}:
        return local
    status = "authorized" if decision == "approved" else decision
    return SimulatedPaymentDecision(
        provider_reference=local.provider_reference,
        status=status,
        risk_score=int(data.get("risk_score") or local.risk_score),
        latency_ms=int(data.get("latency_ms") or local.latency_ms),
        amount_minor_units=local.amount_minor_units,
        currency=local.currency,
        error_code=str(data.get("error_code") or local.error_code),
        decision_source="java-app-server",
    )


def _apply_antifraud_decision(
    decision: SimulatedPaymentDecision,
    context: PaymentContext,
) -> SimulatedPaymentDecision:
    risk_score = max(int(decision.risk_score), int(context.risk_score))
    if not context.should_decline and decision.status == "authorized":
        return SimulatedPaymentDecision(
            provider_reference=decision.provider_reference,
            status=decision.status,
            risk_score=risk_score,
            latency_ms=decision.latency_ms,
            amount_minor_units=decision.amount_minor_units,
            currency=decision.currency,
            error_code=decision.error_code,
            decision_source=decision.decision_source,
        )

    if context.should_decline:
        return SimulatedPaymentDecision(
            provider_reference=decision.provider_reference,
            status="declined",
            risk_score=risk_score,
            latency_ms=decision.latency_ms,
            amount_minor_units=decision.amount_minor_units,
            currency=decision.currency,
            error_code="ANTIFRAUD_DECLINED",
            decision_source="internal-antifraud",
        )
    return SimulatedPaymentDecision(
        provider_reference=decision.provider_reference,
        status=decision.status,
        risk_score=risk_score,
        latency_ms=decision.latency_ms,
        amount_minor_units=decision.amount_minor_units,
        currency=decision.currency,
        error_code=decision.error_code,
        decision_source=decision.decision_source,
    )


async def authorize_simulated_payment(
    *,
    order_id: int,
    total: float,
    currency: str,
    customer_email: str,
    checkout_idempotency_key: str = "",
    payment_method: str = "credit_card",
    payment_details: dict[str, Any] | None = None,
    db=None,
) -> dict[str, Any]:
    if not cfg.payment_gateway_simulation_enabled:
        business_metrics.record_payment_authorization(
            status="skipped",
            provider="simulated",
            source="shop_checkout",
        )
        return {"status": "skipped", "reason": "PAYMENT_GATEWAY_SIMULATION_ENABLED=false"}

    amount_minor_units = int(round(float(total) * 100))
    idempotency_key_hash = (
        sha256(checkout_idempotency_key.encode("utf-8")).hexdigest()[:16]
        if checkout_idempotency_key
        else ""
    )
    payment_context = build_payment_context(
        payment_method=payment_method,
        payment_details=payment_details,
        amount_minor_units=amount_minor_units,
        customer_email=customer_email,
    )
    provider = SimulatedPaymentProvider()
    intent = provider.create_intent(
        amount_minor_units=amount_minor_units,
        currency=currency,
        order_id=order_id,
        customer_email=customer_email,
    )
    decision = provider.decide(
        amount_minor_units=amount_minor_units,
        currency=currency,
        order_id=order_id,
        customer_email=customer_email,
    )

    tracer = get_tracer()
    with tracer.start_as_current_span("payment.simulated.authorize") as span:
        apply_span_attributes(
            span,
            {
                "payment.provider": intent.provider,
                "payment.provider_reference": intent.provider_reference,
                "payment.gateway": payment_context.provider,
                "payment.method": payment_context.method,
                "payment.amount_minor_units": amount_minor_units,
                "payment.amount_bucket": _amount_bucket(amount_minor_units),
                "payment.currency": currency,
                "orders.order_id": order_id,
                **payment_context.safe_fields(),
            },
        )
        gateway_result = await emulate_payment_gateway_authorization(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            customer_email=customer_email,
            idempotency_key_hash=idempotency_key_hash,
            context=payment_context,
            intent_provider_reference=intent.provider_reference,
            java_client=JavaAppServerClient(),
        )
        java_result = gateway_result.java_result
        decision = _merge_java_decision(decision, java_result)
        decision = _apply_antifraud_decision(decision, payment_context)
        final_gateway_step = await emit_final_gateway_decision(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            context=payment_context,
            gateway_result=gateway_result,
            decision=decision,
        )
        fields = decision.observability_fields()
        apply_span_attributes(
            span,
            {
                **fields,
                **payment_context.safe_fields(),
                "payment.gateway.name": gateway_result.response_fields()["gateway"],
                "payment.gateway.provider": gateway_result.gateway_provider,
                "payment.gateway.request_id": gateway_result.gateway_request_id,
                "payment.gateway.step_count": len(gateway_result.steps) + 1,
                "payment.network": gateway_result.payment_network,
            },
        )
        span.set_attribute("payment.java_app_server.status", java_result.get("status", "unknown"))
        if decision.status != "authorized":
            span.set_attribute("otel.status_code", "ERROR")
        business_metrics.record_payment_authorization(
            status=decision.status,
            provider=payment_context.provider,
            source="shop_checkout",
            risk_score=decision.risk_score,
        )
        trace_id = (
            format(trace.get_current_span().get_span_context().trace_id, "032x")
            if trace.get_current_span().get_span_context().is_valid
            else ""
        )
        await persist_payment_transaction(
            db,
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            context=payment_context,
            status=decision.status,
            provider_reference=intent.provider_reference,
            gateway_latency_ms=decision.latency_ms,
            decision_source=decision.decision_source,
            error_code=decision.error_code,
            trace_id=trace_id,
        )
        await persist_payment_gateway_events(
            db,
            order_id=order_id,
            context=payment_context,
            gateway_result=gateway_result,
            final_step=final_gateway_step,
        )
        push_log(
            "INFO" if decision.status == "authorized" else "WARNING",
            "Simulated payment gateway decision",
            **{
                **fields,
                **payment_context.safe_fields(),
                "payment.amount_bucket": _amount_bucket(amount_minor_units),
                "payment.java_app_server.status": java_result.get("status", "unknown"),
                "payment.gateway.name": gateway_result.response_fields()["gateway"],
                "payment.gateway.provider": gateway_result.gateway_provider,
                "payment.gateway.request_id": gateway_result.gateway_request_id,
                "payment.gateway.step_count": len(gateway_result.steps) + 1,
                "payment.network": gateway_result.payment_network,
                "orders.order_id": order_id,
            },
        )
        return {
            "status": decision.status,
            "provider": payment_context.provider,
            "provider_reference": intent.provider_reference,
            "method": payment_context.method,
            "card_brand": payment_context.card_brand,
            "card_last4": payment_context.card_last4,
            "wallet_type": payment_context.wallet_type,
            "risk_score": decision.risk_score,
            "risk_reasons": list(payment_context.risk_reasons),
            "latency_ms": decision.latency_ms,
            "error_code": decision.error_code,
            "decision_source": decision.decision_source,
            "java_app_server": java_result,
            "payment_gateway": gateway_result.response_fields()
            | {"final_step": final_gateway_step.response_fields()},
            "trace_id": trace_id,
        }
