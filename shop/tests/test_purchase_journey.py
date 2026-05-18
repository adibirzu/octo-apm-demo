"""Purchase journey correlation helper tests."""

from __future__ import annotations

from starlette.requests import Request

from server.observability.purchase_journey import purchase_context_from_request, purchase_span_attributes


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/shop/checkout",
            "headers": headers or [],
            "cookies": {},
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def test_purchase_context_prefers_bounded_browser_headers() -> None:
    request = _request(
        [
            (b"x-octo-journey-id", b"journey-abc"),
            (b"x-octo-session-id", b"session-abc"),
            (b"x-correlation-id", b"a" * 32),
            (b"x-octo-user-action", b"shop.checkout.submit"),
            (b"x-octo-checkout-step", b"payment"),
            (b"x-octo-payment-method", b"google_pay"),
        ]
    )

    context = purchase_context_from_request(
        request,
        {"session_id": "payload-session", "payment_method": "credit_card"},
        default_action="fallback",
    )

    assert context == {
        "journey_id": "journey-abc",
        "session_id": "session-abc",
        "browser_trace_id": "a" * 32,
        "user_action": "shop.checkout.submit",
        "checkout_step": "payment",
        "payment_method": "google_pay",
    }


def test_purchase_span_attributes_use_log_analytics_field_names() -> None:
    attrs = purchase_span_attributes(
        {
            "journey_id": "journey-abc",
            "session_id": "session-abc",
            "browser_trace_id": "trace-abc",
            "user_action": "shop.cart.add",
            "checkout_step": "cart",
            "payment_method": "",
        }
    )

    assert attrs == {
        "shop.journey_id": "journey-abc",
        "shop.session_id": "session-abc",
        "browser.trace_id": "trace-abc",
        "enduser.action": "shop.cart.add",
        "checkout.step": "cart",
    }
