"""Cross-service integrations and OCI-DEMO topology status."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from opentelemetry import trace

from server.config import cfg
from server.observability.correlation import (
    build_correlation_id,
    current_trace_context,
    outbound_headers,
    service_metadata,
    set_peer_service,
)
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.order_sync import external_orders_base_url, order_security_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _service_name_from_url(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc or urlparse(url).path
    return host.split(":")[0]


def _dns_url(subdomain: str) -> str:
    """Return https://<subdomain>.<domain> if DNS_DOMAIN is set, else empty."""
    if cfg.dns_domain:
        return f"https://{subdomain}.{cfg.dns_domain}"
    return ""


def _configured_dependencies() -> list[dict]:
    return [
        {
            "name": "drone-shop-portal",
            "display_name": "Drone Shop Portal",
            "type": "application",
            "url": _dns_url("shop") or cfg.octo_drone_shop_url or cfg.mushop_cloudnative_url or cfg.octo_apm_cloudnative_url,
            "health_paths": ["/health", "/ready"],
            "drilldown_product": "APM",
        },
        {
            "name": "seven-kingdoms-portal",
            "display_name": "Seven Kingdoms Portal",
            "type": "application",
            "url": _dns_url("portal") or cfg.c22_skp_url,
            "health_paths": ["/health", "/ready"],
            "drilldown_product": "APM / Log Analytics",
        },
        {
            "name": "oci-demo-control-plane",
            "display_name": "OCI-DEMO Control Plane",
            "type": "backend",
            "url": _dns_url("cp") or cfg.oci_demo_control_plane_url,
            "health_paths": ["/health", "/api/health", "/ready"],
            "drilldown_product": "APM",
        },
        {
            "name": "oci-demo-backend",
            "display_name": "OCI-DEMO Backends",
            "type": "backend",
            "url": cfg.oci_demo_backend_url or _dns_url("cp"),
            "health_paths": ["/health", "/api/health", "/ready"],
            "drilldown_product": "Log Analytics",
        },
        {
            "name": "octo-apm-atp",
            "display_name": "OCTO ATP Backend",
            "type": "database",
            "url": "",
            "health_paths": [],
            "configured": bool(cfg.atp_ocid or cfg.atp_connection_name),
            "drilldown_product": "DB Management / OPSI",
        },
    ]


def _drilldown_targets() -> list[dict]:
    return [
        {"name": "OCI APM", "url": cfg.apm_console_url, "configured": bool(cfg.apm_console_url)},
        {"name": "OCI Operations Insights", "url": cfg.opsi_console_url, "configured": bool(cfg.opsi_console_url)},
        {"name": "OCI DB Management", "url": cfg.db_management_console_url, "configured": bool(cfg.db_management_console_url)},
        {"name": "OCI Log Analytics", "url": cfg.log_analytics_console_url, "configured": bool(cfg.log_analytics_console_url)},
    ]


async def _dependency_health(dep: dict, correlation_id: str) -> dict:
    if dep["name"] == "octo-apm-atp":
        return {
            **dep,
            "configured": dep.get("configured", False),
            "status": "configured" if dep.get("configured", False) else "not_configured",
            "database_target": cfg.database_target_label,
            "atp_ocid": cfg.atp_ocid or None,
            "connection_name": cfg.atp_connection_name or None,
        }

    url = dep.get("url") or ""
    configured = bool(url)
    result = {**dep, "configured": configured}
    if not configured:
        result["status"] = "not_configured"
        return result

    tracer = get_tracer()
    with tracer.start_as_current_span(f"integration.health.{dep['name']}") as span:
        span.set_attribute("integration.target_service", dep["name"])
        span.set_attribute("integration.target_url", url)
        set_peer_service(span, dep["name"], url)
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=outbound_headers(correlation_id)) as client:
                for path in dep.get("health_paths", ["/health"]):
                    probe_url = f"{url.rstrip('/')}{path}"
                    response = await client.get(probe_url)
                    if response.status_code < 500:
                        span.set_attribute("integration.status_code", response.status_code)
                        result["status"] = "healthy" if response.status_code < 400 else "degraded"
                        result["health_url"] = probe_url
                        result["status_code"] = response.status_code
                        return result
            result["status"] = "unhealthy"
            return result
        except Exception as exc:
            span.set_attribute("integration.error", str(exc))
            result["status"] = "unreachable"
            result["error"] = str(exc)
            return result


async def _get_json(url: str, path: str, correlation_id: str, timeout: float = 10.0, peer: str = "") -> httpx.Response:
    headers = outbound_headers(correlation_id)
    if peer:
        span = trace.get_current_span()
        set_peer_service(span, peer, url)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        return await client.get(f"{url.rstrip('/')}{path}")


