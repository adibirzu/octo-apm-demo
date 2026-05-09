"""360 Observability Dashboard — unified monitoring view for Drone Shop.

Provides API endpoints for a single-pane-of-glass dashboard covering
application health, database performance, CRM integration status,
security events, and links to OCI console drill-downs.
"""

from __future__ import annotations

import time
import logging
import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, text, cast, Float

from server.auth_security import require_authenticated_or_internal_service
from server.config import cfg
from server.database import (
    Customer, Order, OrderItem, Product, CartItem,
    Shipment, Warehouse, Campaign, Lead, PageView, AuditLog,
    SecurityEvent, engine, get_db, AsyncSessionLocal,
)
from server.middleware.circuit_breaker import crm_breaker, workflow_breaker
from server.modules.api_gateway_observability import supported_api_gateway_scenarios
from server.modules.payments.gateway_emulator import payment_gateway_capabilities
from server.observability.correlation import build_correlation_id, current_trace_context, service_metadata
from server.observability.logging_sdk import push_log
from server.observability.oci_vss import get_vulnerability_summary
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability-dashboard"])

_SENSITIVE_METADATA_KEY_FRAGMENTS = (
    "authorization",
    "card_number",
    "card.cvv",
    "cvv",
    "pan",
    "raw_token",
    "token.raw",
)


@router.get("/360")
async def observability_360(request: Request):
    """Full 360-degree observability summary."""
    tracer = get_tracer(cfg.otel_service_name)
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    trace_ctx = current_trace_context()
    start = time.time()

    with tracer.start_as_current_span("observability.360.dashboard") as span:
        span.set_attribute("dashboard.type", "360-monitoring")

        app_health = await _app_health_summary()
        db_health = await _db_health_summary()
        integration_health = _integration_health_summary()
        security_summary = await _security_summary()
        vss_summary = get_vulnerability_summary()

        elapsed_ms = round((time.time() - start) * 1000, 2)
        span.set_attribute("dashboard.query_time_ms", elapsed_ms)

        push_log("INFO", "360 observability dashboard loaded", **{
            "dashboard.type": "360-monitoring",
            "dashboard.query_time_ms": elapsed_ms,
            "correlation.id": correlation_id,
        })

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation": {
                "correlation_id": correlation_id,
                "trace_id": trace_ctx["trace_id"],
                "span_id": trace_ctx["span_id"],
                "traceparent": trace_ctx["traceparent"],
            },
            "service": service_metadata(),
            "pillars": {
                "apm": {
                    "configured": cfg.apm_configured,
                    "console_url": cfg.apm_console_url or None,
                    "service_name": cfg.otel_service_name,
                    "rum_configured": cfg.rum_configured,
                },
                "logging": {
                    "configured": cfg.logging_configured,
                    "log_id": cfg.oci_log_id or None,
                    "console_url": cfg.log_analytics_console_url or None,
                },
                "metrics": {
                    "prometheus": True,
                    "otlp_export": cfg.apm_configured,
                },
                "workflow_gateway": {
                    "configured": cfg.workflow_gateway_configured,
                    "base_url": cfg.workflow_public_api_base_url or None,
                    "service_name": cfg.workflow_service_name,
                    "selectai_configured": cfg.selectai_configured,
                },
                "opsi": {
                    "console_url": cfg.opsi_console_url or None,
                    "configured": bool(cfg.opsi_console_url),
                },
                "db_management": {
                    "console_url": cfg.db_management_console_url or None,
                    "configured": bool(cfg.db_management_console_url),
                },
            },
            "app_health": app_health,
            "db_health": db_health,
            "integration_health": integration_health,
            "security": security_summary,
            "vulnerability_scanning": vss_summary,
            "circuit_breakers": {
                "crm": crm_breaker.status(),
                "workflow_gateway": workflow_breaker.status(),
            },
            "dashboard_meta": {"query_time_ms": elapsed_ms},
        }


@router.get("/360/app-health")
async def app_health_detail():
    return await _app_health_summary()


@router.get("/360/db-health")
async def db_health_detail():
    return await _db_health_summary()


