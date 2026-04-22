"""Provider-neutral payment types.

Design principles:
- Every amount is in **minor units** (cents) to avoid float rounding.
- Every currency is lowercase ISO-4217 (``usd``, ``eur``, ``gbp``).
- The ``raw_payload`` field on ``WebhookEvent`` is kept for audit; we
  never evaluate logic on it — we use the typed fields.
- The canonical event enum is deliberately smaller than any individual
  provider's — collapsing 47 Stripe event types onto five states
  (``SUCCEEDED``, ``FAILED``, ``REFUNDED``, ``CANCELLED``, ``PENDING``)
  is what makes the state machine tractable.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol


class PaymentEventKind(str, enum.Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    PENDING = "pending"


class InvalidSignature(Exception):
    """Raised by ``PaymentProvider.verify_webhook`` when the HMAC
    signature check fails. Never expose the underlying provider error
    to the webhook caller — it can leak signing-secret shape."""


@dataclass(frozen=True)
class Intent:
    provider: str                   # "stripe" | "paypal" | "oci_osb"
    provider_reference: str         # pi_..., PAY-..., subscription id
    amount_minor_units: int
    currency: str                   # lowercase ISO-4217
    client_secret: str | None = None  # Stripe-style in-app confirm
    redirect_url: str | None = None   # PayPal-style hosted checkout


@dataclass(frozen=True)
class WebhookEvent:
    provider: str
    provider_event_id: str
    kind: PaymentEventKind
    provider_reference: str         # matches Intent.provider_reference
    amount_minor_units: int
    currency: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    """Every concrete provider adheres to this surface."""

    name: str

    def create_intent(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> Intent: ...

    def verify_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Raises :class:`InvalidSignature` on forged payloads."""
