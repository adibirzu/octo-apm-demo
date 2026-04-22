"""Payment gateway abstraction — Phase 2 of the enhancement roadmap.

Providers implement a single Protocol defined in ``base.py``. The
webhook ingestion route (``webhooks.py``) verifies signatures, classifies
events, and drives the order state machine (``state_machine.py``).

Configuration (env):
    PAYMENT_PROVIDER = stripe | paypal | oci_osb | ""   (empty → stub)
    STRIPE_API_KEY / STRIPE_WEBHOOK_SECRET
    PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET / PAYPAL_WEBHOOK_ID
    OCI_OSB_SUBSCRIPTION_ID

Absence of provider config is intentional: the shop continues to run
with a synchronous stubbed total so existing demos keep working —
webhook endpoint returns 501 until a provider is configured.
"""

from .base import (
    Intent,
    InvalidSignature,
    PaymentEventKind,
    PaymentProvider,
    WebhookEvent,
)
from .state_machine import IllegalTransition, OrderState, transition

__all__ = [
    "Intent",
    "InvalidSignature",
    "PaymentEventKind",
    "PaymentProvider",
    "WebhookEvent",
    "OrderState",
    "IllegalTransition",
    "transition",
]
