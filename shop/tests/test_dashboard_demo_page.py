"""Workspace dashboard copy regression tests."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_dashboard_is_shop_demo_not_backend_workspace() -> None:
    template = (ROOT / "server/templates/dashboard.html").read_text()

    assert "This is a demo page." in template
    assert "All products, customers, orders, stock, prices, and revenue values are fake" in template
    assert "Demo Observability Signals" in template
    assert "Shop Demo Paths" in template
    assert "Platform Health" not in template
    assert "Drilldowns" not in template
    assert "Correlation Snapshot" not in template
    assert "/api/integrations/status" not in template
    assert "/api/integrations/crm/health" not in template
    assert "Enterprise CRM" not in template


def test_customer_templates_avoid_backend_internal_copy() -> None:
    shop_template = (ROOT / "server/templates/shop.html").read_text()
    login_template = (ROOT / "server/templates/login.html").read_text()

    assert "backend APIs" not in login_template
    assert "backendChip" not in shop_template
    assert "APM ready" in shop_template


def test_shop_checkout_explains_observability_pivots() -> None:
    template = (ROOT / "server/templates/shop.html").read_text()

    assert "What this checkout generates" in template
    assert "checkout-payment-correlation" in template
    assert "Captured data pivots" in template
    assert "Payment Gateway Request ID" in template
    assert "Payment Flow Components" in template
    assert "Apple Pay Gateway" in template
    assert "Google Pay Gateway" in template
    assert "VISA Payment Network" in template
    assert "Mastercard Payment Network" in template
    assert "payment-gateway-security-triage" in template
    assert "copy-evidence-btn" in template
    assert "OCTO APM - checkout end-to-end" in template
    assert "DbOracleSqlId" in template
    assert "data-testid=\"checkout-evidence\"" in template
    assert "renderCheckoutEvidence" in template