@router.get("/360/security")
async def security_detail():
    return await _security_summary()


@router.get("/payment-gateway/events")
async def payment_gateway_event_drilldown(
    request: Request,
    order_id: int = Query(default=0, ge=0, description="Filter by Drone Shop order id"),
    trace_id: str = Query(default="", max_length=64, description="Filter by OCI APM trace id"),
    gateway_request_id: str = Query(default="", max_length=128, description="Filter by payment gateway request id"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum events to return"),
):
    """Token-safe payment gateway event drilldown for APM/log correlation."""
    user = require_authenticated_or_internal_service(request)
    safe_trace_id = _safe_filter_value(trace_id, 64)
    safe_gateway_request_id = _safe_filter_value(gateway_request_id, 128)
    tracer = get_tracer(cfg.otel_service_name)
    trace_ctx = current_trace_context()

    with tracer.start_as_current_span("observability.payment_gateway.events") as span:
        span.set_attribute("payment.gateway.filter.order_id", int(order_id or 0))
        span.set_attribute("payment.gateway.filter.trace_id", safe_trace_id or "all")
        span.set_attribute("payment.gateway.filter.request_id", safe_gateway_request_id or "all")
        span.set_attribute("auth.role", str(user.get("role", "unknown")))

        events = await _payment_gateway_events(
            order_id=int(order_id or 0),
            trace_id=safe_trace_id,
            gateway_request_id=safe_gateway_request_id,
            limit=int(limit),
        )
        summary = _payment_gateway_event_summary(events)
        span.set_attribute("payment.gateway.event_count", len(events))
        span.set_attribute("payment.gateway.order_count", len(summary["order_ids"]))
        push_log(
            "INFO",
            "Payment gateway observability events queried",
            **{
                "payment.gateway.event_count": len(events),
                "payment.gateway.filter.order_id": int(order_id or 0),
                "payment.gateway.filter.trace_id": safe_trace_id or "all",
                "payment.gateway.filter.request_id": safe_gateway_request_id or "all",
                "auth.role": str(user.get("role", "unknown")),
            },
        )
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation": {
                "trace_id": trace_ctx["trace_id"],
                "span_id": trace_ctx["span_id"],
                "traceparent": trace_ctx["traceparent"],
            },
            "filters": {
                "order_id": int(order_id or 0) or None,
                "trace_id": safe_trace_id or None,
                "gateway_request_id": safe_gateway_request_id or None,
                "limit": int(limit),
            },
            "summary": summary,
            "events": events,
        }


@router.get("/capabilities")
async def observability_capabilities():
    """Machine-readable observability signal inventory for demos and checks."""
    return _observability_capabilities()


