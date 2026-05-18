"""Drone Shop Java app-server sidecar client tests."""

from __future__ import annotations

import pytest

from server.modules import java_app_server


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, *, timeout: float, headers: dict[str, str]) -> None:
        self.timeout = timeout
        self.headers = headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        self.calls.append({"method": "GET", "url": url, "headers": dict(self.headers)})
        return _FakeResponse({"status": "up"})

    async def post(self, url: str, json: dict):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": dict(self.headers)})
        return _FakeResponse({"decision": "approved", "risk_score": 17, "latency_ms": 12})


class _FakeErrorAsyncClient(_FakeAsyncClient):
    async def post(self, url: str, json: dict):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": dict(self.headers)})
        request = java_app_server.httpx.Request("POST", url)
        response = java_app_server.httpx.Response(503, request=request, content=b"sidecar unavailable")

        class _ErrorResponse:
            status_code = 503

            def raise_for_status(self) -> None:
                raise java_app_server.httpx.HTTPStatusError("upstream error", request=request, response=response)

            def json(self) -> dict:
                return {}

        return _ErrorResponse()


@pytest.mark.asyncio
async def test_java_app_server_client_propagates_trace_context(monkeypatch) -> None:
    _FakeAsyncClient.calls = []
    metric_calls: list[tuple[str, str, float]] = []
    monkeypatch.setattr(java_app_server.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        java_app_server,
        "current_trace_context",
        lambda: {"trace_id": "a" * 32, "span_id": "b" * 16, "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"},
    )
    monkeypatch.setattr(java_app_server, "current_request_id", lambda: "req-java-client-42")
    monkeypatch.setattr(
        java_app_server.business_metrics,
        "record_java_app_server_call",
        lambda operation, status, latency_ms=0.0: metric_calls.append((operation, status, latency_ms)),
    )

    client = java_app_server.JavaAppServerClient("http://127.0.0.1:18080")
    result = await client.authorize_payment(
        order_id=42,
        amount_minor_units=12999,
        currency="usd",
        customer_email="buyer@example.invalid",
        idempotency_key_hash="deadbeef",
    )

    assert result["status"] == "ok"
    assert result["data"]["decision"] == "approved"
    call = _FakeAsyncClient.calls[0]
    assert call["url"] == "http://127.0.0.1:18080/api/java-apm/payment/authorize"
    assert call["headers"]["traceparent"].startswith("00-")
    assert call["headers"]["X-Correlation-Id"] == "a" * 32
    assert call["headers"]["X-B3-TraceId"] == "a" * 32
    assert call["headers"]["X-B3-SpanId"] == "b" * 16
    assert call["headers"]["X-B3-Sampled"] == "1"
    assert call["headers"]["b3"] == f"{'a' * 32}-{'b' * 16}-1"
    assert call["headers"]["X-Workflow-Id"] == "checkout"
    assert call["headers"]["X-Workflow-Step"] == "payment-processor-authorization"
    assert call["headers"]["X-Request-Id"] == "req-java-client-42"
    assert call["json"]["order_id"] == 42
    assert call["json"]["customer_email_domain"] == "example.invalid"
    assert metric_calls
    assert metric_calls[0][1] == "ok"


@pytest.mark.asyncio
async def test_java_app_server_client_sends_token_safe_payment_rail_context(monkeypatch) -> None:
    _FakeAsyncClient.calls = []
    captured_logs: list[dict] = []
    monkeypatch.setattr(java_app_server.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        java_app_server,
        "push_log",
        lambda _level, _message, **fields: captured_logs.append(fields),
    )

    client = java_app_server.JavaAppServerClient("http://127.0.0.1:18080")
    await client.authorize_payment(
        order_id=91,
        amount_minor_units=489900,
        currency="usd",
        customer_email="wallet.buyer@example.invalid",
        idempotency_key_hash="hash-123",
        payment_method="google_pay",
        payment_network="mastercard",
        payment_gateway_request_id="pgw-91-test",
        gateway_provider="cybersource-compatible-simulator",
        wallet_type="google_pay",
        wallet_provider="google_pay",
        wallet_tokenization_type="PAYMENT_GATEWAY",
        wallet_token_hash="tokhash-safe",
        card_brand="mastercard",
        card_last4="4444",
        card_fingerprint="fingerprint-safe",
        billing_postal_code="10001",
        card_cvv_present=True,
        verification_decision="approved",
        risk_reasons="",
    )

    payload = _FakeAsyncClient.calls[0]["json"]
    assert payload["payment_method"] == "google_pay"
    assert payload["payment_network"] == "mastercard"
    assert payload["payment_gateway_request_id"] == "pgw-91-test"
    assert payload["gateway_provider"] == "cybersource-compatible-simulator"
    assert payload["wallet_tokenization_type"] == "PAYMENT_GATEWAY"
    assert payload["wallet_token_hash"] == "tokhash-safe"
    assert payload["card_brand"] == "mastercard"
    assert payload["card_last4"] == "4444"
    assert payload["card_cvv_present"] is True
    assert "wallet.buyer@example.invalid" not in str(payload)
    assert "4111111111111111" not in str(payload)
    assert captured_logs[-1]["payment.gateway.request_id"] == "pgw-91-test"
    assert captured_logs[-1]["java_apm.service.name"] == "octo-java-app-server"
    assert captured_logs[-1]["payment.processor.name"] == "octo-java-app-server"
    assert captured_logs[-1]["peer.service"] == "octo-java-app-server"
    assert captured_logs[-1]["payment.method"] == "google_pay"
    assert captured_logs[-1]["payment.network"] == "mastercard"
    assert captured_logs[-1]["payment.amount_minor_units"] == 489900
    assert captured_logs[-1]["payment.currency"] == "usd"
    assert captured_logs[-1]["payment.wallet.token_hash"] == "tokhash-safe"
    assert captured_logs[-1]["payment.card_last4"] == "4444"
    assert captured_logs[-1]["workflow.id"] == "checkout"
    assert captured_logs[-1]["workflow.step"] == "payment-processor-authorization"


