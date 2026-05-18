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
PAYMENT_COMPONENT_LABELS = {
    "google-pay-gateway": "Google Pay Gateway",
    "apple-pay-gateway": "Apple Pay Gateway",
    "visa-payment-network": "VISA Payment Network",
    "mastercard-payment-network": "Mastercard Payment Network",
    "network-token-payment-network": "Network Token Payment Network",
    "octo-java-payment-processor": "OCTO Java Payment Processor",
    "octo-antifraud-verification-app": "OCTO Antifraud Verification App",
    GATEWAY_NAME: "OCTO Payment Gateway Emulator",
}

_SAFE_WORKFLOW_DETAIL_KEYS = frozenset(
    {
        "payment.gateway.decryption_method",
        "payment.wallet.provider",
        "payment.wallet.tokenization_type",
        "payment.wallet.gateway",
        "payment.wallet.token_hash",
        "payment.google_pay.api_version",
        "payment.google_pay.api_version_minor",
        "payment.google_pay.payment_method_data.type",
        "payment.google_pay.card_network",
        "payment.apple_pay.merchant_validation.status",
        "payment.apple_pay.payment_data.version",
        "payment.apple_pay.payment_method.network",
        "payment.apple_pay.header.transaction_id_hash",
        "payment.card.brand",
        "payment.card.last4",
        "payment.card.tokenized",
        "payment.card.avs.result",
        "payment.card.cvv.result",
        "payment.3ds.program",
        "payment.3ds.eci",
        "payment.processor.decision",
        "payment.processor.response_code",
        "payment.processor.gateway_code",
        "payment.status",
        "payment.error_code",
        "payment.decision_source",
        "payment.risk_score",
        "payment.gateway.final",
        "payment.network",
        "payment.network.route",
        "payment.network.response_code",
        "payment.network.gateway_code",
        "payment.network.transaction_id",
        "payment.acquirer.name",
    }
)