def _observability_capabilities() -> dict:
    return {
        "service": service_metadata(),
        "runtime": cfg.safe_runtime_summary(),
        "signals": {
            "traces": {
                "enabled": cfg.apm_configured,
                "provider": "oci-apm",
                "service_name": cfg.otel_service_name,
                "span_enrichment": [
                    "http",
                    "sql_id",
                    "business_operations",
                    "java_app_server",
                    "payment_gateway",
                    "api_gateway",
                    "attack_lab",
                    "oci_genai",
                    "selectai",
                    "llmetry",
                ],
            },
            "logs": {
                "enabled": cfg.logging_configured,
                "provider": "oci-logging",
                "trace_correlation_fields": ["trace_id", "span_id", "oracleApmTraceId", "oracleApmSpanId"],
                "pii_masking": True,
            },
            "metrics": {
                "prometheus_endpoint": "/metrics",
                "oci_monitoring_enabled": bool(cfg.oci_compartment_id),
                "business_metric_families": [
                    "orders",
                    "checkout",
                    "cart",
                    "payments",
                    "payment_orchestration",
                    "java_app_server",
                    "synthetic_users",
                    "attack_lab",
                    "api_gateway",
                    "crm_sync",
                    "assistant",
                    "llmetry",
                ],
            },
            "ai": {
                "assistant_endpoint": "/api/admin/assistant/query",
                "provider": "oci-genai" if cfg.oci_genai_endpoint else "local-grounded-fallback",
                "genai_configured": bool(cfg.oci_compartment_id and cfg.oci_genai_endpoint and cfg.oci_genai_model_id),
                "selectai_configured": cfg.selectai_configured,
                "selectai_endpoint": "/api/workflow-gateway/api/selectai/generate",
                "query_lab_endpoint": "/api/workflow-gateway/api/query-lab/run",
                "admin_required": True,
                "llmetry_enabled": cfg.llmetry_enabled,
                "llmetry_store": "llmetry_events",
                "langfuse_configured": cfg.langfuse_configured,
                "correlation_fields": [
                    "trace_id",
                    "span_id",
                    "oracleApmTraceId",
                    "assistant.session_id",
                    "llm.prompt.hash",
                    "llm.response.hash",
                ],
            },
            "edge": {
                "api_gateway": {
                    "enabled": True,
                    "provider": "oci-api-gateway",
                    "scopes": ["public", "private"],
                    "controls": ["route_policy", "authentication", "quota", "rate_limit", "backend_health"],
                    "correlation_fields": [
                        "oci.api_gateway.request_id",
                        "oci.api_gateway.route",
                        "oci.api_gateway.action",
                        "oracleApmTraceId",
                    ],
                },
            },
            "rum": {
                "enabled": cfg.rum_configured,
                "web_application": cfg.oci_apm_web_application,
                "synthetic_user_identity": "domain-only",
            },
            "database": {
                "target": cfg.database_target_label,
                "sql_id_enrichment": True,
                "session_tagging": not cfg.use_postgres,
                "connection_name": cfg.oracle_dsn or None,
            },
            "security": {
                "security_spans": True,
                "attack_lab": True,
                "api_gateway_detection": True,
                "cloud_guard_osquery_assets": True,
            },
        },
        "demo_generators": {
            "synthetic_users": {
                "enabled": bool(cfg.internal_service_key),
                "endpoint": "/api/synthetic/users/run",
            },
            "demo_storyboard": {
                "enabled": True,
                "endpoint": "/api/shop/demo/storyboard",
            },
            "attack_lab": {
                "enabled": True,
                "endpoint": "/api/shop/attack/simulate",
            },
            "api_gateway_detection": {
                "enabled": True,
                "endpoint": "/api/shop/attack/simulate",
                "scenarios": supported_api_gateway_scenarios(),
                "safe_storage": "policy_metadata_only",
            },
            "payment_gateway": {
                "enabled": cfg.payment_gateway_simulation_enabled,
                "event_drilldown_endpoint": "/api/observability/payment-gateway/events",
                "java_app_server_enabled": cfg.java_apm_enabled,
                **payment_gateway_capabilities(),
            },
            "assistant_llmetry": {
                "enabled": cfg.llmetry_enabled,
                "endpoint": "/api/admin/assistant/query",
                "stores": ["assistant_sessions", "assistant_messages", "llmetry_events"],
                "exports": ["oci-apm", "oci-logging", "langfuse-otlp"],
            },
        },
        "drilldowns": {
            "apm_console_url": cfg.apm_console_url or None,
            "log_analytics_console_url": cfg.log_analytics_console_url or None,
            "opsi_console_url": cfg.opsi_console_url or None,
            "db_management_console_url": cfg.db_management_console_url or None,
        },
        "endpoints": {
            "dashboard": "/api/observability/360",
            "capabilities": "/api/observability/capabilities",
            "payment_gateway_events": "/api/observability/payment-gateway/events",
            "metrics": "/metrics",
            "readiness": "/ready",
            "integration_status": "/api/integrations/status",
        },
        "privacy": {
            "masks_contact_fields": True,
            "masks_email_mentions_in_text": True,
            "raw_card_numbers_logged": False,
            "raw_card_numbers_persisted": False,
            "raw_card_cvv_persisted": False,
            "raw_llm_prompts_logged": False,
            "raw_llm_responses_logged": False,
            "raw_synthetic_user_email_in_rum_dimensions": False,
            "raw_synthetic_user_email_in_http_headers": False,
        },
    }


