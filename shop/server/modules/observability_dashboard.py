"""360 Observability Dashboard — unified monitoring view for Drone Shop.

Provides API endpoints for a single-pane-of-glass dashboard covering
application health, database performance, CRM integration status,
security events, and links to OCI console drill-downs.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text, cast, Float

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
                "assistant_endpoint": "/api/shop/assistant/query",
                "provider": "oci-genai" if cfg.oci_genai_endpoint else "local-grounded-fallback",
                "genai_configured": bool(cfg.oci_compartment_id and cfg.oci_genai_endpoint and cfg.oci_genai_model_id),
                "selectai_configured": cfg.selectai_configured,
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
                "java_app_server_enabled": cfg.java_apm_enabled,
                **payment_gateway_capabilities(),
            },
            "assistant_llmetry": {
                "enabled": cfg.llmetry_enabled,
                "endpoint": "/api/shop/assistant/query",
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
