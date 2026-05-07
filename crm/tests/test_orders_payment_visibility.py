"""CRM orders page payment visibility checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_orders_page_surfaces_payment_gateway_correlation_fields() -> None:
    template = (ROOT / "server/templates/orders.html").read_text()

    assert "<th>Payment</th>" in template
    assert "<th>Gateway</th>" in template
    assert "order.payment_status" in template
    assert "order.payment_required" in template
    assert "order.payment_gateway_request_id" in template
    assert "Payment Correlation" in template
    assert "payment_provider_reference" in template