async def _payment_gateway_events(
    *,
    order_id: int,
    trace_id: str,
    gateway_request_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    row_limit = max(1, min(int(limit or 50), 200))
    query = text(
        f"""
        SELECT e.id, e.order_id, e.gateway_name, e.gateway_provider, e.gateway_request_id,
               e.payment_method, e.wallet_type, e.card_brand, e.card_last4, e.payment_network,
               e.step_name, e.step_phase, e.step_status, e.step_index, e.latency_ms,
               e.trace_id, e.span_id, e.metadata_json, e.created_at,
               o.status AS order_status, o.payment_status AS order_payment_status,
               o.payment_required AS order_payment_required,
               o.payment_provider_reference AS order_payment_provider_reference,
               o.payment_paid_at AS order_payment_paid_at
        FROM payment_gateway_events e
        LEFT JOIN orders o ON o.id = e.order_id
        WHERE (:order_id = 0 OR e.order_id = :order_id)
          AND (:trace_id IS NULL OR e.trace_id = :trace_id)
          AND (:gateway_request_id IS NULL OR e.gateway_request_id = :gateway_request_id)
        ORDER BY e.created_at DESC, e.gateway_request_id, e.step_index ASC
        FETCH FIRST {row_limit} ROWS ONLY
        """
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            query,
            {
                "order_id": int(order_id or 0),
                "trace_id": trace_id or None,
                "gateway_request_id": gateway_request_id or None,
            },
        )
        return [_serialize_payment_gateway_event(dict(row)) for row in result.mappings().all()]


def _serialize_payment_gateway_event(row: dict[str, Any]) -> dict[str, Any]:
    created_at = row.get("created_at")
    paid_at = row.get("order_payment_paid_at")
    return {
        "id": row.get("id"),
        "order_id": row.get("order_id"),
        "gateway": {
            "name": row.get("gateway_name") or "",
            "provider": row.get("gateway_provider") or "",
            "request_id": row.get("gateway_request_id") or "",
        },
        "payment": {
            "method": row.get("payment_method") or "",
            "wallet_type": row.get("wallet_type") or "",
            "card_brand": row.get("card_brand") or "",
            "card_last4": row.get("card_last4") or "",
            "network": row.get("payment_network") or "",
        },
        "step": {
            "name": row.get("step_name") or "",
            "phase": row.get("step_phase") or "",
            "status": row.get("step_status") or "",
            "index": int(row.get("step_index") or 0),
            "latency_ms": round(float(row.get("latency_ms") or 0), 2),
        },
        "trace": {
            "trace_id": row.get("trace_id") or "",
            "span_id": row.get("span_id") or "",
        },
        "order": {
            "status": row.get("order_status") or "",
            "payment_status": row.get("order_payment_status") or "",
            "payment_required": _boolish(row.get("order_payment_required")),
            "payment_provider_reference": row.get("order_payment_provider_reference") or "",
            "payment_paid_at": paid_at.isoformat() if hasattr(paid_at, "isoformat") else paid_at,
        },
        "metadata": _scrub_gateway_metadata(row.get("metadata_json") or ""),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }


def _payment_gateway_event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_events = sorted(events, key=lambda item: int(item["step"]["index"] or 0))
    return {
        "event_count": len(events),
        "order_ids": sorted({int(event["order_id"]) for event in events if event.get("order_id")}),
        "gateway_request_ids": sorted(
            {event["gateway"]["request_id"] for event in events if event["gateway"].get("request_id")}
        ),
        "trace_ids": sorted({event["trace"]["trace_id"] for event in events if event["trace"].get("trace_id")}),
        "methods": sorted({event["payment"]["method"] for event in events if event["payment"].get("method")}),
        "step_names": [event["step"]["name"] for event in sorted_events],
        "statuses": sorted({event["step"]["status"] for event in events if event["step"].get("status")}),
    }


def _safe_filter_value(value: str, limit: int) -> str:
    return "".join(
        ch for ch in str(value or "").strip()[:limit] if ch.isalnum() or ch in "._:-"
    )


def _boolish(value: Any) -> bool:
    return str(value if value is not None else "0").strip().lower() not in {"", "0", "false", "no"}


def _scrub_gateway_metadata(raw_metadata: str) -> dict[str, Any]:
    if not raw_metadata:
        return {}
    try:
        decoded = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {"metadata_parse_error": "invalid_json"}
    if not isinstance(decoded, dict):
        return {}
    return _scrub_metadata_value(decoded)


def _scrub_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _scrub_metadata_value(item)
            for key, item in value.items()
            if not _is_sensitive_metadata_key(str(key))
        }
    if isinstance(value, list):
        return [_scrub_metadata_value(item) for item in value[:50]]
    return value