def workflow_detail_fields(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Return the token-safe subset shown in checkout/API workflow payloads."""
    if not attributes:
        return {}
    return {
        key: value
        for key, value in attributes.items()
        if key in _SAFE_WORKFLOW_DETAIL_KEYS and value not in ("", None)
    }


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
        attrs = self.attributes or {}
        payload = {
            "name": self.name,
            "phase": self.phase,
            "status": self.status,
            "latency_ms": round(float(self.latency_ms or 0), 2),
        }
        component = attrs.get("component")
        if component:
            payload["component"] = component
            payload["component_label"] = attrs.get("payment.component") or component
        peer_service = attrs.get("peer.service")
        if peer_service:
            payload["peer_service"] = peer_service
        details = workflow_detail_fields(attrs)
        if details:
            payload["details"] = details
        return payload


@dataclass(frozen=True)
class PaymentGatewayResult:
    gateway_request_id: str
    gateway_provider: str
    payment_network: str
    verification_result: dict[str, Any]
    java_result: dict[str, Any]
    steps: tuple[PaymentGatewayStep, ...]

    def response_fields(self) -> dict[str, Any]:
        verification_data = self.verification_result.get("data") or {}
        return {
            "gateway": GATEWAY_NAME,
            "provider": self.gateway_provider,
            "request_id": self.gateway_request_id,
            "payment_network": self.payment_network,
            "verification": {
                "provider": verification_data.get("verification_provider", "octo-antifraud-verification-app"),
                "status": self.verification_result.get("status", "unknown"),
                "decision": verification_data.get("decision", ""),
                "risk_score": verification_data.get("risk_score", 0),
                "error_code": verification_data.get("error_code", ""),
            },
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
        "processor_contract": "cybersource-compatible-authorization",
        "technical_reference_fields": [
            "Google Pay PaymentData.paymentMethodData.tokenizationData",
            "Apple Pay merchant session and payment token",
            "card authorization, AVS, CVV, 3DS, processor response, network transaction id",
        ],
        "steps_by_method": {
            "google_pay": _capability_step_names(_google_pay_steps()),
            "apple_pay": _capability_step_names(_apple_pay_steps()),
            "credit_card": _capability_step_names(_card_steps("visa")),
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


def _capability_step_names(method_steps: list[PaymentGatewayStep]) -> list[str]:
    return [
        step.name
        for step in [
            *method_steps,
            *_verification_steps(),
            *_processor_steps(),
            *_network_steps(),
            *_final_steps(),
        ]
    ]


async def emulate_payment_gateway_authorization(
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    customer_email: str,
    idempotency_key_hash: str,
    context: PaymentContext,
    intent_provider_reference: str,
    observability_context: dict[str, Any] | None = None,
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
    processor_service_name = _processor_service_name(java)
    journey_attrs = dict(observability_context or {})

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
                observability_context=journey_attrs,
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
                    observability_context=journey_attrs,
                )
            )

        emitted.append(
            _emit_step(
                PaymentGatewayStep(
                    name="verification_antifraud_request",
                    phase="verification",
                    message="Payment gateway sent transaction metadata to the antifraud verification app",
                    attributes={
                        "payment.verification.provider": "octo-antifraud-verification-app",
                        "payment.idempotency_key_hash": idempotency_key_hash,
                        "payment.antifraud.input_score": context.risk_score,
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
                observability_context=journey_attrs,
            )
        )
        verification_result = await java.verify_payment(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            customer_email=customer_email,
            idempotency_key_hash=idempotency_key_hash,
            payment_method=context.method,
            payment_network=network,
            context_risk_score=context.risk_score,
            risk_reasons=",".join(context.risk_reasons),
            payment_gateway_request_id=gateway_request_id,
            gateway_provider=GATEWAY_PROVIDER,
            wallet_type=context.wallet_type,
            wallet_provider=context.wallet_type,
            wallet_tokenization_type="PAYMENT_GATEWAY" if context.wallet_type == "google_pay" else ("APPLE_PAY" if context.wallet_type == "apple_pay" else ""),
            wallet_token_hash=context.wallet_token_hash,
            card_brand=context.card_brand,
            card_last4=context.card_last4,
            card_fingerprint=context.card_fingerprint,
            card_exp_month=context.card_exp_month,
            card_exp_year=context.card_exp_year,
            billing_postal_code=context.billing_postal_code,
            card_cvv_present=context.card_cvv_present,
        )
        verification_data = verification_result.get("data") or {}
        verification_decision = str(verification_data.get("decision") or "")
        verification_status = "completed" if verification_result.get("status") == "ok" else str(verification_result.get("status") or "error")
        if verification_decision == "declined":
            verification_status = "declined"
        elif verification_decision == "review":
            verification_status = "review"
        emitted.append(
            _emit_step(
                PaymentGatewayStep(
                    name="verification_antifraud_response",
                    phase="verification",
                    message="Payment gateway received antifraud verification decision",
                    status=verification_status,
                    attributes={
                        "payment.verification.provider": verification_data.get("verification_provider", "octo-antifraud-verification-app"),
                        "payment.verification.status": verification_result.get("status", "unknown"),
                        "payment.verification.decision": verification_decision,
                        "payment.verification.risk_score": int(verification_data.get("risk_score") or 0),
                        "payment.verification.error_code": verification_data.get("error_code", ""),
                        "payment.verification.periodic_review": bool(verification_data.get("periodic_review") or False),
                        "payment.verification.latency_ms": verification_result.get("latency_ms", 0),
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
                observability_context=journey_attrs,
            )
        )

        for processor_step in _processor_steps()[:1]:
            emitted.append(
                _emit_step(
                    replace(
                        processor_step,
                        attributes={
                            "payment.processor.name": processor_service_name,
                            "payment.gateway.authorization_type": "authorization",
                            "payment.idempotency_key_hash": idempotency_key_hash,
                            "payment.verification.decision": verification_decision,
                        },
                    ),
                    order_id=order_id,
                    amount_minor_units=amount_minor_units,
                    currency=currency,
                    context=context,
                    gateway_request_id=gateway_request_id,
                    network=network,
                    step_index=len(emitted) + 1,
                    observability_context=journey_attrs,
                )
            )
        java_result = await java.authorize_payment(
            order_id=order_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            customer_email=customer_email,
            idempotency_key_hash=idempotency_key_hash,
            payment_method=context.method,
            payment_network=network,
            payment_gateway_request_id=gateway_request_id,
            gateway_provider=GATEWAY_PROVIDER,
            wallet_type=context.wallet_type,
            wallet_provider=context.wallet_type,
            wallet_tokenization_type="PAYMENT_GATEWAY" if context.wallet_type == "google_pay" else ("APPLE_PAY" if context.wallet_type == "apple_pay" else ""),
            wallet_token_hash=context.wallet_token_hash,
            card_brand=context.card_brand,
            card_last4=context.card_last4,
            card_fingerprint=context.card_fingerprint,
            card_exp_month=context.card_exp_month,
            card_exp_year=context.card_exp_year,
            billing_postal_code=context.billing_postal_code,
            card_cvv_present=context.card_cvv_present,
            verification_decision=verification_decision,
            risk_reasons=",".join(context.risk_reasons),
        )
        java_data = java_result.get("data") or {}
        network_authorization = java_data.get("network_authorization") if isinstance(java_data.get("network_authorization"), dict) else {}
        card_flow = java_data.get("card_flow") if isinstance(java_data.get("card_flow"), dict) else {}
        processor_status = "completed" if java_result.get("status") == "ok" else str(java_result.get("status") or "error")
        emitted.append(
            _emit_step(
                replace(
                    _processor_steps()[1],
                    status=processor_status,
                    attributes={
                        "payment.processor.name": processor_service_name,
                        "payment.processor.status": java_result.get("status", "unknown"),
                        "payment.processor.decision": java_data.get("decision", ""),
                        "payment.processor.authorization_code": java_data.get("authorization_code", ""),
                        "payment.processor.error_code": java_data.get("error_code", ""),
                        "payment.processor.latency_ms": java_result.get("latency_ms", 0),
                        "payment.processor.response_code": network_authorization.get("response_code", ""),
                        "payment.processor.gateway_code": network_authorization.get("gateway_code", ""),
                        "payment.card.avs.result": card_flow.get("avs_result", ""),
                        "payment.card.cvv.result": card_flow.get("cvv_result", ""),
                    },
                ),
                order_id=order_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
                context=context,
                gateway_request_id=gateway_request_id,
                network=network,
                step_index=len(emitted) + 1,
                observability_context=journey_attrs,
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
                        "payment.network.response_code": network_authorization.get("response_code", ""),
                        "payment.network.gateway_code": network_authorization.get("gateway_code", ""),
                        "payment.network.transaction_id": network_authorization.get("network_transaction_id", ""),
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
                observability_context=journey_attrs,
            )
        )

    return PaymentGatewayResult(
        gateway_request_id=gateway_request_id,
        gateway_provider=GATEWAY_PROVIDER,
        payment_network=network,
        verification_result=verification_result,
        java_result=java_result,
        steps=tuple(emitted),
    )


def _processor_service_name(java: JavaAppServerClient) -> str:
    return str(getattr(java, "service_name", "") or "octo-java-app-server")


async def emit_final_gateway_decision(
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    context: PaymentContext,
    gateway_result: PaymentGatewayResult,
    decision: SimulatedPaymentDecision,
    observability_context: dict[str, Any] | None = None,
) -> PaymentGatewayStep:
    if decision.status == "authorized":
        status = "completed"
    elif decision.status in {"declined", "timeout"}:
        status = decision.status
    else:
        status = decision.status or "error"
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
        observability_context=observability_context,
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
    observability_context: dict[str, Any] | None = None,
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
            observability_context=observability_context,
        ),
        "payment.gateway.step": step.name,
        "payment.gateway.step_index": step_index,
        "payment.gateway.phase": step.phase,
        "payment.gateway.step_status": step.status,
        **_component_attributes(step, context=context, network=network),
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
    observability_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "component": GATEWAY_NAME,
        "peer.service": GATEWAY_NAME,
        "net.peer.name": GATEWAY_NAME,
        "payment.component": PAYMENT_COMPONENT_LABELS[GATEWAY_NAME],
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
        **dict(observability_context or {}),
    }


def _component_attributes(
    step: PaymentGatewayStep,
    *,
    context: PaymentContext,
    network: str,
) -> dict[str, Any]:
    component = _component_name(step, context=context, network=network)
    return {
        "component": component,
        "peer.service": component,
        "net.peer.name": component,
        "payment.component": PAYMENT_COMPONENT_LABELS.get(component, component),
    }


def _component_name(step: PaymentGatewayStep, *, context: PaymentContext, network: str) -> str:
    if step.phase == "verification":
        return "octo-antifraud-verification-app"
    if step.phase == "processor":
        return "octo-java-payment-processor"
    if step.name == "network_authorization_routing" or step.phase == "network":
        return _network_component(network)
    if context.method == "google_pay" and step.phase in {"ingress", "wallet_token", "network_token"}:
        return "google-pay-gateway"
    if context.method == "apple_pay" and step.phase in {"ingress", "wallet_session", "wallet_token", "network_token"}:
        return "apple-pay-gateway"
    if context.method == "credit_card" and step.name == "card_network_routing":
        return _network_component(network)
    return GATEWAY_NAME


def _network_component(network: str) -> str:
    normalized = (network or "").strip().lower()
    if normalized == "mastercard":
        return "mastercard-payment-network"
    if normalized == "visa":
        return "visa-payment-network"
    return "network-token-payment-network"


def _step_attributes(step: PaymentGatewayStep, *, context: PaymentContext, network: str) -> dict[str, Any]:
    network_label = _network_label(network or context.card_brand)
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
            "payment.wallet.gateway_merchant_id_hash": _stable_hash("octo-demo-google-pay-merchant"),
            "payment.wallet.cryptogram.present": bool(context.wallet_token_hash),
            "payment.google_pay.api_version": 2,
            "payment.google_pay.api_version_minor": 0,
            "payment.google_pay.payment_method_data.type": "CARD",
            "payment.google_pay.card_network": network_label,
        }
        method_specific = {
            "gateway_payment_received": {
                "payment.gateway.request_shape": "GooglePay.PaymentData",
                "payment.google_pay.allowed_auth_methods": "PAN_ONLY,CRYPTOGRAM_3DS",
            },
            "wallet_token_received": {
                "payment.wallet.token_hash": context.wallet_token_hash,
                "payment.wallet.encrypted_payload.present": bool(context.wallet_token_hash),
                "payment.google_pay.tokenization_data.type": "PAYMENT_GATEWAY",
            },
            "gateway_token_decryption": {
                "payment.gateway.decryption_method": "cybersource-compatible",
                "payment.wallet.encrypted_payload.format": "base64-simulated",
                "payment.google_pay.signed_message.format": "encrypted-json-simulated",
            },
            "network_token_cryptogram_validation": {
                "payment.network.token.present": bool(context.wallet_token_hash),
                "payment.network.cryptogram.validated": bool(context.wallet_token_hash),
                **_three_ds_fields(network, wallet=True),
            },
        }.get(step.name, {})
        return {**common, **wallet, **method_specific}
    if context.method == "apple_pay":
        wallet = {
            "payment.wallet.provider": "apple_pay",
            "payment.wallet.merchant_session.validated": True,
            "payment.wallet.cryptogram.present": bool(context.wallet_token_hash),
            "payment.apple_pay.payment_method.network": network_label,
            "payment.apple_pay.payment_method.type": "debit_or_credit",
        }
        method_specific = {
            "apple_pay_merchant_validation": {
                "payment.apple_pay.validation_url": "apple-pay-gateway.apple.com",
                "payment.apple_pay.session.emulated": True,
                "payment.apple_pay.merchant_validation.status": "completed",
                "payment.apple_pay.merchant_identifier_hash": _stable_hash("merchant.com.octo.demo"),
            },
            "wallet_token_received": {
                "payment.wallet.token_hash": context.wallet_token_hash,
                "payment.wallet.token_type": "apple_pay_payment_token",
                "payment.apple_pay.payment_data.version": "EC_v1",
                "payment.apple_pay.header.transaction_id_hash": _stable_hash(
                    f"{context.wallet_token_hash}:apple-pay-transaction"
                ),
                "payment.apple_pay.header.ephemeral_public_key.present": bool(context.wallet_token_hash),
                "payment.apple_pay.header.public_key_hash.present": bool(context.wallet_token_hash),
                "payment.apple_pay.signature.present": bool(context.wallet_token_hash),
                "payment.apple_pay.data.present": bool(context.wallet_token_hash),
            },
            "gateway_token_decryption": {
                "payment.gateway.decryption_method": "payment-service-provider",
                "payment.apple_pay.payment_processing_certificate": "simulated",
            },
            "network_token_cryptogram_validation": {
                "payment.network.token.present": bool(context.wallet_token_hash),
                "payment.network.cryptogram.validated": bool(context.wallet_token_hash),
                **_three_ds_fields(network, wallet=True),
            },
        }.get(step.name, {})
        return {**common, **wallet, **method_specific}
    method_specific = {
        "card_data_received": {
            "payment.card.pan_present": bool(context.card_last4),
            "payment.card.cvv_present": "not_logged",
            "payment.card.brand": context.card_brand,
            "payment.card.last4": context.card_last4,
            "payment.card.entry_mode": "ecommerce",
        },
        "gateway_card_tokenization": {
            "payment.card.tokenized": bool(context.card_fingerprint),
            "payment.card.fingerprint": context.card_fingerprint,
            "payment.card.brand": context.card_brand,
            "payment.card.last4": context.card_last4,
            "payment.card.avs.result": "Y" if context.billing_postal_code else "U",
            "payment.card.cvv.result": "M" if context.card_cvv_present else "U",
        },
        "card_network_routing": {
            "payment.network.route": f"{network or 'card'}-authorization",
            **_three_ds_fields(network),
        },
    }.get(step.name, {})
    return {**common, **method_specific}


def _network_label(network: str) -> str:
    normalized = (network or "").strip().lower()
    if normalized == "mastercard":
        return "MASTERCARD"
    if normalized == "visa":
        return "VISA"
    if normalized in {"network-token", "network_token"}:
        return "NETWORK_TOKEN"
    return normalized.upper() if normalized else "UNKNOWN"


def _three_ds_fields(network: str, *, wallet: bool = False) -> dict[str, Any]:
    normalized = (network or "").lower()
    if normalized == "mastercard":
        return {
            "payment.3ds.program": "Mastercard Identity Check",
            "payment.3ds.eci": "02",
            "payment.3ds.authentication_value.present": True,
            "payment.3ds.flow": "wallet_cryptogram" if wallet else "frictionless",
        }
    if normalized == "visa":
        return {
            "payment.3ds.program": "Visa Secure",
            "payment.3ds.eci": "05",
            "payment.3ds.authentication_value.present": True,
            "payment.3ds.flow": "wallet_cryptogram" if wallet else "frictionless",
        }
    return {
        "payment.3ds.program": "network-token-authentication" if wallet else "cardholder-authentication",
        "payment.3ds.eci": "07",
        "payment.3ds.authentication_value.present": wallet,
        "payment.3ds.flow": "wallet_cryptogram" if wallet else "attempted",
    }


def _stable_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:24]


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


def _verification_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("verification_antifraud_request", "verification", "Payment gateway sent transaction metadata to the antifraud verification app"),
        PaymentGatewayStep("verification_antifraud_response", "verification", "Payment gateway received antifraud verification decision"),
    ]


def _processor_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("processor_authorization_request", "processor", "Payment gateway forwarded the authorization request to the simulated processor"),
        PaymentGatewayStep("processor_authorization_response", "processor", "Payment gateway received the simulated processor authorization response"),
    ]


def _network_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("network_authorization_routing", "network", "Payment gateway routed the authorization through the simulated card network"),
    ]


def _final_steps() -> list[PaymentGatewayStep]:
    return [
        PaymentGatewayStep("merchant_authorization_result", "merchant_response", "Payment gateway returned the normalized authorization result to Drone Shop"),
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
