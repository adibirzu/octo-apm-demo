"""KG-025 — shop catalog cache read-through tests.

Stubs the DB fetch + cache adapter so we verify the read-through
pattern without pulling in a real Redis or ATP.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTO_CACHE_URL", raising=False)


async def test_list_products_no_cache_goes_to_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import products

    called: dict[str, Any] = {}

    async def _fake_db(limit: int) -> list[dict[str, Any]]:
        called["limit"] = limit
        return [{"id": 1, "name": "X", "price": 1.0, "stock": 1, "category": "c"}]

    monkeypatch.setattr(products, "_list_products_from_db", _fake_db)

    items = await products._list_products_for_public_api(limit=3)
    assert items[0]["id"] == 1
    assert called["limit"] == 3


async def test_cache_hit_short_circuits_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import products

    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test:6379")

    class _FakeCache:
        async def get(self, ns, key):
            return json.dumps([{"id": 99, "name": "cached", "price": 9.99, "stock": 2, "category": "c"}]).encode()

        async def set(self, *a, **kw):
            return True

        async def aclose(self):
            return None

    async def _fake_cache_getter():
        return _FakeCache()

    db_called = False

    async def _fake_db(limit: int):
        nonlocal db_called
        db_called = True
        return []

    monkeypatch.setattr(products, "_get_cache", _fake_cache_getter)
    monkeypatch.setattr(products, "_list_products_from_db", _fake_db)

    items = await products._list_products_for_public_api(limit=20)
    assert items[0]["id"] == 99
    assert db_called is False, "cache hit must NOT call the DB"


async def test_cache_miss_populates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import products

    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test:6379")

    set_calls: list[tuple] = []

    class _FakeCache:
        async def get(self, ns, key):
            return None  # miss

        async def set(self, ns, key, value, *, ttl_seconds):
            set_calls.append((ns, key, ttl_seconds))
            return True

        async def aclose(self):
            return None

    async def _fake_cache_getter():
        return _FakeCache()

    async def _fake_db(limit: int):
        return [{"id": 7, "name": "Y", "price": 2.0, "stock": 5, "category": "d"}]

    monkeypatch.setattr(products, "_get_cache", _fake_cache_getter)
    monkeypatch.setattr(products, "_list_products_from_db", _fake_db)

    items = await products._list_products_for_public_api(limit=20)
    assert items[0]["id"] == 7
    assert len(set_calls) == 1
    assert set_calls[0][0] == "shop:catalog"
    assert set_calls[0][2] == 300  # _CATALOG_TTL_SECONDS
