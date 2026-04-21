from __future__ import annotations

import asyncio
from types import SimpleNamespace

from server import order_sync


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"orders": [{"id": 101, "status": "pending"}]}


def test_fetch_external_orders_includes_internal_service_key(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, *args, headers=None, **kwargs):
            observed["headers"] = headers or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, params=None):
            observed["url"] = url
            observed["params"] = params
            return _FakeResponse()

    monkeypatch.setattr(order_sync.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(
        order_sync,
        "cfg",
        SimpleNamespace(
            drone_shop_internal_key="shared-key",
            external_orders_path="/api/orders",
        ),
    )

    orders = asyncio.run(
        order_sync._fetch_external_orders(
            "http://octo-drone-shop.octo-drone-shop.svc.cluster.local",
            "corr-123",
            25,
        )
    )

    assert observed["headers"]["X-Internal-Service-Key"] == "shared-key"
    assert observed["params"] == {"limit": 25}
    assert orders == [{"id": 101, "status": "pending"}]
