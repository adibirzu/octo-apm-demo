"""OCI Subscription Billing (OSB) adapter — scaffold.

Intended for subscription-style charges (recurring drone maintenance
plans, fleet-manager tiers). Uses OCI REST APIs rather than a vendor
SDK; signing is via OCI request signatures so no per-webhook secret
is needed.

Production implementation deferred — the scaffold exists so the
provider-picker config accepts the option and exits with a clear
error rather than a KeyError.
"""

from __future__ import annotations

from .base import Intent, PaymentEventKind, WebhookEvent


class OCIOSBProvider:
    name = "oci_osb"

    def __init__(self, *, subscription_id: str, compartment_id: str):
        self._subscription_id = subscription_id
        self._compartment_id = compartment_id

    def create_intent(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> Intent:
        raise NotImplementedError(
            "OCI OSB create_intent not yet implemented — see OCI "
            "Subscription Billing REST reference"
        )

    def verify_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        raise NotImplementedError(
            "OCI OSB verify_webhook not yet implemented"
        )