def _is_sensitive_metadata_key(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in _SENSITIVE_METADATA_KEY_FRAGMENTS)


async def _app_health_summary() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            customers = await session.scalar(select(func.count(Customer.id))) or 0
            orders = await session.scalar(select(func.count(Order.id))) or 0
            products = await session.scalar(select(func.count(Product.id))) or 0
            shipments = await session.scalar(select(func.count(Shipment.id))) or 0
            campaigns = await session.scalar(select(func.count(Campaign.id))) or 0
            leads = await session.scalar(select(func.count(Lead.id))) or 0

            cutoff_24h = datetime.utcnow() - timedelta(hours=24)
            recent_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.created_at >= cutoff_24h)
            ) or 0
            total_revenue = await session.scalar(
                select(cast(func.coalesce(func.sum(Order.total), 0), Float))
            ) or 0.0
            page_views_24h = await session.scalar(
                select(func.count(PageView.id)).where(PageView.created_at >= cutoff_24h)
            ) or 0

        return {
            "status": "healthy",
            "entities": {
                "customers": int(customers),
                "orders": int(orders),
                "products": int(products),
                "shipments": int(shipments),
                "campaigns": int(campaigns),
                "leads": int(leads),
            },
            "activity": {
                "orders_24h": int(recent_orders),
                "total_revenue": float(total_revenue),
                "page_views_24h": int(page_views_24h),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _db_health_summary() -> dict:
    health_sql = "SELECT 1 FROM DUAL" if not cfg.use_postgres else "SELECT 1"
    try:
        start = time.time()
        async with AsyncSessionLocal() as session:
            await session.execute(text(health_sql))
        latency_ms = round((time.time() - start) * 1000, 2)
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "database_target": cfg.database_target_label}

    return {
        "status": "connected",
        "latency_ms": latency_ms,
        "database_target": cfg.database_target_label,
        "session_tagging": not cfg.use_postgres,
        "observability": {
            "sql_id_enrichment": True,
            "session_tagging_enabled": not cfg.use_postgres,
            "opsi_console": cfg.opsi_console_url or None,
            "db_management_console": cfg.db_management_console_url or None,
        },
    }


def _integration_health_summary() -> dict:
    return {
        "crm": {
            "configured": bool(cfg.enterprise_crm_url),
            "url": cfg.crm_public_url or None,
            "hostname": cfg.crm_public_hostname or None,
        },
        "shared_atp": {
            "configured": bool(cfg.oracle_dsn),
            "target": cfg.database_target_label,
        },
        "workflow_gateway": {
            "configured": cfg.workflow_gateway_configured,
            "base_url": cfg.workflow_public_api_base_url or None,
            "selectai_profile": cfg.selectai_profile_name or None,
        },
    }


async def _security_summary() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            cutoff_24h = datetime.utcnow() - timedelta(hours=24)
            total_audit = await session.scalar(select(func.count(AuditLog.id))) or 0
            recent_audit = await session.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.created_at >= cutoff_24h)
            ) or 0
            total_security = await session.scalar(select(func.count(SecurityEvent.id))) or 0
            recent_security = await session.scalar(
                select(func.count(SecurityEvent.id)).where(SecurityEvent.created_at >= cutoff_24h)
            ) or 0

        return {
            "audit": {"total": int(total_audit), "entries_24h": int(recent_audit)},
            "security_events": {"total": int(total_security), "events_24h": int(recent_security)},
            "waf": {"detection_enabled": True, "headers": ["x-oci-waf-score", "x-oci-waf-action"]},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
