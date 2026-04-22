from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.modules._authz import require_management_user
from server.modules.products import ProductMutation
from server.modules.shops import ShopMutation


def _request_with_user(user: dict | None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/catalog",
        "headers": [],
    }
    request = Request(scope)
    request._state = SimpleNamespace(current_user=user)
    return request


def test_require_management_user_allows_admin_and_manager() -> None:
    admin_request = _request_with_user({"user_id": 1, "username": "admin", "role": "admin"})
    manager_request = _request_with_user({"user_id": 2, "username": "manager", "role": "manager"})

    assert require_management_user(admin_request)["role"] == "admin"
    assert require_management_user(manager_request)["role"] == "manager"


def test_require_management_user_rejects_viewer() -> None:
    request = _request_with_user({"user_id": 3, "username": "viewer", "role": "viewer"})

    with pytest.raises(HTTPException) as exc:
        require_management_user(request)

    assert exc.value.status_code == 403


def test_product_mutation_rejects_negative_price() -> None:
    with pytest.raises(Exception):
        ProductMutation(
            name="Bad Product",
            sku="BAD-001",
            price=-1,
            stock=10,
        )


def test_shop_mutation_rejects_invalid_urls() -> None:
    with pytest.raises(Exception):
        ShopMutation(
            name="Octo Demo",
            slug="octo-demo",
            storefront_url="not-a-url",
            crm_base_url="https://crm.example.cloud",
            region="eu-central",
        )


def test_products_page_template_exposes_management_controls() -> None:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "server"
        / "templates"
        / "products.html"
    )
    template = template_path.read_text()

    assert 'id="product-form"' in template
    assert "Save Product" in template
    assert "New Drone" in template