@pytest.mark.asyncio
async def test_java_app_server_client_degrades_when_disabled() -> None:
    client = java_app_server.JavaAppServerClient("")

    result = await client.health()

    assert result == {"status": "disabled", "reason": "JAVA_APM_SERVICE_URL not configured"}


@pytest.mark.asyncio
async def test_java_app_server_client_logs_upstream_error_type_for_rules(monkeypatch) -> None:
    _FakeErrorAsyncClient.calls = []
    captured_logs: list[dict] = []
    monkeypatch.setattr(java_app_server.httpx, "AsyncClient", _FakeErrorAsyncClient)
    monkeypatch.setattr(
        java_app_server,
        "push_log",
        lambda _level, _message, **fields: captured_logs.append(fields),
    )

    client = java_app_server.JavaAppServerClient("http://127.0.0.1:18080")
    result = await client.authorize_payment(
        order_id=94,
        amount_minor_units=119900,
        currency="usd",
        customer_email="buyer@example.invalid",
        payment_gateway_request_id="pgw-94-error",
        payment_method="credit_card",
        payment_network="visa",
    )

    assert result["status"] == "upstream_error"
    assert captured_logs[-1]["java_apm.path"] == "/api/java-apm/payment/authorize"
    assert captured_logs[-1]["java_apm.status_code"] == 503
    assert captured_logs[-1]["java_apm.error_type"] == "HTTPStatusError"
    assert captured_logs[-1]["java_apm.service.name"] == "octo-java-app-server"
    assert captured_logs[-1]["payment.gateway.request_id"] == "pgw-94-error"


@pytest.mark.asyncio
async def test_java_app_server_client_allows_apm_error_and_attack_scenarios(monkeypatch) -> None:
    _FakeAsyncClient.calls = []
    captured_attrs: list[dict] = []
    captured_logs: list[dict] = []
    monkeypatch.setattr(java_app_server.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        java_app_server,
        "apply_span_attributes",
        lambda _span, attrs: captured_attrs.append(dict(attrs)),
    )
    monkeypatch.setattr(
        java_app_server,
        "push_log",
        lambda _level, _message, **fields: captured_logs.append(fields),
    )

    client = java_app_server.JavaAppServerClient("http://127.0.0.1:18080")
    await client.simulate("external-error", {"status_code": 503})
    await client.simulate("sql-error", {"error_code": "ora-00942"})
    await client.simulate(
        "attack",
        {
            "technique_id": "T1059",
            "attack_id": "attack-123",
            "run_id": "run-123",
            "request_id": "req-123",
            "api_gateway_request_id": "gw-123",
            "api_gateway_route": "/api/shop/attack/simulate",
            "api_gateway_action": "allow",
        },
    )

    assert [call["url"] for call in _FakeAsyncClient.calls] == [
        "http://127.0.0.1:18080/api/java-apm/simulate/external-error",
        "http://127.0.0.1:18080/api/java-apm/simulate/sql-error",
        "http://127.0.0.1:18080/api/java-apm/simulate/attack",
    ]
    assert captured_attrs[-1]["security.attack.id"] == "attack-123"
    assert captured_attrs[-1]["run_id"] == "run-123"
    assert captured_attrs[-1]["request_id"] == "req-123"
    assert captured_attrs[-1]["oci.api_gateway.request_id"] == "gw-123"
    assert captured_attrs[-1]["oci.api_gateway.route"] == "/api/shop/attack/simulate"
    assert captured_attrs[-1]["oci.api_gateway.action"] == "allow"
    assert captured_logs[-1]["security.attack.id"] == "attack-123"
    assert captured_logs[-1]["oci.api_gateway.request_id"] == "gw-123"
