"""Client for the Java OCI APM app-server sidecar.

The sidecar is intentionally optional. When it is configured, Drone Shop
checkout and simulations make real HTTP calls to a Java/Spring service so OCI
APM can link the Python trace to a supported Java app-server/JVM segment.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from opentelemetry import trace

from server.config import cfg
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes, current_trace_context
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.security.request_id import current_request_id


def _email_domain(email: str) -> str:
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    if not domain or domain == email:
        return "unknown"
    return "".join(ch for ch in domain if ch.isalnum() or ch in "._-")[:120] or "unknown"


def _workflow_defaults(path: str) -> tuple[str, str]:
    if path == "/api/java-apm/payment/verify":
        return "checkout", "payment-antifraud-verification"
    if path == "/api/java-apm/payment/authorize":
        return "checkout", "payment-processor-authorization"
    if path == "/api/java-apm/quote":
        return "checkout", "quote"
    if path.startswith("/api/java-apm/simulate/"):
        return "simulation", path.rsplit("/", 1)[-1] or "java-simulation"
    return "", ""


def _safe_header_value(value: object, limit: int = 128) -> str:
    raw = str(value or "").strip()
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in "._:@+,-")
    return safe[:limit]


def _outbound_workflow_context(path: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    default_workflow, default_step = _workflow_defaults(path)
    workflow_id = _safe_header_value(payload.get("workflow_id") or default_workflow, 80)
    workflow_step = _safe_header_value(payload.get("workflow_step") or default_step, 80)
    request_id = _safe_header_value(payload.get("request_id") or current_request_id() or "", 128)
    run_id = _safe_header_value(payload.get("run_id") or "", 128)
    return {
        key: value
        for key, value in {
            "request_id": request_id,
            "workflow.id": workflow_id,
            "workflow.step": workflow_step,
            "run_id": run_id,
        }.items()
        if value
    }


def _outbound_headers(path: str = "", payload: dict[str, Any] | None = None) -> dict[str, str]:
    trace_ctx = current_trace_context()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Correlation-Id": trace_ctx["trace_id"] or "java-app-server",
    }
    if trace_ctx["traceparent"]:
        headers["traceparent"] = trace_ctx["traceparent"]
    if trace_ctx["trace_id"] and trace_ctx["span_id"]:
        headers["X-B3-TraceId"] = trace_ctx["trace_id"]
        headers["X-B3-SpanId"] = trace_ctx["span_id"]
        headers["X-B3-Sampled"] = "1"
        headers["b3"] = f"{trace_ctx['trace_id']}-{trace_ctx['span_id']}-1"
    outbound_context = _outbound_workflow_context(path, payload)
    header_map = {
        "request_id": "X-Request-Id",
        "workflow.id": "X-Workflow-Id",
        "workflow.step": "X-Workflow-Step",
        "run_id": "X-Run-Id",
    }
    for field_name, header_name in header_map.items():
        if outbound_context.get(field_name):
            headers[header_name] = outbound_context[field_name]
    return headers


def _payload_correlation_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    mapping = {
        "workflow_id": "workflow.id",
        "workflow_step": "workflow.step",
        "attack_id": "security.attack.id",
        "run_id": "run_id",
        "request_id": "request_id",
        "technique_id": "mitre.technique_id",
        "tactic": "mitre.tactic",
        "source_ip": "client.address",
        "api_gateway_request_id": "oci.api_gateway.request_id",
        "api_gateway_route": "oci.api_gateway.route",
        "api_gateway_action": "oci.api_gateway.action",
        "api_gateway_policy_decision": "oci.api_gateway.policy.decision",
        "order_id": "orders.order_id",
        "amount_minor_units": "payment.amount_minor_units",
        "currency": "payment.currency",
        "payment_method": "payment.method",
        "payment_network": "payment.network",
        "payment_gateway_request_id": "payment.gateway.request_id",
        "gateway_provider": "payment.gateway.provider",
        "wallet_type": "payment.wallet_type",
        "wallet_provider": "payment.wallet.provider",
        "wallet_tokenization_type": "payment.wallet.tokenization_type",
        "wallet_token_hash": "payment.wallet.token_hash",
        "card_brand": "payment.card_brand",
        "card_last4": "payment.card_last4",
        "verification_decision": "payment.verification.decision",
        "context_risk_score": "payment.risk_score",
    }
    fields: dict[str, Any] = {}
    for source_key, target_key in mapping.items():
        value = payload.get(source_key)
        if value is None or value == "":
            continue
        fields[target_key] = str(value)[:180] if isinstance(value, str) else value
    return fields


def _java_component_fields() -> dict[str, str]:
    service_name = cfg.java_apm_service_name or "octo-java-app-server"
    return {
        "peer.service": service_name,
        "java_apm.service.name": service_name,
        "payment.processor.name": service_name,
    }


def _safe_payment_text(value: object, limit: int = 120) -> str:
    raw = str(value or "").strip()
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in " ._:@+-,")
    return safe[:limit]


def _payment_rail_payload(
    *,
    payment_method: str = "",
    payment_network: str = "",
    payment_gateway_request_id: str = "",
    gateway_provider: str = "",
    wallet_type: str = "",
    wallet_provider: str = "",
    wallet_tokenization_type: str = "",
    wallet_token_hash: str = "",
    card_brand: str = "",
    card_last4: str = "",
    card_fingerprint: str = "",
    card_exp_month: int | None = None,
    card_exp_year: int | None = None,
    billing_postal_code: str = "",
    card_cvv_present: bool | None = None,
    verification_decision: str = "",
    risk_reasons: str = "",
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "payment_method": _safe_payment_text(payment_method, 50),
        "payment_network": _safe_payment_text(payment_network, 40).lower(),
        "payment_gateway_request_id": _safe_payment_text(payment_gateway_request_id, 128),
        "gateway_provider": _safe_payment_text(gateway_provider, 100),
        "wallet_type": _safe_payment_text(wallet_type, 40),
        "wallet_provider": _safe_payment_text(wallet_provider, 40),
        "wallet_tokenization_type": _safe_payment_text(wallet_tokenization_type, 40),
        "wallet_token_hash": _safe_payment_text(wallet_token_hash, 80),
        "card_brand": _safe_payment_text(card_brand, 40).lower(),
        "card_last4": _safe_payment_text(card_last4, 4),
        "card_fingerprint": _safe_payment_text(card_fingerprint, 80),
        "billing_postal_code": _safe_payment_text(billing_postal_code, 24),
        "verification_decision": _safe_payment_text(verification_decision, 40),
        "risk_reasons": _safe_payment_text(risk_reasons, 500),
    }
    if card_exp_month is not None:
        fields["card_exp_month"] = int(card_exp_month or 0)
    if card_exp_year is not None:
        fields["card_exp_year"] = int(card_exp_year or 0)
    if card_cvv_present is not None:
        fields["card_cvv_present"] = bool(card_cvv_present)
    return {key: value for key, value in fields.items() if value != ""}


class JavaAppServerClient:
    """Small async HTTP client with safe disabled/unreachable fallbacks."""

    def __init__(self, base_url: str | None = None, *, timeout: float | None = None) -> None:
        self.base_url = (base_url if base_url is not None else cfg.java_apm_service_url).rstrip("/")
        self.timeout = timeout if timeout is not None else cfg.java_apm_timeout_seconds

    @property
    def service_name(self) -> str:
        return cfg.java_apm_service_name or "octo-java-app-server"

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/java-apm/health")

    async def quote(
        self,
        *,
        product_id: int,
        quantity: int,
        base_price_minor_units: int,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/java-apm/quote",
            {
                "product_id": int(product_id),
                "quantity": int(quantity),
                "base_price_minor_units": int(base_price_minor_units),
            },
        )

    async def authorize_payment(
        self,
        *,
        order_id: int,
        amount_minor_units: int,
        currency: str,
        customer_email: str,
        idempotency_key_hash: str = "",
        simulation_mode: str = "",
        payment_method: str = "",
        payment_network: str = "",
        payment_gateway_request_id: str = "",
        gateway_provider: str = "",
        wallet_type: str = "",
        wallet_provider: str = "",
        wallet_tokenization_type: str = "",
        wallet_token_hash: str = "",
        card_brand: str = "",
        card_last4: str = "",
        card_fingerprint: str = "",
        card_exp_month: int | None = None,
        card_exp_year: int | None = None,
        billing_postal_code: str = "",
        card_cvv_present: bool | None = None,
        verification_decision: str = "",
        risk_reasons: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/java-apm/payment/authorize",
            {
                "order_id": int(order_id),
                "amount_minor_units": int(amount_minor_units),
                "currency": (currency or "usd").lower(),
                "customer_email_domain": _email_domain(customer_email),
                "idempotency_key_hash": idempotency_key_hash[:64],
                "simulation_mode": simulation_mode,
                **_payment_rail_payload(
                    payment_method=payment_method,
                    payment_network=payment_network,
                    payment_gateway_request_id=payment_gateway_request_id,
                    gateway_provider=gateway_provider,
                    wallet_type=wallet_type,
                    wallet_provider=wallet_provider,
                    wallet_tokenization_type=wallet_tokenization_type,
                    wallet_token_hash=wallet_token_hash,
                    card_brand=card_brand,
                    card_last4=card_last4,
                    card_fingerprint=card_fingerprint,
                    card_exp_month=card_exp_month,
                    card_exp_year=card_exp_year,
                    billing_postal_code=billing_postal_code,
                    card_cvv_present=card_cvv_present,
                    verification_decision=verification_decision,
                    risk_reasons=risk_reasons,
                ),
            },
        )

    async def verify_payment(
        self,
        *,
        order_id: int,
        amount_minor_units: int,
        currency: str,
        customer_email: str,
        idempotency_key_hash: str = "",
        payment_method: str = "credit_card",
        payment_network: str = "",
        context_risk_score: int = 0,
        risk_reasons: str = "",
        simulation_mode: str = "",
        payment_gateway_request_id: str = "",
        gateway_provider: str = "",
        wallet_type: str = "",
        wallet_provider: str = "",
        wallet_tokenization_type: str = "",
        wallet_token_hash: str = "",
        card_brand: str = "",
        card_last4: str = "",
        card_fingerprint: str = "",
        card_exp_month: int | None = None,
        card_exp_year: int | None = None,
        billing_postal_code: str = "",
        card_cvv_present: bool | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/java-apm/payment/verify",
            {
                "order_id": int(order_id),
                "amount_minor_units": int(amount_minor_units),
                "currency": (currency or "usd").lower(),
                "customer_email_domain": _email_domain(customer_email),
                "idempotency_key_hash": idempotency_key_hash[:64],
                "payment_method": payment_method,
                "payment_network": payment_network,
                "context_risk_score": int(context_risk_score or 0),
                "risk_reasons": risk_reasons[:500],
                "simulation_mode": simulation_mode,
                **_payment_rail_payload(
                    payment_method=payment_method,
                    payment_network=payment_network,
                    payment_gateway_request_id=payment_gateway_request_id,
                    gateway_provider=gateway_provider,
                    wallet_type=wallet_type,
                    wallet_provider=wallet_provider,
                    wallet_tokenization_type=wallet_tokenization_type,
                    wallet_token_hash=wallet_token_hash,
                    card_brand=card_brand,
                    card_last4=card_last4,
                    card_fingerprint=card_fingerprint,
                    card_exp_month=card_exp_month,
                    card_exp_year=card_exp_year,
                    billing_postal_code=billing_postal_code,
                    card_cvv_present=card_cvv_present,
                ),
            },
        )

    async def simulate(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = {"slow", "gc", "cpu", "error", "external-error", "sql-error", "attack"}
        if name not in allowed:
            return {"status": "error", "reason": f"unsupported Java simulation '{name}'"}
        return await self._request("POST", f"/api/java-apm/simulate/{name}", payload or {})

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        operation = f"java_app_server.{method.lower()}.{path.strip('/').replace('/', '.')}"
        if not self.enabled:
            business_metrics.record_java_app_server_call(operation=operation, status="disabled")
            return {"status": "disabled", "reason": "JAVA_APM_SERVICE_URL not configured"}

        tracer = get_tracer()
        started = time.monotonic()
        with tracer.start_as_current_span(operation) as span:
            correlation_fields = _payload_correlation_fields(payload)
            outbound_context = _outbound_workflow_context(path, payload)
            java_component_fields = _java_component_fields()
            apply_span_attributes(
                span,
                {
                    "component": "http",
                    "http.method": method,
                    "http.url": f"{self.base_url}{path}",
                    "java_apm.enabled": True,
                    "app.module": "shop",
                    "app.logical_endpoint": "java_app_server.sidecar",
                    **java_component_fields,
                    **outbound_context,
                    **correlation_fields,
                },
            )
            try:
                async with httpx.AsyncClient(timeout=self.timeout, headers=_outbound_headers(path, payload)) as client:
                    if method == "GET":
                        response = await client.get(f"{self.base_url}{path}")
                    else:
                        response = await client.post(f"{self.base_url}{path}", json=payload or {})
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("java_apm.latency_ms", elapsed_ms)
                response.raise_for_status()
                data = response.json()
                business_metrics.record_java_app_server_call(
                    operation=operation,
                    status="ok",
                    latency_ms=elapsed_ms,
                )
                push_log(
                    "INFO",
                    "Java app-server sidecar call completed",
                    **{
                        "java_apm.path": path,
                        "java_apm.status_code": response.status_code,
                        "java_apm.latency_ms": elapsed_ms,
                        **java_component_fields,
                        **outbound_context,
                        **correlation_fields,
                    },
                )
                return {"status": "ok", "data": data, "latency_ms": elapsed_ms}
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                span.record_exception(exc)
                span.set_attribute("otel.status_code", "ERROR")
                push_log(
                    "WARNING",
                    "Java app-server sidecar unreachable",
                    **{
                        "java_apm.path": path,
                        "java_apm.error_type": type(exc).__name__,
                        "java_apm.latency_ms": elapsed_ms,
                        **java_component_fields,
                        **outbound_context,
                        **correlation_fields,
                    },
                )
                business_metrics.record_java_app_server_call(
                    operation=operation,
                    status="unreachable",
                    latency_ms=elapsed_ms,
                )
                return {"status": "unreachable", "reason": type(exc).__name__, "latency_ms": elapsed_ms}
            except httpx.HTTPStatusError as exc:
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                span.record_exception(exc)
                span.set_attribute("otel.status_code", "ERROR")
                push_log(
                    "WARNING",
                    "Java app-server sidecar returned upstream error",
                    **{
                        "java_apm.path": path,
                        "java_apm.status_code": exc.response.status_code,
                        "java_apm.error_type": type(exc).__name__,
                        "java_apm.latency_ms": elapsed_ms,
                        **java_component_fields,
                        **outbound_context,
                        **correlation_fields,
                    },
                )
                business_metrics.record_java_app_server_call(
                    operation=operation,
                    status="upstream_error",
                    latency_ms=elapsed_ms,
                )
                return {
                    "status": "upstream_error",
                    "upstream_status": exc.response.status_code,
                    "reason": exc.response.text[:300],
                    "latency_ms": elapsed_ms,
                }


def client() -> JavaAppServerClient:
    return JavaAppServerClient()
