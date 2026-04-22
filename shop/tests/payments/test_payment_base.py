"""Contract tests for the payment-provider abstraction.

Every concrete provider must honour the ``PaymentProvider`` Protocol:
- ``create_intent()`` → returns an ``Intent`` with an opaque provider
  reference and a redirect URL (or client_secret for in-app confirm).
- ``verify_webhook(body, headers)`` → raises ``InvalidSignature`` on
  tampered payloads, returns a ``WebhookEvent`` on valid ones.
- ``classify_event(event)`` → maps provider-specific event codes onto
  the shop's canonical ``PaymentEventKind`` enum.

Concrete provider tests live in test_stripe.py / test_paypal.py /
test_oci_osb.py and inherit these behaviours.
"""

from __future__ import annotations

import pytest

from server.modules.payments.base import (
    Intent,
    InvalidSignature,
    PaymentEventKind,
    WebhookEvent,
)


def test_intent_is_frozen_dataclass() -> None:
    intent = Intent(
        provider="stripe",
        provider_reference="pi_test_123",
        amount_minor_units=4999,
        currency="usd",
        client_secret="pi_test_123_secret_abc",
        redirect_url=None,
    )
    with pytest.raises(Exception):  # FrozenInstanceError subclass of AttributeError
        intent.amount_minor_units = 0  # type: ignore[misc]


def test_payment_event_kind_covers_canonical_states() -> None:
    # These five are the states the Order state machine consumes.
    must_have = {"SUCCEEDED", "FAILED", "REFUNDED", "CANCELLED", "PENDING"}
    assert must_have.issubset({e.name for e in PaymentEventKind})


def test_invalid_signature_is_raisable() -> None:
    with pytest.raises(InvalidSignature):
        raise InvalidSignature("forged hmac")


def test_webhook_event_carries_raw_payload_for_audit() -> None:
    event = WebhookEvent(
        provider="paypal",
        provider_event_id="evt_xyz",
        kind=PaymentEventKind.SUCCEEDED,
        provider_reference="PAY-9K3",
        amount_minor_units=19999,
        currency="usd",
        raw_payload={"id": "evt_xyz"},
    )
    assert event.raw_payload["id"] == "evt_xyz"
