"""Checkout idempotency regression tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.store_service import normalize_checkout_idempotency_key, place_order


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class _FakeDb:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []
        self.order_items: dict[int, list[dict[str, Any]]] = {}
        self.shipments: dict[int, dict[str, Any]] = {}
        self.order_insert_count = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        sql = str(statement)
        params = params or {}

        if "FROM orders WHERE checkout_idempotency_key" in sql:
            lookup_key = params.get("key") or params.get("checkout_idempotency_key")
            for order in self.orders:
                if order["checkout_idempotency_key"] == lookup_key:
                    return _Rows([order])
            return _Rows()

        if "FROM coupons" in sql:
            return _Rows()

        if "INSERT INTO orders" in sql:
            self.order_insert_count += 1
            order = {
                "id": self.order_insert_count,
                "customer_id": params["customer_id"],
                "total": params["total"],
                "status": params["status"],
                "created_at": "2026-05-06T00:00:00",
                "checkout_idempotency_key": params["checkout_idempotency_key"],
            }
            self.orders.append(order)
            return _Rows()

        if "UPDATE orders SET payment_provider" in sql:
            for order in self.orders:
                if order["id"] == params["order_id"]:
                    order.update(
                        {
                            "payment_provider": params["payment_provider"],
                            "payment_provider_reference": params["payment_provider_reference"],
                            "payment_status": params["payment_status"],
                            "status": params["status"],
                        }
                    )
            return _Rows()

        if "INSERT INTO order_items" in sql:
            self.order_items.setdefault(params["order_id"], []).append(
                {
                    "quantity": params["quantity"],
                    "unit_price": params["unit_price"],
                }
            )
            return _Rows()

        if "INSERT INTO shipments" in sql:
            self.shipments[params["order_id"]] = {
                "tracking_number": params["tracking_number"],
                "shipping_cost": params["shipping_cost"],
            }
            return _Rows()

        if "FROM order_items WHERE order_id" in sql:
            items = self.order_items.get(params["order_id"], [])
            subtotal = sum(item["quantity"] * item["unit_price"] for item in items)
            item_count = sum(item["quantity"] for item in items)
            return _Rows([{"subtotal": subtotal, "item_count": item_count}])

        if "FROM shipments WHERE order_id" in sql:
            shipment = self.shipments.get(params["order_id"])
            return _Rows([shipment] if shipment else [])

        return _Rows()


@pytest.mark.parametrize("key", ["abc", "white space", "x" * 129])
def test_checkout_idempotency_key_validation_rejects_unsafe_values(key: str) -> None:
    with pytest.raises(ValueError):
        normalize_checkout_idempotency_key(key)


def test_place_order_reuses_existing_order_for_same_checkout_key() -> None:
    db = _FakeDb()
    customer = {"id": 7, "email": "buyer@example.invalid", "name": "Buyer"}
    items = [
        {
            "product_id": 11,
            "quantity": 2,
            "price": 100.0,
        }
    ]

    first = asyncio.run(
        place_order(
            db,
            customer=customer,
            items=items,
            shipping_address="Dock 1",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440000",
        )
    )
    replay = asyncio.run(
        place_order(
            db,
            customer=customer,
            items=items,
            shipping_address="Dock 1",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440000",
        )
    )

    assert db.order_insert_count == 1
    assert first["order"]["id"] == replay["order"]["id"]
    assert replay["idempotent_replay"] is True