def _status_payload(request: Optional[Request], dependencies: list[dict]) -> dict:
    trace_ctx = current_trace_context()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    return {
        "service": {
            "display_name": cfg.brand_name,
            "app_name": cfg.app_name,
            "service_name": cfg.otel_service_name,
            "service_host": _service_name_from_url(str(request.base_url)) if request else "",
            **service_metadata(),
        },
        "correlation": {
            "correlation_id": correlation_id,
            "trace_id": trace_ctx["trace_id"],
            "span_id": trace_ctx["span_id"],
            "traceparent": trace_ctx["traceparent"],
            "oracleApmTraceId": trace_ctx["trace_id"],
        },
        "telemetry": {
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
            "logging_configured": cfg.logging_configured,
            "otlp_log_export_enabled": cfg.otlp_log_export_enabled,
            "database_target": cfg.database_target_label,
            "database_observability_enabled": cfg.database_observability_enabled,
            "orders_sync_enabled": cfg.orders_sync_enabled,
            "orders_sync_interval_seconds": cfg.orders_sync_interval_seconds,
            "orders_sync_source_name": cfg.orders_sync_source_name,
        },
        "dependencies": dependencies,
        "drilldowns": _drilldown_targets(),
    }


def _mushop_url() -> str:
    return cfg.octo_drone_shop_url or cfg.mushop_cloudnative_url or cfg.octo_apm_cloudnative_url


def _order_source_url() -> str:
    return external_orders_base_url()


