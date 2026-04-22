"""Provider registry — one active provider per deployment.

Reads ``PAYMENT_PROVIDER`` env and returns the matching adapter. The
shop's checkout route calls this on every order so the live provider
can be swapped without redeploying (just restart the pod after
changing the Secret).
"""

from __future__ import annotations

import os
from functools import lru_cache

from .base import PaymentProvider
from .oci_osb_provider import OCIOSBProvider
from .paypal_provider import PayPalProvider
from .stripe_provider import StripeProvider


def _env_secret(name: str, default: str = "") -> str:
    """Same secret-lookup semantics as server.config — honours *_FILE."""
    value = os.getenv(name, "")
    if value:
        return value
    file_path = (os.getenv(f"{name}_FILE", "") or "").strip()
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return default
    return default


@lru_cache(maxsize=1)
def _active_provider() -> PaymentProvider | None:
    name = os.getenv("PAYMENT_PROVIDER", "").strip().lower()
    if not name:
        return None

    if name == "stripe":
        api_key = _env_secret("STRIPE_API_KEY")
        webhook_secret = _env_secret("STRIPE_WEBHOOK_SECRET")
        if not api_key or not webhook_secret:
            return None
        return StripeProvider(api_key=api_key, webhook_secret=webhook_secret)

    if name == "paypal":
        client_id = _env_secret("PAYPAL_CLIENT_ID")
        client_secret = _env_secret("PAYPAL_CLIENT_SECRET")
        webhook_id = _env_secret("PAYPAL_WEBHOOK_ID")
        if not client_id or not client_secret or not webhook_id:
            return None
        return PayPalProvider(
            client_id=client_id,
            client_secret=client_secret,
            webhook_id=webhook_id,
            sandbox=os.getenv("PAYPAL_SANDBOX", "true").lower() == "true",
        )

    if name == "oci_osb":
        sub = _env_secret("OCI_OSB_SUBSCRIPTION_ID")
        comp = _env_secret("OCI_COMPARTMENT_ID")
        if not sub or not comp:
            return None
        return OCIOSBProvider(subscription_id=sub, compartment_id=comp)

    return None


def get_provider(name: str | None = None) -> PaymentProvider | None:
    """Return the configured provider. ``name`` is a hint — if provided,
    must match the configured one (so a Stripe webhook against a PayPal
    deployment returns ``None`` and yields a 501)."""
    active = _active_provider()
    if active is None:
        return None
    if name is None:
        return active
    return active if active.name == name else None


def clear_cache() -> None:
    """Test helper — forget the cached active provider so env-var
    changes in a test suite are honoured."""
    _active_provider.cache_clear()
