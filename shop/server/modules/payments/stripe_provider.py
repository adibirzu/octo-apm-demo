"""Stripe adapter.

Wraps the ``stripe`` Python SDK (already a transitive dep of our demo
stack). Only two API surfaces are touched: ``PaymentIntent.create`` and
``Webhook.construct_event`` — both are imported lazily so the module
stays importable even when the SDK is absent in minimal dev envs.
"""

from __future__ import annotations

from typing import Any

try:
    import stripe as _stripe_sdk  # type: ignore
except ImportError:  # pragma: no cover — exercised in minimal installs
    _stripe_sdk = None

from .base import (
    Intent,
    InvalidSignature,
    PaymentEventKind,
    PaymentProvider,
    WebhookEvent,
)

# Module-level reference so tests can monkeypatch a single name.
stripe = _stripe_sdk


def _map_stripe_event_type(type_: str) -> PaymentEventKind:
    """Canonicalise Stripe event codes onto :class:`PaymentEventKind`."""
    mapping = {
        "payment_intent.succeeded": PaymentEventKind.SUCCEEDED,
        "payment_intent.payment_failed": PaymentEventKind.FAILED,
        "charge.refunded": PaymentEventKind.REFUNDED,
        "payment_intent.canceled": PaymentEventKind.CANCELLED,
        "payment_intent.processing": PaymentEventKind.PENDING,
    }
    return mapping.get(type_, PaymentEventKind.PENDING)


class StripeProvider:
    name = "stripe"

    def __init__(self, *, api_key: str, webhook_secret: str):
        # Deliberately do NOT check ``stripe`` at construction time.
        # Tests monkeypatch the module-level ``stripe`` reference after
        # instantiation; a constructor-time check would break that.
        # The SDK-missing error surfaces on the first real call.
        self._api_key = api_key
        self._webhook_secret = webhook_secret

    def _require_sdk(self) -> None:
        if stripe is None:
            raise RuntimeError(
                "stripe SDK not installed; add `stripe>=8,<12` to "
                "shop/requirements.txt to enable."
            )

    def create_intent(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> Intent:
        self._require_sdk()
        stripe.api_key = self._api_key  # pragma: no cover — SDK module
        pi = stripe.PaymentIntent.create(
            amount=amount_minor_units,
            currency=currency,
            metadata={
                "order_id": str(order_id),
                "customer_email": customer_email,
                "source_system": "octo-drone-shop",
            },
            automatic_payment_methods={"enabled": True},
        )
        return Intent(
            provider=self.name,
            provider_reference=pi.id,
            amount_minor_units=int(pi.amount),
            currency=str(pi.currency).lower(),
            client_secret=pi.client_secret,
        )

    def verify_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        self._require_sdk()
        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature") or ""
        try:
            event: Any = stripe.Webhook.construct_event(
                payload=body,
                sig_header=sig,
                secret=self._webhook_secret,
            )
        except stripe.error.SignatureVerificationError as exc:  # type: ignore[attr-defined]
            raise InvalidSignature(str(exc)) from exc
        except Exception as exc:  # pragma: no cover — other SDK errors
            raise InvalidSignature(f"stripe webhook verify failed: {exc}") from exc

        obj = event["data"]["object"]
        return WebhookEvent(
            provider=self.name,
            provider_event_id=str(event.get("id", "")),
            kind=_map_stripe_event_type(str(event.get("type", ""))),
            provider_reference=str(obj.get("id", "")),
            amount_minor_units=int(obj.get("amount", 0) or 0),
            currency=str(obj.get("currency", "")).lower() or "usd",
            raw_payload=event if isinstance(event, dict) else dict(event),
        )
