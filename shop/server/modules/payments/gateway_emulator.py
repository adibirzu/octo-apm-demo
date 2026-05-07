"""Dedicated payment gateway emulator for checkout observability.

The emulator models the middle tier between Drone Shop checkout and the
simulated card/wallet networks. It emits one span and one structured log for
each gateway step so APM and Logging show the full wallet/card authorization
path, while only storing token-safe metadata.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any

from opentelemetry import trace
from sqlalchemy import text

from server.modules.java_app_server import JavaAppServerClient
from server.modules.payments.checkout_workflow import PaymentContext
from server.modules.payments.simulated_provider import SimulatedPaymentDecision
from server.observability.correlation import apply_span_attributes, current_trace_context
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer


GATEWAY_NAME = "octo-payment-gateway-emulator"
GATEWAY_PROVIDER = "cybersource-compatible-simulator"
GATEWAY_VERSION = "2026.05"


@dataclass(frozen=True)
class PaymentGatewayStep:
    name: str
    phase: str
    message: str
    status: str = "completed"
    attributes: dict[str, Any] | None = None
    latency_ms: float = 0.0
    trace_id: str = ""
    span_id: str = ""

    def response_fields(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phase": self.phase,
            "status": self.status,
            "latency_ms": round(float(self.latency_ms or 0), 2),
        }


@dataclass(frozen=True)
class PaymentGatewayResult:
    gateway_request_id: str
    gateway_provider: str
    payment_network: str
    java_result: dict[str, Any]
    steps: tuple[PaymentGatewayStep, ...]

    def response_fields(self) -> dict[str, Any]:
        return {
            "gateway": GATEWAY_NAME,
            "provider": self.gateway_provider,
            "request_id": self.gateway_request_id,
            "payment_network": self.payment_network,
            "steps": [step.response_fields() for step in self.steps],
        }


def payment_gateway_capabilities() -> dict[str, Any]:
    return {
        "gateway": GATEWAY_NAME,
        "provider": GATEWAY_PROVIDER,
        "version": GATEWAY_VERSION,
        "methods": ["credit_card", "apple_pay", "google_pay"],
        "card_networks": ["visa", "mastercard"],
        "wallets": ["apple_pay", "google_pay"],
        "steps_by_method": {
            "google_pay": [step.name for step in _google_pay_steps()],
            "apple_pay": [step.name for step in _apple_pay_steps()],
            "credit_card": [step.name for step in _card_steps("visa")],
        },
        "stores": ["payment_transactions", "payment_gateway_events"],
        "safe_storage": "tokenized_metadata_only",
    }


def build_gateway_steps(context: PaymentContext) -> tuple[PaymentGatewayStep, ...]:
    if context.method == "google_pay":
        return tuple(_google_pay_steps())
    if context.method == "apple_pay":
        return tuple(_apple_pay_steps())
    return tuple(_card_steps(context.card_brand or "card"))


async def emulate_payment_gateway_authorization(
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    customer_email: str,
    idempotency_key_hash: str,
    context: PaymentContext,
    intent_provider_reference: str,
    java_client: JavaAppServerClient | None = None,
) -> PaymentGatewayResult:
    """Run gateway processing and return the downstream Java authorization.

    The Java sidecar remains the simulated processor/network hop, but it is now
    wrapped by explicit gateway spans so wallet/card processing appears as a
    real component between checkout and the downstream authorization segment.
    """

    gateway_request_id = _gateway_request_id(order_id, intent_provider_reference)
    network = _payment_network(context)
    tracer = get_tracer()
    emitted: list[PaymentGatewayStep] = []
    java = java_client or JavaAppServerClient()

    with tracer.start_as_current_span("payment_gateway.emulator.authorize") as span:
        apply_span_attributes(
            span,
            _base_attributes(
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
            ),
        )
        for index, step in enumerate(build_gateway_steps(context), start=1):
            emitted.append(
                _emit_step(
                    replace(step, attributes=_step_attributes(step, context=context, network=network)),
                    order_id=order_id,
                    amount_minor_units=amount_minor_units,
                    currency=currency,
                    context=context,
                    gateway_request_id=gateway_request_id,
                    network=network,
                    step_index=index,
                )
            )

        emitted.append(
            _emit_step(
                PaymentGatewayStep(
                    name="processor_authorization_request",
                    phase="processor",
                    message="Payment gateway forwarded the authorization request to the simulated processor",
                    attributes={
                        "payment.processor.name": "octo-java-app-server",
                        "payment.gateway.authorization_type": "authorization",
                        "payment.idempotency_key_hash": idempotency_key_hash,
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
            )
        )
        java_result = await java.authorize_payment(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            customer_email=customer_email,
            idempotency_key_hash=idempotency_key_hash,
        )
        java_data = java_result.get("data") or {}
        processor_status = "completed" if java_result.get("status") == "ok" else str(java_result.get("status") or "error")
        emitted.append(
            _emit_step(
                PaymentGatewayStep(
                    name="processor_authorization_response",
                    phase="processor",
                    message="Payment gateway received the simulated processor authorization response",
                    status=processor_status,
                    attributes={
                        "payment.processor.name": "octo-java-app-server",
                        "payment.processor.status": java_result.get("status", "unknown"),
                        "payment.processor.decision": java_data.get("decision", ""),
                        "payment.processor.authorization_code": java_data.get("authorization_code", ""),
                        "payment.processor.error_code": java_data.get("error_code", ""),
                        "payment.processor.latency_ms": java_result.get("latency_ms", 0),
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
            )
        )
        emitted.append(
            _emit_step(
                PaymentGatewayStep(
                    name="network_authorization_routing",
                    phase="network",
                    message="Payment gateway routed the authorization through the simulated card network",
                    attributes={
                        "payment.network": network,
                        "payment.network.route": f"{network or 'card'}-simulated-rail",
                        "payment.acquirer.name": "octo-acquirer-simulator",
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
            )
        )

    return PaymentGatewayResult(
        gateway_request_id=gateway_request_id,
        gateway_provider=GATEWAY_PROVIDER,
        payment_network=network,
        java_result=java_result,
        steps=tuple(emitted),
    )


async def emit_final_gateway_decision(
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    context: PaymentContext,
    gateway_result: PaymentGatewayResult,
    decision: SimulatedPaymentDecision,
) -> PaymentGatewayStep:
    status = "completed" if decision.status == "authorized" else "declined"
    step = _emit_step(
        PaymentGatewayStep(
            name="merchant_authorization_result",
            phase="merchant_response",
            status=status,
            message="Payment gateway returned the normalized authorization result to Drone Shop",
            attributes={
                "payment.status": decision.status,
                "payment.provider_reference": decision.provider_reference,
                "payment.error_code": decision.error_code,
                "payment.decision_source": decision.decision_source,
                "payment.risk_score": decision.risk_score,
                "payment.gateway.final": True,
            },
        ),
        order_id=order_id,
        amount_minor_units=amount_minor_units,
        currency=currency,
        context=context,
        gateway_request_id=gateway_result.gateway_request_id,
        network=gateway_result.payment_network,
        step_index=len(gateway_result.steps) + 1,
    )
    return step


async def persist_payment_gateway_events(
    db,
    *,
    order_id: int,
    context: PaymentContext,
    gateway_result: PaymentGatewayResult,
    final_step: PaymentGatewayStep,
) -> None:
    if db is None:
        return

    for index, step in enumerate((*gateway_result.steps, final_step), start=1):
        attrs = _safe_json(step.attributes or {})
        await db.execute(
            text(
                """
                INSERT INTO payment_gateway_events (
                    order_id, gateway_name, gateway_provider, gateway_request_id,
                    payment_method, wallet_type, card_brand, card_last4,
                    payment_network, step_name, step_phase, step_status,
                    step_index, latency_ms, trace_id, span_id, metadata_json
                ) VALUES (
                    :order_id, :gateway_name, :gateway_provider, :gateway_request_id,
                    :payment_method, :wallet_type, :card_brand, :card_last4,
                    :payment_network, :step_name, :step_phase, :step_status,
                    :step_index, :latency_ms, :trace_id, :span_id, :metadata_json
                )
                """
            ),
            {
                "order_id": int(order_id),
                "gateway_name": GATEWAY_NAME,
                "gateway_provider": gateway_result.gateway_provider,
                "gateway_request_id": gateway_result.gateway_request_id,
                "payment_method": context.method,
                "wallet_type": context.wallet_type,
                "card_brand": context.card_brand,
                "card_last4": context.card_last4,
                "payment_network": gateway_result.payment_network,
                "step_name": step.name,
                "step_phase": step.phase,
                "step_status": step.status,
                "step_index": index,
                "latency_ms": round(float(step.latency_ms or 0), 2),
                "trace_id": step.trace_id,
                "span_id": step.span_id,
                "metadata_json": attrs,
            },
        )


def _emit_step(
    step: PaymentGatewayStep,
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    context: PaymentContext,
    gateway_request_id: str,
    network: str,
    step_index: int,
) -> PaymentGatewayStep:
    tracer = get_tracer()
    started = time.monotonic()
    operation = f"payment_gateway.{context.method}.{step.name}"
    attrs = {
        **_base_attributes(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            context=context,
            gateway_request_id=gateway_request_id,
            network=network,
        ),
        "payment.gateway.step": step.name,
        "payment.gateway.step_index": step_index,
        "payment.gateway.phase": step.phase,
        "payment.gateway.step_status": step.status,
        **(step.attributes or {}),
    }
    with tracer.start_as_current_span(operation) as span:
        apply_span_attributes(span, attrs)
        if step.status not in {"completed", "authorized", "ok"}:
            span.set_attribute("otel.status_code", "ERROR")
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        trace_ctx = current_trace_context()
        attrs["payment.gateway.step_latency_ms"] = elapsed_ms
        push_log(
            "INFO" if step.status in {"completed", "authorized", "ok"} else "WARNING",
            step.message,
            **attrs,
        )
        return replace(
            step,
            latency_ms=elapsed_ms,
            trace_id=trace_ctx["trace_id"],
            span_id=trace_ctx["span_id"],
            attributes=attrs,
        )


def _base_attributes(
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    context: PaymentContext,
    gateway_request_id: str,
    network: str,
) -> dict[str, Any]:
    return {
        "peer.service": GATEWAY_NAME,
        "payment.gateway.name": GATEWAY_NAME,
        "payment.gateway.provider": GATEWAY_PROVIDER,
        "payment.gateway.version": GATEWAY_VERSION,
        "payment.gateway.request_id": gateway_request_id,
        "payment.method": context.method,
        "payment.provider": context.provider,
        "payment.wallet_type": context.wallet_type,
        "payment.network": network,
        "payment.card_brand": context.card_brand,
        "payment.card_last4": context.card_last4,
        "payment.wallet_token_hash": context.wallet_token_hash,
        "payment.amount_minor_units": int(amount_minor_units),
        "payment.currency": (currency or "usd").lower(),
        "orders.order_id": int(order_id),
        "workflow.id": "checkout-payment",
        "workflow.step": "payment-gateway",
    }


def _step_attributes(step: PaymentGatewayStep, *, context: PaymentContext, network: str) -> dict[str, Any]:
    common = {
        "payment.gateway.emulated": True,
        "payment.token.safe": True,
        "payment.network": network,
    }
    if context.method == "google_pay":
        wallet = {
            "payment.wallet.provider": "google_pay",
            "payment.wallet.tokenization_type": "PAYMENT_GATEWAY",
            "payment.wallet.gateway": "cybersource",
            "payment.wallet.cryptogram.present": bool(context.wallet_token_hash),
        }
        method_specific = {
            "wallet_token_received": {
                "payment.wallet.token_hash": context.wallet_token_hash,
                "payment.wallet.encrypted_payload.present": bool(context.wallet_token_hash),
            },
            "gateway_token_decryption": {
                "payment.gateway.decryption_method": "cybersource-compatible",
                "payment.wallet.encrypted_payload.format": "base64-simulated",
            },
            "network_token_cryptogram_validation": {
                "payment.network.token.present": bool(context.wallet_token_hash),
                "payment.network.cryptogram.validated": bool(context.wallet_token_hash),
            },
        }.get(step.name, {})
        return {**common, **wallet, **method_specific}
    if context.method == "apple_pay":
        wallet = {
            "payment.wallet.provider": "apple_pay",
            "payment.wallet.merchant_session.validated": True,
            "payment.wallet.cryptogram.present": bool(context.wallet_token_hash),
        }
        method_specific = {
            "apple_pay_merchant_validation": {
                "payment.apple_pay.validation_url": "apple-pay-gateway.apple.com",
                "payment.apple_pay.session.emulated": True,
            },
            "wallet_token_received": {
                "payment.wallet.token_hash": context.wallet_token_hash,
                "payment.wallet.token_type": "apple_pay_payment_token",
            },
            "gateway_token_decryption": {
                "payment.gateway.decryption_method": "payment-service-provider",
                "payment.apple_pay.payment_processing_certificate": "simulated",
            },
            "network_token_cryptogram_validation": {
                "payment.network.token.present": bool(context.wallet_token_hash),
                "payment.network.cryptogram.validated": bool(context.wallet_token_hash),
            },
        }.get(step.name, {})
        return {**common, **wallet, **method_specific}
    method_specific = {
        "card_data_received": {
            "payment.card.pan_present": bool(context.card_last4),
            "payment.card.cvv_present": "not_logged",
        },
        "gateway_card_tokenization": {
            "payment.card.tokenized": bool(context.card_fingerprint),
            "payment.card.fingerprint": context.card_fingerprint,
        },
        "card_network_routing": {
            "payment.network.route": f"{network or 'card'}-authorization",
        },
    }.get(step.name, {})
    return {**common, **method_specific}


def _google_pay_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("gateway_payment_received", "ingress", "Payment gateway received Google Pay authorization request"),
        PaymentGatewayStep("wallet_token_received", "wallet_token", "Payment gateway received Google Pay encrypted payment data"),
        PaymentGatewayStep("gateway_token_decryption", "wallet_token", "Payment gateway simulated Google Pay token formatting and decryption"),
        PaymentGatewayStep("network_token_cryptogram_validation", "network_token", "Payment gateway validated simulated Google Pay network token and cryptogram"),
        PaymentGatewayStep("internal_antifraud_screening", "risk", "Payment gateway ran internal antifraud screening for Google Pay"),
    ]


def _apple_pay_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("gateway_payment_received", "ingress", "Payment gateway received Apple Pay authorization request"),
        PaymentGatewayStep("apple_pay_merchant_validation", "wallet_session", "Payment gateway simulated Apple Pay merchant session validation"),
        PaymentGatewayStep("wallet_token_received", "wallet_token", "Payment gateway received Apple Pay payment token"),
        PaymentGatewayStep("gateway_token_decryption", "wallet_token", "Payment gateway simulated Apple Pay PSP token decryption handoff"),
        PaymentGatewayStep("network_token_cryptogram_validation", "network_token", "Payment gateway validated simulated Apple Pay network token and cryptogram"),
        PaymentGatewayStep("internal_antifraud_screening", "risk", "Payment gateway ran internal antifraud screening for Apple Pay"),
    ]


def _card_steps(network: str) -> list[PaymentGatewayStep]:
    label = "Mastercard" if network == "mastercard" else "Visa" if network == "visa" else "card"
    return [
        PaymentGatewayStep("gateway_payment_received", "ingress", f"Payment gateway received {label} card authorization request"),
        PaymentGatewayStep("card_data_received", "card_token", f"Payment gateway received {label} card data at simulator boundary"),
        PaymentGatewayStep("gateway_card_tokenization", "card_token", f"Payment gateway tokenized {label} card metadata"),
        PaymentGatewayStep("internal_antifraud_screening", "risk", f"Payment gateway ran internal antifraud screening for {label} card"),
        PaymentGatewayStep("card_network_routing", "network", f"Payment gateway selected the simulated {label} authorization rail"),
    ]


def _payment_network(context: PaymentContext) -> str:
    if context.card_brand in {"visa", "mastercard"}:
        return context.card_brand
    if context.wallet_type:
        return "network-token"
    return "card"


def _gateway_request_id(order_id: int, provider_reference: str) -> str:
    digest = sha256(f"{order_id}:{provider_reference}".encode("utf-8")).hexdigest()[:16]
    return f"pgw-{order_id}-{digest}"


def _safe_json(value: dict[str, Any]) -> str:
    safe = {
        key: item
        for key, item in value.items()
        if not any(secret in key.lower() for secret in ("pan", "cvv", "token.raw", "authorization"))
    }
    safe["metadata_id"] = uuid.uuid4().hex[:12]
    return json.dumps(safe, sort_keys=True, default=str)[:4000]