@router.get("/mushop/product-catalog", response_model=None)
async def mushop_product_catalog(category: str = "", request: Request = None):
    """Fetch MuShop catalog with propagated trace context."""
    tracer = get_tracer()
    mushop = _mushop_url()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    if not mushop:
        return {"error": "MuShop not configured", "products": []}

    with tracer.start_as_current_span("integration.mushop.product_catalog") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        span.set_attribute("integration.category", category)
        span.set_attribute("integration.mushop_url", mushop)
        set_peer_service(span, "drone-shop-portal", mushop)
        try:
            params = {"category": category} if category else {}
            async with httpx.AsyncClient(timeout=10.0, headers=outbound_headers(correlation_id)) as client:
                resp = await client.get(f"{mushop.rstrip('/')}/api/products", params=params)
            span.set_attribute("integration.mushop.status_code", resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                push_log("INFO", "MuShop product catalog fetched", **{
                    "integration.type": "product_catalog",
                    "integration.target_service": "mushop-cloudnative",
                    "integration.product_count": len(data.get("products", [])),
                    "correlation.id": correlation_id,
                })
                return {
                    "products": data.get("products", []),
                    "source": "mushop-cloudnative",
                    "category": category,
                    "correlation_id": correlation_id,
                }
            return {"products": [], "reason": f"MuShop returned {resp.status_code}", "correlation_id": correlation_id}
        except Exception as exc:
            span.set_attribute("integration.error", str(exc))
            return {"products": [], "reason": str(exc), "correlation_id": correlation_id}


@router.get("/mushop/order-history", response_model=None)
async def mushop_order_history(customer_email: str = "", request: Request = None):
    """Fetch MuShop orders for a CRM customer."""
    tracer = get_tracer()
    mushop = _order_source_url()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    if not mushop:
        return {"error": "MuShop not configured"}

    with tracer.start_as_current_span("integration.mushop.order_history") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        span.set_attribute("integration.customer_email", customer_email)
        set_peer_service(span, "drone-shop-portal", mushop)
        try:
            response = await _get_json(mushop, "/api/orders", correlation_id)
            span.set_attribute("integration.mushop.status_code", response.status_code)
            if response.status_code == 200:
                data = response.json()
                orders = data.get("orders", [])
                if customer_email:
                    orders = [order for order in orders if order.get("customer_email") == customer_email]
                return {
                    "orders": orders,
                    "source": "mushop-cloudnative",
                    "customer_email": customer_email,
                    "correlation_id": correlation_id,
                }
            return {"orders": [], "reason": f"MuShop returned {response.status_code}", "correlation_id": correlation_id}
        except Exception as exc:
            span.set_attribute("integration.error", str(exc))
            return {"orders": [], "reason": str(exc), "correlation_id": correlation_id}


@router.post("/mushop/recommend-products")
async def mushop_recommend_products(payload: dict, request: Request):
    """Recommend MuShop products based on CRM context."""
    tracer = get_tracer()
    mushop = _mushop_url()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    if not mushop:
        return {"error": "MuShop not configured"}

    with tracer.start_as_current_span("integration.mushop.recommend_products") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        ticket_id = payload.get("ticket_id")
        customer_id = payload.get("customer_id")
        span.set_attribute("integration.ticket_id", ticket_id or 0)
        span.set_attribute("integration.customer_id", customer_id or 0)
        set_peer_service(span, "drone-shop-portal", mushop)
        try:
            response = await _get_json(mushop, "/api/shop/featured", correlation_id)
            span.set_attribute("integration.mushop.status_code", response.status_code)
            if response.status_code == 200:
                data = response.json()
                push_log("INFO", "MuShop product recommendations fetched", **{
                    "integration.type": "recommend_products",
                    "integration.target_service": "mushop-cloudnative",
                    "integration.product_count": len(data.get("products", [])),
                    "integration.ticket_id": ticket_id,
                    "integration.customer_id": customer_id,
                    "correlation.id": correlation_id,
                })
                return {
                    "recommendations": data.get("products", []),
                    "source": "mushop-cloudnative",
                    "context": {"ticket_id": ticket_id, "customer_id": customer_id},
                    "correlation_id": correlation_id,
                }
            return {"recommendations": [], "reason": f"MuShop returned {response.status_code}", "correlation_id": correlation_id}
        except Exception as exc:
            span.set_attribute("integration.error", str(exc))
            return {"recommendations": [], "reason": str(exc), "correlation_id": correlation_id}


@router.get("/mushop/health", response_model=None)
async def mushop_health(request: Request = None):
    """Check MuShop service health with current correlation context."""
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    status = await _dependency_health(_configured_dependencies()[0], correlation_id)
    status["correlation_id"] = correlation_id
    return status


@router.get("/topology")
async def topology(request: Request):
    """Return the OCI-DEMO application topology with correlation metadata."""
    correlation_id = build_correlation_id(getattr(request.state, "correlation_id", ""))
    dependencies = await _collect_dependency_status(correlation_id)
    payload = _status_payload(request, dependencies)
    payload["orders"] = await order_security_summary()
    push_log("INFO", "Topology requested", **{
        "integration.type": "topology",
        "integration.dependency_count": len(dependencies),
        "correlation.id": correlation_id,
    })
    return payload


@router.get("/status")
async def integration_status(request: Request):
    """Show configured integrations, telemetry state, and drilldown targets."""
    correlation_id = build_correlation_id(getattr(request.state, "correlation_id", ""))
    dependencies = await _collect_dependency_status(correlation_id)
    payload = _status_payload(request, dependencies)
    payload["orders"] = await order_security_summary()
    push_log("INFO", "Integration status requested", **{
        "integration.type": "status",
        "integration.dependency_count": len(dependencies),
        "correlation.id": correlation_id,
    })
    return payload


async def _collect_dependency_status(correlation_id: str) -> list[dict]:
    results = []
    for dependency in _configured_dependencies():
        results.append(await _dependency_health(dependency, correlation_id))
    return results


# ── Browser Remote Access (Guacamole via Control Plane) ──────

@router.get("/console/connections")
async def console_connections(request: Request):
    """Fetch Guacamole connections from the Control Plane and return auto-login URLs."""
    import base64

    cp_url = cfg.oci_demo_control_plane_url
    if not cp_url:
        return {"connections": [], "error": "Control Plane not configured"}

    tracer = get_tracer()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))

    try:
        with tracer.start_as_current_span("integration.control_plane.guacamole") as span:
            set_peer_service(span, "oci-demo-control-plane", cp_url)
            span.set_attribute("integration.target_service", "oci-demo-control-plane")
            async with httpx.AsyncClient(timeout=10.0, headers=outbound_headers(correlation_id)) as client:
                resp = await client.get(f"{cp_url.rstrip('/')}/api/guacamole/connections")
                span.set_attribute("http.status_code", resp.status_code)
                if resp.status_code != 200:
                    return {"connections": [], "error": f"Control Plane returned {resp.status_code}"}
                data = resp.json()
    except Exception as exc:
        return {"connections": [], "error": str(exc)}

    guac_url = data.get("guacamole_url", "")
    connections = data.get("connections", [])
    result = []
    for conn in connections:
        conn_id = conn.get("id", conn.get("identifier", ""))
        name = conn.get("name", "")
        protocol = conn.get("protocol", "ssh")
        hostname = conn.get("parameters", {}).get("hostname", "") if isinstance(conn.get("parameters"), dict) else ""
        client_id = f"{conn_id}\0c\0postgresql"
        encoded = base64.b64encode(client_id.encode()).decode()
        client_url = f"{guac_url}/#/client/{encoded}" if guac_url else ""
        result.append({
            "identifier": conn_id,
            "name": name,
            "protocol": protocol,
            "hostname": hostname,
            "client_url": client_url,
        })

    return {"connections": result, "guacamole_url": guac_url, "total": len(result)}


@router.get("/console/config")
async def console_config():
    """Check if Browser Remote Access is available."""
    cp_url = cfg.oci_demo_control_plane_url
    return {
        "available": bool(cp_url),
        "control_plane_url": cp_url or None,
    }
