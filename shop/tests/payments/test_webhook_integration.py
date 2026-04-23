"""Integration test for the payments webhook route.

Exercises the full path:

    POST /api/payments/webhooks/{provider}
      ─► registry.get_provider  (stubbed)
      ─► provider.verify_webhook  (stubbed)
      ─► _find_order_by_provider_reference  (in-memory stub)
      ─► state_machine.transition  (REAL — this is the point)
      ─► order.status mutation + emit_order_state_change  (observed)

Unlike the unit tests in test_order_state_machine.py (which only call
``transition`` directly) and test_stripe.py (which mocks the adapter
alone), this test fires through the FastAPI router to validate the
glue in webhooks.py.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.modules.payments.base import (
    InvalidSignature,
    PaymentEventKind,
    WebhookEvent,
)
from server.modules.payments.state_machine import OrderState


@dataclass
class _FakeOrder:
    id: int
    status: str
    payment_provider_reference: str


class _FakeDBSession:
    """Minimal async-context + execute/commit surface the route needs."""

    def __init__(self, order: _FakeOrder | None):
        self._order = order
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        order = self._order

        class _Result:
            def scalar_one_or_none(self_inner):
                return order

        return _Result()

    async def commit(self):
        self.commits += 1


class _FakeProvider:
    name = "stripe"

    def __init__(self, *, event_kind: PaymentEventKind, invalid_sig: bool = False):
        self._kind = event_kind
        self._invalid_sig = invalid_sig

    def verify_webhook(self, *, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        if self._invalid_sig:
            raise InvalidSignature("bad signature")
        return WebhookEvent(
            provider=self.name,
            provider_event_id="evt_test_1",
            kind=self._kind,
            provider_reference="pi_test_ref",
            amount_minor_units=12999,
            currency="usd",
            raw_payload={"id": "evt_test_1"},
        )


def _build_app(monkeypatch, *, order: _FakeOrder | None, provider: _FakeProvider | None):
    from server.modules.payments import webhooks

    db = _FakeDBSession(order)

    # Stub get_db() used inside the route.
    import server.database as database_module

    def _fake_get_db():
        return db

    monkeypatch.setattr(database_module, "get_db", _fake_get_db, raising=False)

    # Stub registry.get_provider.
    import server.modules.payments.registry as registry_module

    def _fake_get_provider(name: str):
        if provider is None or name != provider.name:
            return None
        return provider

    monkeypatch.setattr(registry_module, "get_provider", _fake_get_provider)

    # Capture emit_order_state_change calls.
    emitted: list[dict[str, Any]] = []
    import server.modules.payments.events as events_module

    def _fake_emit(**kwargs):
        emitted.append(kwargs)

    monkeypatch.setattr(events_module, "emit_order_state_change", _fake_emit)
    monkeypatch.setattr(webhooks, "emit_order_state_change", _fake_emit)

    app = FastAPI()
    app.include_router(webhooks.router)
    return TestClient(app), db, emitted


def test_webhook_unknown_provider_501(monkeypatch) -> None:
    client, _, _ = _build_app(monkeypatch, order=None, provider=None)
    r = client.post("/api/payments/webhooks/stripe", content=b"{}")
    assert r.status_code == 501


def test_webhook_invalid_signature_400(monkeypatch) -> None:
    provider = _FakeProvider(event_kind=PaymentEventKind.SUCCEEDED, invalid_sig=True)
    client, db, emitted = _build_app(monkeypatch, order=None, provider=provider)
    r = client.post("/api/payments/webhooks/stripe", content=b"{}")
    assert r.status_code == 400
    assert db.commits == 0
    assert emitted == []


def test_webhook_unknown_order_404(monkeypatch) -> None:
    provider = _FakeProvider(event_kind=PaymentEventKind.SUCCEEDED)
    client, db, emitted = _build_app(monkeypatch, order=None, provider=provider)
    r = client.post("/api/payments/webhooks/stripe", content=b"{}")
    assert r.status_code == 404
    assert db.commits == 0
    assert emitted == []


def test_webhook_pending_event_acks_without_transition(monkeypatch) -> None:
    order = _FakeOrder(id=100, status=OrderState.PAYMENT_PENDING.value, payment_provider_reference="pi_test_ref")
    provider = _FakeProvider(event_kind=PaymentEventKind.PENDING)
    client, db, emitted = _build_app(monkeypatch, order=order, provider=provider)
    r = client.post("/api/payments/webhooks/stripe", content=b"{}")
    assert r.status_code == 200
    assert order.status == OrderState.PAYMENT_PENDING.value
    assert db.commits == 0
    assert emitted == []


def test_webhook_succeeded_drives_payment_pending_to_paid(monkeypatch) -> None:
    order = _FakeOrder(id=100, status=OrderState.PAYMENT_PENDING.value, payment_provider_reference="pi_test_ref")
    provider = _FakeProvider(event_kind=PaymentEventKind.SUCCEEDED)
    client, db, emitted = _build_app(monkeypatch, order=order, provider=provider)

    r = client.post("/api/payments/webhooks/stripe", content=b"{}")

    assert r.status_code == 200
    assert order.status == OrderState.PAID.value
    assert db.commits == 1
    assert len(emitted) == 1
    evt = emitted[0]
    assert evt["order_id"] == 100
    assert evt["previous_state"] == OrderState.PAYMENT_PENDING
    assert evt["new_state"] == OrderState.PAID
    assert evt["provider"] == "stripe"
    assert evt["provider_reference"] == "pi_test_ref"
    assert evt["amount_minor_units"] == 12999
    assert evt["currency"] == "usd"


def test_webhook_illegal_transition_acks_without_mutation(monkeypatch) -> None:
    # Order already PAID — SUCCEEDED event would be illegal.
    order = _FakeOrder(id=100, status=OrderState.PAID.value, payment_provider_reference="pi_test_ref")
    provider = _FakeProvider(event_kind=PaymentEventKind.SUCCEEDED)
    client, db, emitted = _build_app(monkeypatch, order=order, provider=provider)

    r = client.post("/api/payments/webhooks/stripe", content=b"{}")

    # Still 200 — we ack so the provider stops retrying.
    assert r.status_code == 200
    assert order.status == OrderState.PAID.value
    assert db.commits == 0
    assert emitted == []


def test_webhook_refunded_from_paid_is_legal(monkeypatch) -> None:
    order = _FakeOrder(id=100, status=OrderState.PAID.value, payment_provider_reference="pi_test_ref")
    provider = _FakeProvider(event_kind=PaymentEventKind.REFUNDED)
    client, db, emitted = _build_app(monkeypatch, order=order, provider=provider)

    r = client.post("/api/payments/webhooks/stripe", content=b"{}")

    assert r.status_code == 200
    assert order.status == OrderState.REFUNDED.value
    assert db.commits == 1
    assert len(emitted) == 1
    assert emitted[0]["new_state"] == OrderState.REFUNDED
