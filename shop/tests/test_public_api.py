"""Public + partner API surface tests.

Stubs the underlying product/order adapters so the tests don't hit ATP.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Import the real module first so it's bound to sys.modules with
    # its real loader. Then inject fake adapter modules that the
    # handlers import lazily inside their function bodies.
    from server.modules import public_api
    from server.modules import version as version_module

    import types, sys

    products_stub = types.ModuleType("server.modules.products")

    async def _list_products_for_public_api(limit: int = 20):
        return [
            {"id": 1, "name": "Surveyor 6", "price": 1299.99, "stock": 5, "category": "drones"}
        ][:limit]

    async def _get_product_for_public_api(product_id: int):
        if product_id == 1:
            return {"id": 1, "name": "Surveyor 6", "price": 1299.99, "stock": 5, "category": "drones"}
        return None

    products_stub._list_products_for_public_api = _list_products_for_public_api
    products_stub._get_product_for_public_api = _get_product_for_public_api

    orders_stub = types.ModuleType("server.modules.orders")

    async def _get_order_for_partner_api(order_id: int):
        if order_id == 100:
            return {"id": 100, "customer_email": "b@example.invalid", "total": 99.99}
        return None

    async def _create_order_for_partner_api(*, customer_email, items, idempotency_token):
        return {
            "id": 9001,
            "customer_email": customer_email,
            "items": items,
            "idempotency_token": idempotency_token,
        }

    orders_stub._get_order_for_partner_api = _get_order_for_partner_api
    orders_stub._create_order_for_partner_api = _create_order_for_partner_api

    monkeypatch.setitem(sys.modules, "server.modules.products", products_stub)
    monkeypatch.setitem(sys.modules, "server.modules.orders", orders_stub)

    public_api._buckets.clear()

    app = FastAPI()
    app.include_router(public_api.public_router)
    app.include_router(public_api.partner_router)
    app.include_router(version_module.router)
    return TestClient(app)


def test_public_catalog(client: TestClient) -> None:
    r = client.get("/api/v1/public/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["name"] == "Surveyor 6"


def test_public_product_404(client: TestClient) -> None:
    r = client.get("/api/v1/public/products/999")
    assert r.status_code == 404


def test_partner_requires_key(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("PARTNER_API_KEY", "correct-key")
    # Missing header
    r = client.get("/api/v1/partner/orders/100")
    assert r.status_code == 401

    # Wrong key
    r = client.get("/api/v1/partner/orders/100", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_partner_success(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("PARTNER_API_KEY", "correct-key")
    r = client.get(
        "/api/v1/partner/orders/100",
        headers={"X-API-Key": "correct-key"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == 100


def test_partner_create_echoes_idempotency_token(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("PARTNER_API_KEY", "correct-key")
    r = client.post(
        "/api/v1/partner/orders",
        headers={"X-API-Key": "correct-key"},
        json={
            "customer_email": "b@example.invalid",
            "items": [{"product_id": 1, "quantity": 1}],
            "idempotency_token": "abc-123",
        },
    )
    assert r.status_code == 201
    assert r.json()["idempotency_token"] == "abc-123"


def test_partner_unset_returns_501(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("PARTNER_API_KEY", raising=False)
    r = client.get("/api/v1/partner/orders/100", headers={"X-API-Key": "x"})
    assert r.status_code == 501


def test_public_rate_limit(client: TestClient) -> None:
    # Fire 105 requests from the same client.host. The TestClient
    # reports the client as "testclient" so they all share a bucket.
    for _ in range(99):
        assert client.get("/api/v1/public/catalog").status_code == 200
    # 100th still ok
    assert client.get("/api/v1/public/catalog").status_code == 200
    # 101st should be limited
    r = client.get("/api/v1/public/catalog")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_version_endpoint(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("APP_IMAGE_TAG", "20260422-abc123")
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    monkeypatch.setenv("SCHEMA_VERSION", "3")
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["image_tag"] == "20260422-abc123"
    assert body["git_sha"] == "deadbeef"
    assert body["schema_version"] == "3"
