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


def _email_domain(email: str) -> str:
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    if not domain or domain == email:
        return "unknown"
    return "".join(ch for ch in domain if ch.isalnum() or ch in "._-")[:120] or "unknown"


def _outbound_headers() -> dict[str, str]:
    trace_ctx = current_trace_context()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Correlation-Id": trace_ctx["trace_id"] or "java-app-server",
    }
    if trace_ctx["traceparent"]:
        headers["traceparent"] = trace_ctx["traceparent"]
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
    }
    fields: dict[str, Any] = {}
    for source_key, target_key in mapping.items():
        value = payload.get(source_key)
        if value is None or value == "":
            continue
        fields[target_key] = str(value)[:180] if isinstance(value, str) else value
    return fields


class JavaAppServerClient:
    """Small async HTTP client with safe disabled/unreachable fallbacks."""

    def __init__(self, base_url: str | None = None, *, timeout: float | None = None) -> None:
        self.base_url = (base_url if base_url is not None else cfg.java_apm_service_url).rstrip("/")
        self.timeout = timeout if timeout is not None else cfg.java_apm_timeout_seconds

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
            apply_span_attributes(
                span,
                {
                    "peer.service": "octo-java-app-server",
                    "component": "http",
                    "http.method": method,
                    "http.url": f"{self.base_url}{path}",
                    "java_apm.enabled": True,
                    "app.module": "shop",
                    "app.logical_endpoint": "java_app_server.sidecar",
                    **correlation_fields,
                },
            )
            try:
                async with httpx.AsyncClient(timeout=self.timeout, headers=_outbound_headers()) as client:
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
                        "java_apm.latency_ms": elapsed_ms,
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
