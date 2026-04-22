"""PayPal adapter.

PayPal webhook signature verification uses the
``/v1/notifications/verify-webhook-signature`` REST endpoint rather
than a local HMAC check. We keep the API surface identical to Stripe
but the implementation is HTTP-bound — heavy to exercise in unit tests,
so production use is validated via the webhook E2E suite.

This is a scaffold: the full PayPal SDK integration lands in a follow-up
PR. Tests verify the scaffold shape (Protocol conformance, name, raises
NotImplementedError for the two operations until the SDK is wired).
"""

from __future__ import annotations

from typing import Any

from .base import Intent, InvalidSignature, PaymentEventKind, WebhookEvent


class PayPalProvider:
    name = "paypal"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        webhook_id: str,
        sandbox: bool = True,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._webhook_id = webhook_id
        self._sandbox = sandbox

    def create_intent(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> Intent:
        # Scaffold — production path calls
        # POST /v2/checkout/orders and returns the approval URL.
        raise NotImplementedError(
            "PayPal create_intent not yet implemented — see "
            "https://developer.paypal.com/docs/api/orders/v2/#orders_create"
        )

    def verify_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        # Scaffold — production path POSTs to
        # /v1/notifications/verify-webhook-signature with the headers
        # (auth_algo, cert_url, transmission_id, etc.) and webhook body,
        # expects a 200 + verification_status="SUCCESS".
        raise NotImplementedError(
            "PayPal verify_webhook not yet implemented — see "
            "https://developer.paypal.com/api/rest/webhooks/rest/"
        )


def _map_paypal_event_type(type_: str) -> PaymentEventKind:  # pragma: no cover — future use
    mapping = {
        "PAYMENT.CAPTURE.COMPLETED": PaymentEventKind.SUCCEEDED,
        "PAYMENT.CAPTURE.DENIED": PaymentEventKind.FAILED,
        "PAYMENT.CAPTURE.REFUNDED": PaymentEventKind.REFUNDED,
        "CHECKOUT.ORDER.VOIDED": PaymentEventKind.CANCELLED,
        "CHECKOUT.ORDER.APPROVED": PaymentEventKind.PENDING,
    }
    return mapping.get(type_, PaymentEventKind.PENDING)
