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
    assert "checkoutErrorMessage(result, res.status)" in template
    assert "typeof result.detail === 'string'" in template
    assert "browser_trace_id: state.browserTraceId" in template
    assert "journey_id: state.journeyId" in template
    assert "traceparent:" not in template
    assert "'X-Correlation-Id': correlationId" in template
    assert "Authorization = `Bearer ${token}`" in template
    assert "JOURNEY_TRACE_TTL_MS = 30 * 60 * 1000" in template
    assert "headers['X-OCTO-Journey-Id'] = state.journeyId" in template
    assert "purchaseJourney: true" in template
    assert "'X-OCTO-User-Action'" in template
    assert "'X-OCTO-Checkout-Step'" in template
    assert "'X-OCTO-Payment-Method'" in template
    assert "rotatePurchaseJourney('checkout_complete')" in template
    assert "shop_journey_id: state.journeyId" in template
    assert "payment.card_brand" in template
    assert "payment.wallet_type" in template
    assert "payment.gateway.step_count" in template
    assert "payment.gateway.verification.decision" in template
    rum_start = template.split("rumEvent('shop.checkout_start'", 1)[1].split("});", 1)[0]
    assert "card_number" not in rum_start
    assert "card_cvv" not in rum_start


def test_shop_checkout_renders_buyer_login_panel() -> None:
    template = (ROOT / "server/templates/shop.html").read_text()

    assert 'data-testid="buyer-panel"' in template
    assert 'data-testid="shop-login-link"' in template
    assert 'data-testid="shop-signout-button"' in template
    assert "renderBuyerPanel" in template
    assert "applyBuyerDefaults" in template


def test_shop_page_copy_is_demo_storefront_not_backend_console() -> None:
    template = (ROOT / "server/templates/shop.html").read_text()

    assert "All products, orders, prices, payment tokens, and customer data on this demo page are fake" in template
    assert "Showing synthetic demo catalog results" in template
    assert "existing backend" not in template
    assert "live Oracle ATP catalog" not in template
    assert "Loading catalog from Oracle ATP" not in template
    assert "Orders are persisted in Oracle ATP" not in template
    assert "Enterprise CRM" not in template
