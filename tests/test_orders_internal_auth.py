from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server import auth_security
from server.modules import orders as orders_module


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/orders",
        "headers": raw_headers,
    }
    return Request(scope)


class _DummySpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_attribute(self, name: str, value) -> None:
        return None


class _DummyTracer:
    def start_as_current_span(self, name: str) -> _DummySpan:
        return _DummySpan()


class _FakeResult:
    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list:
        return []


class _FakeDb:
    async def execute(self, query):
        return _FakeResult()


class _FakeDbContext:
    async def __aenter__(self) -> _FakeDb:
        return _FakeDb()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def test_require_authenticated_or_internal_service_rejects_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(auth_security.cfg, "internal_service_key", "shared-key")

    with pytest.raises(HTTPException) as exc:
        auth_security.require_authenticated_or_internal_service(_request())

    assert exc.value.status_code == 401


def test_list_orders_allows_internal_service_key(monkeypatch) -> None:
    monkeypatch.setattr(auth_security.cfg, "internal_service_key", "shared-key")
    monkeypatch.setattr(orders_module, "get_tracer", lambda: _DummyTracer())
    monkeypatch.setattr(orders_module, "get_db", lambda: _FakeDbContext())

    payload = asyncio.run(
        orders_module.list_orders(
            _request({"X-Internal-Service-Key": "shared-key"}),
            limit=10,
        )
    )

    assert payload["orders"] == []
