"""Regression: POST /api/orders must reject unauthenticated callers when
INTERNAL_SERVICE_KEY is configured, and must honor idempotency metadata
(idempotency_token, source_system, source_order_id) supplied by the
calling service so retries don't create duplicate orders.

The shop-side change (octo-drone-shop) adds these fields to every order
sync payload; this side must accept them rather than regenerate a new
source_order_id on each call.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Iterable
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.modules import orders as orders_module


def _set_internal_key(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """cfg is a frozen dataclass — replace the whole cfg object in
    the orders module with a SimpleNamespace whose only attribute the
    auth check reads."""
    monkeypatch.setattr(
        orders_module, "cfg", SimpleNamespace(drone_shop_internal_key=key)
    )


class _FakeScalarResult:
    def __init__(self, items: Iterable[Any]):
        self._items = list(items)

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._items)


class _FakeCustomer:
    def __init__(self, customer_id: int = 42, email: str = "buyer@example.invalid"):
        self.id = customer_id
        self.email = email
        self.name = "Buyer"


class _FakeDb:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed: int = 0

    async def get(self, _model: Any, pk: int) -> _FakeCustomer | None:
        return _FakeCustomer(customer_id=pk) if pk else None

    async def execute(self, _stmt: Any) -> _FakeScalarResult:
        # No products matched → order_items list will be empty but fine
        return _FakeScalarResult([])

    def add(self, obj: Any) -> None:
        # Mimic SQLAlchemy auto-id assignment on first add of an Order
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = 9001
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1


class _FakeDbCtx:
    def __init__(self) -> None:
        self.db = _FakeDb()

    async def __aenter__(self) -> _FakeDb:
        return self.db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Prevent the real DB and tracer from running during tests.
    monkeypatch.setattr(orders_module, "get_db", lambda: _FakeDbCtx())
    dummy_span = MagicMock()
    dummy_span.__enter__ = MagicMock(return_value=dummy_span)
    dummy_span.__exit__ = MagicMock(return_value=False)
    dummy_tracer = MagicMock()
    dummy_tracer.start_as_current_span.return_value = dummy_span
    monkeypatch.setattr(orders_module, "tracer_fn", lambda: dummy_tracer)

    app = FastAPI()
    app.include_router(orders_module.router)
    return TestClient(app)


@pytest.mark.portability
@pytest.mark.security
def test_post_order_rejects_without_key_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_internal_key(monkeypatch, "shared-secret")
    resp = client.post(
        "/api/orders",
        json={"customer_id": 42, "items": [{"product_id": 1, "quantity": 1, "unit_price": 1.0}]},
    )
    assert resp.status_code == 401, (
        "Cross-service order POST must require X-Internal-Service-Key "
        "when INTERNAL_SERVICE_KEY is configured."
    )


@pytest.mark.portability
@pytest.mark.security
def test_post_order_accepts_with_valid_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_internal_key(monkeypatch, "shared-secret")
    resp = client.post(
        "/api/orders",
        headers={"X-Internal-Service-Key": "shared-secret"},
        json={"customer_id": 42, "items": [{"product_id": 1, "quantity": 1, "unit_price": 1.0}]},
    )
    assert resp.status_code == 200


@pytest.mark.portability
def test_post_order_allows_anonymous_when_key_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-compat: if no key is configured, anonymous POST is still allowed.
    That is the pre-change behavior; we only add enforcement when opted in."""
    _set_internal_key(monkeypatch, "")
    resp = client.post(
        "/api/orders",
        json={"customer_id": 42, "items": [{"product_id": 1, "quantity": 1, "unit_price": 1.0}]},
    )
    assert resp.status_code == 200


@pytest.mark.portability
def test_post_order_honors_payload_source_order_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the calling service supplies source_system + source_order_id,
    CRM must use those values verbatim instead of generating its own.
    That is the basis for dedup across retries."""
    _set_internal_key(monkeypatch, "")
    captured: dict[str, Any] = {}

    original_add = _FakeDb.add

    def _tracking_add(self: _FakeDb, obj: Any) -> None:
        if obj.__class__.__name__ == "Order":
            captured["source_system"] = obj.source_system
            captured["source_order_id"] = obj.source_order_id
        original_add(self, obj)

    monkeypatch.setattr(_FakeDb, "add", _tracking_add)

    resp = client.post(
        "/api/orders",
        json={
            "customer_id": 42,
            "items": [{"product_id": 1, "quantity": 1, "unit_price": 1.0}],
            "source_system": "octo-drone-shop",
            "source_order_id": "99",
            "idempotency_token": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert resp.status_code == 200
    assert captured["source_system"] == "octo-drone-shop"
    assert captured["source_order_id"] == "99"
