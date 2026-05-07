"""OCI API Gateway observability helpers for edge detection demos.

The helpers model route-policy outcomes without needing a live OCI API Gateway.
They emit the same low-cardinality fields the attack lab needs for APM spans,
structured logs, Log Analytics saved searches, and business metrics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
import os
from typing import Any, Mapping


_DEFAULT_GATEWAY_NAME = "octo-public-api-gateway"
_DEFAULT_DEPLOYMENT_ID = os.getenv("API_GATEWAY_DEMO_DEPLOYMENT_ID", "demo-api-gateway-deployment")
_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
})

_SCENARIOS: dict[str, dict[str, Any]] = {
    "allow": {
        "action": "allow",
        "policy_decision": "suspicious_burst_observed",
        "http_status_code": 200,
        "attack_type": "api_gateway_policy_detection",
        "severity": "high",
        "threat_signal": "suspicious_burst",
        "rate_limit": 60,
        "rate_remaining": 1,
    },
    "rate_limit": {
        "action": "throttle",
        "policy_decision": "rate_limit_exceeded",
        "http_status_code": 429,
        "attack_type": "api_gateway_rate_limit",
        "severity": "high",
        "threat_signal": "quota_exhaustion",
        "rate_limit": 60,
        "rate_remaining": 0,
    },
    "auth_failure": {
        "action": "deny",
        "policy_decision": "auth_policy_failed",
        "http_status_code": 401,
        "attack_type": "api_gateway_auth_failure",
        "severity": "high",
        "threat_signal": "invalid_token",
        "rate_limit": 60,
        "rate_remaining": 42,
    },
    "backend_error": {
        "action": "backend_error",
        "policy_decision": "upstream_unhealthy",
        "http_status_code": 502,
        "attack_type": "api_gateway_backend_error",
        "severity": "medium",
        "threat_signal": "backend_error",
        "rate_limit": 60,
        "rate_remaining": 24,
    },
    "route_not_found": {
        "action": "deny",
        "policy_decision": "route_not_found",
        "http_status_code": 404,
        "attack_type": "api_gateway_route_probe",
        "severity": "medium",
        "threat_signal": "unknown_route_probe",
        "rate_limit": 60,
        "rate_remaining": 39,
    },
}


@dataclass(frozen=True)
class ApiGatewayObservation:
    request_id: str
    name: str
    deployment_id: str
    scope: str
    route: str
    route_id: str
    route_family: str
    http_method: str
    action: str
    policy_decision: str
    http_status_code: int
    latency_ms: int
    source_ip: str
    attack_type: str
    severity: str
    threat_signal: str
    rate_limit: int
    rate_remaining: int
    headers: Mapping[str, str] = field(default_factory=dict)

    def log_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "oci.api_gateway.name": self.name,
            "oci.api_gateway.deployment_id": self.deployment_id,
            "oci.api_gateway.scope": self.scope,
            "oci.api_gateway.route": self.route,
            "oci.api_gateway.route_id": self.route_id,
            "oci.api_gateway.route_family": self.route_family,
            "oci.api_gateway.request_id": self.request_id,
            "oci.api_gateway.action": self.action,
            "oci.api_gateway.policy.decision": self.policy_decision,
            "oci.api_gateway.latency_ms": self.latency_ms,
            "oci.api_gateway.rate_limit.limit": self.rate_limit,
            "oci.api_gateway.rate_limit.remaining": self.rate_remaining,
            "oci.api_gateway.threat_signal": self.threat_signal,
            "http.method": self.http_method,
            "http.route": self.route,
            "http.url.path": self.route,
            "http.status_code": self.http_status_code,
            "client.address": self.source_ip,
            "source.ip": self.source_ip,
            "network.protocol.name": "https",
            "security.attack.detected": True,
            "security.attack.type": self.attack_type,
            "security.attack.severity": self.severity,
        }
        fields.update(_safe_header_fields(self.headers))
        return fields

    def to_response(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "name": self.name,
            "deployment_id": self.deployment_id,
            "scope": self.scope,
            "route": self.route,
            "route_id": self.route_id,
            "route_family": self.route_family,
            "action": self.action,
            "policy_decision": self.policy_decision,
            "http_status_code": self.http_status_code,
            "latency_ms": self.latency_ms,
            "threat_signal": self.threat_signal,
            "rate_limit": self.rate_limit,
            "rate_remaining": self.rate_remaining,
        }


def build_api_gateway_observation(
    *,
    request_id: object | None = None,
    source_ip: object | None = None,
    route: object | None = None,
    route_id: object | None = None,
    scenario: object | None = None,
    scope: object | None = None,
    name: object | None = None,
    deployment_id: object | None = None,
    http_method: object | None = None,
    latency_ms: object | None = None,
    headers: Mapping[str, object] | None = None,
) -> ApiGatewayObservation:
    normalized_scenario = _clean_token(scenario, fallback="allow", limit=32)
    model = _SCENARIOS.get(normalized_scenario, _SCENARIOS["allow"])
    safe_route = _clean_route(route or "/api/shop/attack/simulate")
    gateway_scope = _clean_token(scope, fallback="public", limit=24)

    return ApiGatewayObservation(
        request_id=_clean_text(request_id, fallback=f"gw-{uuid.uuid4().hex[:16]}", limit=80),
        name=_clean_text(name, fallback=_DEFAULT_GATEWAY_NAME, limit=80),
        deployment_id=_clean_text(deployment_id, fallback=_DEFAULT_DEPLOYMENT_ID, limit=120),
        scope=gateway_scope,
        route=safe_route,
        route_id=_clean_token(route_id, fallback=_default_route_id(gateway_scope, safe_route), limit=80),
        route_family=_route_family(safe_route),
        http_method=_clean_token(http_method, fallback="POST", limit=12).upper(),
        action=str(model["action"]),
        policy_decision=str(model["policy_decision"]),
        http_status_code=int(model["http_status_code"]),
        latency_ms=_positive_int(latency_ms, fallback=17, limit=30000),
        source_ip=_clean_text(source_ip, fallback="203.0.113.77", limit=48),
        attack_type=str(model["attack_type"]),
        severity=str(model["severity"]),
        threat_signal=str(model["threat_signal"]),
        rate_limit=int(model["rate_limit"]),
        rate_remaining=int(model["rate_remaining"]),
        headers=_normalize_headers(headers or {}),
    )


def supported_api_gateway_scenarios() -> list[str]:
    return list(_SCENARIOS)


def _clean_text(value: object, *, fallback: str, limit: int) -> str:
    raw = str(value or fallback).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    normalized = " ".join(raw.split())
    return (normalized or fallback)[:limit]


def _clean_token(value: object, *, fallback: str, limit: int) -> str:
    raw = _clean_text(value, fallback=fallback, limit=limit).lower()
    token = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    return (token.strip("._-") or fallback)[:limit]


def _clean_route(value: object) -> str:
    route = _clean_text(value, fallback="/api/shop/attack/simulate", limit=160)
    if not route.startswith("/"):
        route = f"/{route}"
    if "?" in route:
        route = route.split("?", 1)[0]
    return route or "/"


def _positive_int(value: object, *, fallback: int, limit: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(parsed, limit))


def _default_route_id(scope: str, route: str) -> str:
    return _clean_token(f"{scope}-{route.strip('/').replace('/', '-') or 'root'}", fallback=f"{scope}-api", limit=80)


def _route_family(route: str) -> str:
    if "/attack" in route:
        return "shop_attack"
    if "/checkout" in route or "/payment" in route:
        return "checkout"
    if route.startswith("/api/admin") or "/crm" in route:
        return "admin"
    if "/java-apm" in route or "/sidecar" in route:
        return "java_app_server"
    if route.startswith("/api/shop"):
        return "shop_api"
    return "api"


def _normalize_headers(headers: Mapping[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        safe_key = _clean_header_name(key)
        if not safe_key:
            continue
        if safe_key in _SENSITIVE_HEADERS:
            normalized[safe_key] = "<redacted>"
        else:
            normalized[safe_key] = _clean_text(value, fallback="", limit=180)
    return normalized


def _safe_header_fields(headers: Mapping[str, str]) -> dict[str, str]:
    return {f"http.request.header.{key.replace('-', '_')}": value for key, value in headers.items()}


def _clean_header_name(value: object) -> str:
    raw = str(value or "").strip().lower()
    return "".join(ch for ch in raw if ch.isalnum() or ch == "-")[:80]
