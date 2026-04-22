"""KG-034 — async order-sync publisher tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTO_ASYNC_ORDER_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("OCTO_ORDER_STREAM_REDIS_URL", raising=False)


async def _call(**overrides):
    from server.modules.order_sync_async import publish_order_for_async_sync

    defaults = dict(
        order_id=100,
        customer_id=42,
        customer_email="b@example.invalid",
        items=[{"product_id": 1, "quantity": 1, "unit_price": 1.0}],
        source_order_id="100",
        idempotency_token="uuid-1",
    )
    defaults.update(overrides)
    return await publish_order_for_async_sync(**defaults)


async def test_feature_flag_off_by_default() -> None:
    result = await _call()
    assert result["queued"] is False
    assert "disabled" in result["reason"]


async def test_flag_on_but_no_publisher_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_ASYNC_ORDER_SYNC_ENABLED", "true")
    # No OCTO_ORDER_STREAM_REDIS_URL → publisher is None
    result = await _call()
    assert result["queued"] is False
    assert "not configured" in result["reason"]


async def test_happy_path_returns_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_ASYNC_ORDER_SYNC_ENABLED", "true")
    monkeypatch.setenv("OCTO_ORDER_STREAM_REDIS_URL", "redis://test:6379")

    published: dict[str, Any] = {}

    class _FakePub:
        async def publish(self, *, stream, payload, run_id, workflow_id, trace_id, span_id):
            published["stream"] = stream
            published["payload"] = payload
            published["workflow_id"] = workflow_id
            return "1-0"

        async def aclose(self):
            return None

    async def _fake_getter():
        return _FakePub()

    from server.modules import order_sync_async

    monkeypatch.setattr(order_sync_async, "_get_publisher", _fake_getter)

    result = await _call(run_id="run-xyz")
    assert result["queued"] is True
    assert result["event_id"] == "1-0"
    assert published["stream"] == "octo.orders.to-sync"
    assert published["workflow_id"] == "shop.order.sync.async"
    assert published["payload"]["source_system"] == "octo-drone-shop"
    assert published["payload"]["idempotency_token"] == "uuid-1"


async def test_publish_exception_returns_queued_false_not_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_ASYNC_ORDER_SYNC_ENABLED", "true")
    monkeypatch.setenv("OCTO_ORDER_STREAM_REDIS_URL", "redis://test:6379")

    class _BoomPub:
        async def publish(self, *a, **kw):
            raise RuntimeError("redis down")

        async def aclose(self):
            return None

    async def _fake_getter():
        return _BoomPub()

    from server.modules import order_sync_async

    monkeypatch.setattr(order_sync_async, "_get_publisher", _fake_getter)

    result = await _call()
    assert result["queued"] is False
    assert "publish failed" in result["reason"]
