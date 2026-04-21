"""PR-3 regression: outbound order-sync POST to Enterprise CRM must carry
the X-Internal-Service-Key header and an idempotency_token in the body
so the CRM side can deduplicate retries and reject anonymous callers.

Why: the production failure mode is "CRM_SERVICE_URL misconfigured to a
public endpoint → shop POSTs orders without auth". Network isolation is
not a sufficient control for a multi-tenant deployment.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.modules import integrations


class _FakeResponse:
    def __init__(self, status_code: int = 201, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {"id": 7331}

    def json(self) -> dict[str, Any]:
        return self._payload


class _CaptureClient:
    """Mimics just enough of httpx.AsyncClient to capture the POST call."""

    def __init__(self) -> None:
        self.captured_post: dict[str, Any] = {}
        self.captured_get: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_CaptureClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: D401
        return False

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.captured_get.append({"url": url, **kwargs})
        # _find_crm_customer calls GET /api/customers?email= — return a hit
        return _FakeResponse(
            status_code=200,
            payload={"customers": [{"id": 42, "email": "buyer@example.invalid"}]},
        )

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.captured_post = {"url": url, **kwargs}
        return _FakeResponse(status_code=201)


@pytest.fixture
def capture_client(monkeypatch: pytest.MonkeyPatch) -> _CaptureClient:
    client = _CaptureClient()

    # Patch httpx.AsyncClient used inside integrations
    def _factory(*_args: Any, **_kwargs: Any) -> _CaptureClient:
        return client

    monkeypatch.setattr(integrations.httpx, "AsyncClient", _factory)
    # Stub the circuit breaker to always allow
    monkeypatch.setattr(integrations.crm_breaker, "allow_request", lambda: True)
    monkeypatch.setattr(integrations.crm_breaker, "record_success", lambda: None)
    monkeypatch.setattr(integrations.crm_breaker, "record_failure", lambda: None)
    monkeypatch.setattr(
        integrations.crm_breaker,
        "status",
        lambda: {"state": "CLOSED"},
    )
    # Ensure tracer + push_log don't fail the test
    monkeypatch.setattr(integrations, "push_log", lambda *a, **k: None)

    # Point sync at a fake CRM
    monkeypatch.setenv("ENTERPRISE_CRM_URL", "https://crm.example.invalid")
    integrations.CRM_BASE_URL = "https://crm.example.invalid"
    return client


@pytest.mark.portability
@pytest.mark.security
def test_sync_order_sends_internal_service_key_header(
    capture_client: _CaptureClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integrations.cfg, "internal_service_key", "shared-secret")

    result = asyncio.run(
        integrations.sync_order_to_crm(
            order_id=100, customer_email="buyer@example.invalid", total=49.99
        )
    )
    assert result["synced"] is True
    headers = capture_client.captured_post.get("headers") or {}
    assert headers.get("X-Internal-Service-Key") == "shared-secret", (
        "Outbound CRM order sync must carry the shared key so CRM can "
        "reject anonymous callers."
    )


@pytest.mark.portability
def test_sync_order_omits_header_when_key_not_configured(
    capture_client: _CaptureClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No key configured → no header. Avoid sending an empty string that a
    strict CRM side might trust as a valid key."""
    monkeypatch.setattr(integrations.cfg, "internal_service_key", "")

    asyncio.run(
        integrations.sync_order_to_crm(
            order_id=101, customer_email="buyer@example.invalid", total=1.00
        )
    )
    headers = capture_client.captured_post.get("headers") or {}
    assert "X-Internal-Service-Key" not in headers


@pytest.mark.portability
def test_sync_order_includes_idempotency_token(
    capture_client: _CaptureClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integrations.cfg, "internal_service_key", "shared-secret")

    asyncio.run(
        integrations.sync_order_to_crm(
            order_id=200, customer_email="buyer@example.invalid", total=1.00
        )
    )
    body = capture_client.captured_post.get("json") or {}
    token = body.get("idempotency_token")
    assert token, "order sync payload must include idempotency_token"
    # UUID-ish: at least 16 hex-ish chars, contains a dash
    assert len(token) >= 16 and "-" in token


@pytest.mark.portability
def test_sync_order_idempotency_token_stable_per_order(
    capture_client: _CaptureClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same order_id retried → same idempotency_token (so CRM dedupes)."""
    monkeypatch.setattr(integrations.cfg, "internal_service_key", "k")

    first = asyncio.run(
        integrations.sync_order_to_crm(
            order_id=555, customer_email="buyer@example.invalid", total=1.00
        )
    )
    token_1 = capture_client.captured_post["json"]["idempotency_token"]

    second = asyncio.run(
        integrations.sync_order_to_crm(
            order_id=555, customer_email="buyer@example.invalid", total=1.00
        )
    )
    token_2 = capture_client.captured_post["json"]["idempotency_token"]

    assert first["synced"] and second["synced"]
    assert token_1 == token_2, (
        "retries for the same (order_id, source) must produce a stable "
        "idempotency_token — otherwise CRM cannot deduplicate."
    )
