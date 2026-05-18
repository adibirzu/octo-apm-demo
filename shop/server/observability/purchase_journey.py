"""Purchase journey correlation helpers for shop traces and logs."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request


def _safe_text(value: object, *, limit: int = 120) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    safe = "".join(ch for ch in " ".join(text.split()) if 32 <= ord(ch) <= 126)
    return safe[:limit]


def _first_text(*values: object, limit: int = 120) -> str:
    for value in values:
        safe = _safe_text(value, limit=limit)
        if safe:
            return safe
    return ""


def purchase_context_from_request(
    request: Request,
    payload: dict[str, Any] | None = None,
    *,
    default_action: str = "",
    default_step: str = "",
    default_payment_method: str = "",
) -> dict[str, str]:
    """Extract token-safe browser journey metadata from request headers/payload."""
    body = payload if isinstance(payload, dict) else {}
    headers = request.headers
    return {
        "journey_id": _first_text(
            headers.get("x-octo-journey-id"),
            body.get("journey_id"),
            body.get("shop_journey_id"),
            limit=80,
        ),
        "session_id": _first_text(
            headers.get("x-octo-session-id"),
            body.get("session_id"),
            request.cookies.get("session_id", ""),
            limit=80,
        ),
        "browser_trace_id": _first_text(
            body.get("browser_trace_id"),
            headers.get("x-correlation-id"),
            limit=64,
        ),
        "user_action": _first_text(
            headers.get("x-octo-user-action"),
            body.get("user_action"),
            default_action,
            limit=120,
        ),
        "checkout_step": _first_text(
            headers.get("x-octo-checkout-step"),
            body.get("checkout_step"),
            default_step,
            limit=80,
        ),
        "payment_method": _first_text(
            headers.get("x-octo-payment-method"),
            body.get("payment_method"),
            default_payment_method,
            limit=50,
        ),
    }


def purchase_span_attributes(context: dict[str, str]) -> dict[str, str]:
    """Map browser journey metadata onto stable span/log field names."""
    field_map = {
        "journey_id": "shop.journey_id",
        "session_id": "shop.session_id",
        "browser_trace_id": "browser.trace_id",
        "user_action": "enduser.action",
        "checkout_step": "checkout.step",
        "payment_method": "payment.method",
    }
    return {
        target_key: context[source_key]
        for source_key, target_key in field_map.items()
        if context.get(source_key)
    }

