"""Workflow mapping regression tests for APM and Log Analytics pivots."""

from __future__ import annotations

from server.observability.workflow_context import resolve_workflow


def test_checkout_and_login_paths_have_log_analytics_workflow_fields() -> None:
    checkout = resolve_workflow("/api/shop/checkout")
    login = resolve_workflow("/api/auth/login")

    assert checkout.workflow_id == "checkout"
    assert checkout.step == "payment"
    assert login.workflow_id == "login"
    assert login.step == "authenticate"


def test_storefront_paths_keep_catalog_workflow_fields() -> None:
    storefront = resolve_workflow("/api/shop/storefront")

    assert storefront.workflow_id == "browse-catalog"
    assert storefront.step == "storefront"
