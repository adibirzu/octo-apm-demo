"""Storefront payment widget regression tests."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shop_checkout_renders_card_and_wallet_payment_controls() -> None:
    template = (ROOT / "server/templates/shop.html").read_text()

    assert 'id="paymentCardPanel"' in template
    assert 'name="card_number"' in template
    assert 'name="card_cvv"' in template
    assert 'value="apple_pay"' in template
    assert 'value="google_pay"' in template
    assert "Simulate Apple Pay" in template
    assert "Simulate Google Pay" in template


def test_shop_checkout_posts_structured_payment_details() -> None:
    template = (ROOT / "server/templates/shop.html").read_text()

    assert "payment_details: buildPaymentDetails(formEl, form)" in template
    assert "payment.card_brand" in template
    assert "payment.wallet_type" in template
    assert "payment.gateway.step_count" in template
    rum_start = template.split("rumEvent('shop.checkout_start'", 1)[1].split("});", 1)[0]
    assert "card_number" not in rum_start
    assert "card_cvv" not in rum_start
