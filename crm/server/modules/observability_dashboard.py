"""OCI Observability demo dashboard.

The browser-facing dashboard returns customer-safe business and experience
signals while internal detail endpoints retain lower-level health checks.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text, cast, Float

from server.config import cfg
from server.database import (
    AuditLog, Customer, Invoice, Order, OrderSyncAudit,
    Product, SupportTicket, User, UserSession, async_session_factory,
)
from server.db_compat import HEALTH_CHECK_SQL
from server.observability.correlation import build_correlation_id, service_metadata
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability-dashboard"])


@router.get("/360")
async def observability_360(request: Request):
    """Full 360-degree observability summary — one call for the dashboard page."""
    tracer = get_tracer()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    start = time.time()

    with tracer.start_as_current_span("observability.360.dashboard") as span:
        span.set_attribute("dashboard.type", "360-monitoring")

        app_health = await _app_health_summary()
        db_health = await _db_health_summary()
        integration_health = await _integration_health_summary()
        security_summary = await _security_summary()
        sync_health = await _order_sync_health()
        pillars = _observability_pillars()

        elapsed_ms = round((time.time() - start) * 1000, 2)
        span.set_attribute("dashboard.query_time_ms", elapsed_ms)

        push_log("INFO", "360 observability dashboard loaded", **{
            "dashboard.type": "360-monitoring",
            "dashboard.query_time_ms": elapsed_ms,
            "correlation.id": correlation_id,
        })

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **_customer_observability_dashboard(
                app_health=app_health,
                db_health=db_health,
                integration_health=integration_health,
                security=security_summary,
                order_sync=sync_health,
                pillars=pillars,
            ),
            "dashboard_meta": {
                "query_time_ms": elapsed_ms,
                "data_source": "live_demo_application",
            },
        }


@router.get("/360/app-health")
async def app_health_detail():
    """Application health: entity counts, recent activity, error signals."""
    return await _app_health_summary()


@router.get("/360/db-health")
async def db_health_detail():
    """Database health: connectivity, pool stats, query performance hints."""
    return await _db_health_summary()


@router.get("/360/sync-health")
async def sync_health_detail():
    """Order sync health: success rates, last sync, failure breakdown."""
    return await _order_sync_health()


@router.get("/360/security")
async def security_detail():
    """Security summary: recent events, attack types, audit activity."""
    return await _security_summary()


@router.get("/capabilities")
async def observability_capabilities():
    """Machine-readable observability signal inventory for demos and checks."""
    return _observability_capabilities()


@router.get("/melts")
async def observability_melts():
    """MELTS collection contract for admin demo evidence."""
    return _melts_capabilities()


def _observability_capabilities() -> dict:
    return {
        "service": service_metadata(),
        "runtime": cfg.safe_runtime_summary(),
        "melts": _melts_capabilities(),
        "signals": {
            "traces": {
                "enabled": cfg.apm_configured,
                "provider": "oci-apm",
                "service_name": cfg.otel_service_name,
                "span_enrichment": [
                    "http",
                    "sql_id",
                    "business_operations",
                    "order_sync",
                    "security_events",
                    "chaos_simulation",
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
                "oci_monitoring_namespace": "octo_apm_demo",
                "business_metric_families": [
                    "orders",
                    "order_sync",
                    "invoices",
                    "tickets",
                    "auth",
                    "campaigns",
                    "shipping",
                    "dashboard",
                    "security",
                ],
            },
            "rum": {
                "enabled": cfg.rum_configured,
                "frontend_ingest_endpoint": "/api/observability/frontend",
                "same_origin_w3c_trace_propagation": True,
                "login_actions": ["auth.login.submit", "auth.login.result"],
            },
            "database": {
                "target": cfg.database_target_label,
                "sql_id_enrichment": cfg.database_observability_enabled,
                "session_tagging": True,
                "connection_name": cfg.atp_connection_name or None,
                "atp_ocid": cfg.atp_ocid or None,
            },
            "security": {
                "security_spans": cfg.security_log_enabled,
                "session_gate": True,
                "sso_configured": cfg.idcs_configured,
            },
            "admin_coordinator": {
                "enabled": True,
                "surface": "admin.octodemo.cloud",
                "scope": "octo-apm-demo",
                "admin_only": True,
                "scope_enforced": True,
                "oci_auth_mode": cfg.oci_auth_mode,
                "raw_prompt_logged": False,
                "allowed_hosts": ["admin.octodemo.cloud"],
                "span_names": ["admin.coordinator.scope", "admin.coordinator.query"],
                "log_fields": [
                    "coordinator.surface",
                    "coordinator.host",
                    "coordinator.scope",
                    "coordinator.allowed",
                    "coordinator.topic",
                    "coordinator.refusal_reason",
                    "coordinator.scope.enforced",
                    "coordinator.auth.mode",
                    "oci.auth.mode",
                ],
            },
        },
        "demo_generators": {
            "crm_simulation": {
                "enabled": True,
                "endpoint": "/api/simulation",
            },
            "drone_shop_proxy": {
                "enabled": bool(cfg.octo_drone_shop_url and cfg.drone_shop_internal_key),
                "shop_configured": bool(cfg.octo_drone_shop_url),
            },
            "order_sync": {
                "enabled": cfg.orders_sync_enabled,
                "interval_seconds": cfg.orders_sync_interval_seconds,
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
            "melts": "/api/observability/melts",
            "frontend_ingest": "/api/observability/frontend",
            "admin_coordinator": "/api/admin/coordinator/query",
            "metrics": "/metrics",
            "readiness": "/ready",
            "integration_schema": "/api/integrations/schema",
        },
        "privacy": {
            "masks_contact_fields": True,
            "masks_email_mentions_in_text": True,
            "raw_shared_secret_exposed": False,
        },
    }


def _melts_capabilities() -> dict[str, Any]:
    """Describe how Admin/CRM proves Metrics, Events, Logs, Traces, and Synthetics."""
    return {
        "version": "2026.05",
        "coverage": {
            "metrics": {
                "status": "enabled" if cfg.oci_compartment_id else "needs_oci_compartment_id",
                "namespace": "octo_apm_demo",
                "families": [
                    "app.requests.rate",
                    "app.errors.rate",
                    "app.orders.count",
                    "app.order_sync.count",
                    "app.auth.success.count",
                    "app.auth.failure.count",
                    "app.security.events.count",
                    "app.dashboard.loads.count",
                ],
                "dimensions": ["serviceName", "environment", "runtime", "instanceId"],
            },
            "events": {
                "status": "enabled",
                "families": [
                    "auth.login",
                    "admin.coordinator.query",
                    "orders.sync.external",
                    "simulation.storyboard",
                    "attack_lab.stage",
                ],
                "join_fields": ["Trace ID", "Order ID", "Source Order ID", "Attack ID", "Assistant Session ID"],
            },
            "logs": {
                "status": "enabled" if cfg.logging_configured else "not_configured",
                "sources": ["SOC Application Logs", "OCI Unified Schema Logs"],
                "saved_searches": [
                    "service-trace-log-coverage",
                    "connector-live-log-coverage",
                    "auth-login-correlation",
                    "service-error-triage",
                    "attack-lab-trace-timeline",
                ],
            },
            "traces": {
                "status": "enabled" if cfg.apm_configured else "not_configured",
                "saved_queries": [
                    "OCTO APM - login/auth flow",
                    "OCTO APM - trace drilldown",
                    "OCTO APM - platform workflows",
                    "OCTO APM - service errors",
                ],
                "required_components": [
                    "enterprise-crm-portal",
                    "octo-drone-shop",
                    "oracle-atp",
                    "admin.coordinator",
                ],
            },
            "synthetics": {
                "status": "enabled" if cfg.orders_sync_enabled else "manual",
                "generators": ["admin_simulation", "order_sync", "browser_runner", "traffic_generator"],
                "rum_dimensions": ["workflow_id", "request_id", "auth.login.result"],
            },
        },
        "operator_pivots": {
            "primary": ["Trace ID", "Order ID", "Source Order ID", "Request ID"],
            "secondary": ["Run ID", "Workflow ID", "Attack ID", "Assistant Session ID"],
            "privacy": "customer_safe_no_raw_secret_or_payment_content",
        },
    }


def _observability_pillars() -> dict:
    """Internal signal inventory used to build the customer demo view."""
    return {
        "apm": {
            "configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
        },
        "logging": {
            "configured": cfg.logging_configured,
        },
        "metrics": {
            "configured": True,
        },
        "data_insights": {
            "configured": bool(cfg.opsi_console_url or cfg.db_management_console_url),
        },
        "security": {
            "configured": True,
        },
    }


def _customer_observability_dashboard(
    *,
    app_health: dict,
    db_health: dict,
    integration_health: dict,
    security: dict,
    order_sync: dict,
    pillars: dict,
) -> dict:
    """Build the browser-facing, customer-safe observability demo payload."""
    entities = app_health.get("entities") or {}
    activity = app_health.get("activity") or {}
    sync_stats = (order_sync.get("stats") or {})
    sync_orders = (order_sync.get("orders") or {})
    audit = (security.get("audit") or {})
    waf = (security.get("waf") or {})
    total_syncs = int(sync_stats.get("total_sync_operations") or 0)
    successful_syncs = int(sync_stats.get("successful") or 0)
    failed_syncs = int(sync_stats.get("failed") or 0)
    raw_success_rate = sync_stats.get("success_rate_pct")
    success_rate = float(raw_success_rate) if raw_success_rate is not None else 100.0
    backlog = int(sync_orders.get("backlog") or 0)
    db_available = db_health.get("status") == "connected"
    integration_ready = bool((integration_health.get("drone_shop") or {}).get("configured"))
    signal_cards = _customer_signal_cards(pillars, db_available, bool(waf.get("detection_enabled")))
    active_signal_count = sum(1 for item in signal_cards if item["active"])
    total_signal_count = len(signal_cards)
    health_tone = _demo_health_tone(
        db_available=db_available,
        success_rate=success_rate,
        backlog=backlog,
        failed_syncs=failed_syncs,
    )

    return {
        "demo": {
            "name": "OCI Observability Demo",
            "badge": "Demo project",
            "description": (
                "A customer-facing demo project showcasing OCI Observability "
                "service capabilities with live business and experience signals."
            ),
            "privacy_note": "Technical identifiers and infrastructure settings are intentionally hidden.",
        },
        "hero": {
            "title": "Customer Experience Monitoring",
            "status": health_tone["label"],
            "tone": health_tone["tone"],
            "summary": health_tone["summary"],
            "active_signals": active_signal_count,
            "total_signals": total_signal_count,
        },
        "scorecards": [
            {
                "id": "customers",
                "label": "Customers",
                "value": int(entities.get("customers") or 0),
                "format": "number",
                "tone": "neutral",
            },
            {
                "id": "orders",
                "label": "Orders",
                "value": int(entities.get("orders") or 0),
                "format": "number",
                "tone": "neutral",
            },
            {
                "id": "revenue",
                "label": "Revenue",
                "value": float(activity.get("total_revenue") or 0),
                "format": "currency",
                "tone": "success",
            },
            {
                "id": "experience",
                "label": "Order Experience",
                "value": success_rate,
                "format": "percent",
                "tone": _percent_tone(success_rate),
            },
        ],
        "charts": {
            "business_mix": [
                {"label": "Customers", "value": int(entities.get("customers") or 0), "tone": "accent"},
                {"label": "Orders", "value": int(entities.get("orders") or 0), "tone": "success"},
                {"label": "Products", "value": int(entities.get("products") or 0), "tone": "warm"},
                {"label": "Support", "value": int(entities.get("tickets") or 0), "tone": "rose"},
            ],
            "order_flow": [
                {"label": "Successful handoffs", "value": successful_syncs, "tone": "success"},
                {"label": "Needs attention", "value": failed_syncs, "tone": "danger"},
                {"label": "In progress", "value": backlog, "tone": "warm"},
            ],
            "signal_coverage": signal_cards,
        },
        "customer_journey": [
            {
                "label": "Browse and buy",
                "metric": f"{int(activity.get('orders_24h') or 0)} orders in the last 24 hours",
                "status": "Observed",
                "tone": "success" if int(activity.get("orders_24h") or 0) > 0 else "neutral",
            },
            {
                "label": "Order handoff",
                "metric": f"{success_rate:.1f}% successful",
                "status": "Healthy" if success_rate >= 95 else "Watch",
                "tone": _percent_tone(success_rate),
            },
            {
                "label": "Support readiness",
                "metric": f"{int(activity.get('open_tickets') or 0)} open tickets",
                "status": "Ready",
                "tone": "warm" if int(activity.get("open_tickets") or 0) > 5 else "success",
            },
            {
                "label": "Experience protection",
                "metric": f"{int(audit.get('entries_24h') or 0)} signals today",
                "status": "Monitored",
                "tone": "neutral",
            },
        ],
        "service_health": {
            "data_service": {
                "label": "Customer data service",
                "status": "Available" if db_available else "Needs attention",
                "latency_ms": round(float(db_health.get("latency_ms") or 0), 1) if db_available else None,
                "tone": "success" if db_available else "danger",
            },
            "order_handoff": {
                "label": "Storefront order handoff",
                "status": "On" if order_sync.get("enabled") else "Paused",
                "success_rate": success_rate,
                "total": total_syncs,
                "tone": _percent_tone(success_rate) if order_sync.get("enabled") else "warm",
            },
            "integration": {
                "label": "Storefront connection",
                "status": "Connected" if integration_ready else "Ready to connect",
                "tone": "success" if integration_ready else "warm",
            },
            "protection": {
                "label": "Protection monitoring",
                "status": "Active" if waf.get("detection_enabled") else "Ready",
                "events_today": int(audit.get("entries_24h") or 0),
                "coverage_count": len(security.get("owasp_coverage") or []),
                "tone": "success" if waf.get("detection_enabled") else "warm",
            },
        },
    }


def _customer_signal_cards(pillars: dict, db_available: bool, security_active: bool) -> list[dict]:
    """Return OCI capability cards without infrastructure identifiers."""
    return [
        {
            "id": "apm",
            "label": "Application performance",
            "service": "OCI Application Performance Monitoring",
            "active": bool((pillars.get("apm") or {}).get("configured")),
            "description": "Trace application journeys and latency across the demo experience.",
            "tone": "accent",
        },
        {
            "id": "rum",
            "label": "Real user experience",
            "service": "OCI APM Browser RUM",
            "active": bool((pillars.get("apm") or {}).get("rum_configured")),
            "description": "Measure page loads, browser errors, and user interactions.",
            "tone": "success",
        },
        {
            "id": "logs",
            "label": "Logs and events",
            "service": "OCI Logging and Log Analytics",
            "active": bool((pillars.get("logging") or {}).get("configured")),
            "description": "Review customer-impacting events from one searchable timeline.",
            "tone": "warm",
        },
        {
            "id": "metrics",
            "label": "Service metrics",
            "service": "OCI Monitoring",
            "active": bool((pillars.get("metrics") or {}).get("configured")),
            "description": "Track health indicators for the live demo application.",
            "tone": "rose",
        },
        {
            "id": "data",
            "label": "Data service insight",
            "service": "OCI Database Management and Operations Insights",
            "active": bool((pillars.get("data_insights") or {}).get("configured") or db_available),
            "description": "Connect user journeys with data service responsiveness.",
            "tone": "success",
        },
        {
            "id": "security",
            "label": "Protection signals",
            "service": "OCI security and edge observability",
            "active": security_active,
            "description": "Surface security-relevant events as part of the experience view.",
            "tone": "accent",
        },
    ]


def _demo_health_tone(
    *,
    db_available: bool,
    success_rate: float,
    backlog: int,
    failed_syncs: int,
) -> dict:
    if not db_available:
        return {
            "label": "Needs attention",
            "tone": "danger",
            "summary": "Customer activity is visible, but the data service needs attention.",
        }
    if success_rate < 80 or failed_syncs > 0:
        return {
            "label": "Watch",
            "tone": "warm",
            "summary": "OCI Observability highlights customer flows that need review.",
        }
    if backlog > 5:
        return {
            "label": "Busy",
            "tone": "warm",
            "summary": "The demo is healthy with active customer work in progress.",
        }
    return {
        "label": "Healthy",
        "tone": "success",
        "summary": "Live customer journeys are visible across OCI Observability signals.",
    }


def _percent_tone(value: float) -> str:
    if value >= 95:
        return "success"
    if value >= 80:
        return "warm"
    return "danger"


async def _app_health_summary() -> dict:
    """Aggregate application entity counts and recent activity."""
    try:
        async with async_session_factory() as session:
            customers = await session.scalar(select(func.count(Customer.id))) or 0
            orders = await session.scalar(select(func.count(Order.id))) or 0
            products = await session.scalar(select(func.count(Product.id))) or 0
            invoices = await session.scalar(select(func.count(Invoice.id))) or 0
            tickets = await session.scalar(select(func.count(SupportTicket.id))) or 0
            users = await session.scalar(select(func.count(User.id))) or 0
            active_sessions = await session.scalar(select(func.count(UserSession.id))) or 0

            # Recent orders (last 24h)
            cutoff_24h = datetime.utcnow() - timedelta(hours=24)
            recent_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.created_at >= cutoff_24h)
            ) or 0

            # Open tickets
            open_tickets = await session.scalar(
                select(func.count(SupportTicket.id)).where(SupportTicket.status == "open")
            ) or 0

            # Revenue (total)
            total_revenue = await session.scalar(
                select(cast(func.coalesce(func.sum(Order.total), 0), Float))
            ) or 0.0

        return {
            "status": "healthy",
            "entities": {
                "customers": int(customers),
                "orders": int(orders),
                "products": int(products),
                "invoices": int(invoices),
                "tickets": int(tickets),
                "users": int(users),
                "active_sessions": int(active_sessions),
            },
            "activity": {
                "orders_24h": int(recent_orders),
                "open_tickets": int(open_tickets),
                "total_revenue": float(total_revenue),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _db_health_summary() -> dict:
    """Database connectivity and configuration."""
    db_ok = False
    db_latency_ms = 0.0
    try:
        start = time.time()
        async with async_session_factory() as session:
            await session.execute(text(HEALTH_CHECK_SQL))
            db_ok = True
        db_latency_ms = round((time.time() - start) * 1000, 2)
        try:
            from server.observability.oci_monitoring import set_db_latency
            set_db_latency(db_latency_ms)
        except Exception:  # noqa: S110
            pass
    except Exception as e:
        return {
            "status": "disconnected",
            "error": str(e),
            "database_target": cfg.database_target_label,
        }

    return {
        "status": "connected",
        "latency_ms": db_latency_ms,
        "database_target": cfg.database_target_label,
        "atp_ocid": cfg.atp_ocid or None,
        "connection_name": cfg.atp_connection_name or None,
        "session_tagging": True,
        "pool": {
            "size": cfg.db_pool_size,
            "max_overflow": cfg.db_max_overflow,
            "timeout": cfg.db_pool_timeout,
        },
        "observability": {
            "sql_id_enrichment": cfg.database_observability_enabled,
            "session_tagging_enabled": True,
            "opsi_console": cfg.opsi_console_url or None,
            "db_management_console": cfg.db_management_console_url or None,
        },
    }


async def _integration_health_summary() -> dict:
    """Cross-service integration status."""
    return {
        "drone_shop": {
            "configured": bool(cfg.octo_drone_shop_url or cfg.mushop_cloudnative_url),
            "sync_enabled": cfg.orders_sync_enabled,
            "sync_interval_seconds": cfg.orders_sync_interval_seconds,
            "source_name": cfg.orders_sync_source_name,
        },
        "seven_kingdoms": {
            "configured": bool(cfg.c22_skp_url),
        },
        "control_plane": {
            "configured": bool(cfg.control_plane_url),
        },
        "atp": {
            "configured": bool(cfg.atp_ocid or cfg.atp_connection_name),
            "atp_ocid": cfg.atp_ocid or None,
        },
    }


async def _security_summary() -> dict:
    """Security events and audit log summary."""
    try:
        async with async_session_factory() as session:
            cutoff_24h = datetime.utcnow() - timedelta(hours=24)

            # Recent audit entries
            total_audit = await session.scalar(select(func.count(AuditLog.id))) or 0
            recent_audit = await session.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.created_at >= cutoff_24h)
            ) or 0

            # Failed sync attempts (security-relevant)
            failed_syncs = await session.scalar(
                select(func.count(OrderSyncAudit.id)).where(OrderSyncAudit.sync_status == "failed")
            ) or 0

        return {
            "audit": {
                "total_entries": int(total_audit),
                "entries_24h": int(recent_audit),
            },
            "waf": {
                "detection_enabled": True,
                "header_monitoring": ["x-oci-waf-score", "x-oci-waf-action"],
            },
            "order_sync_failures": int(failed_syncs),
            "owasp_coverage": [
                "A01-Broken Access Control",
                "A02-Cryptographic Failures",
                "A03-Injection",
                "A04-Insecure Design",
                "A07-Auth Failures",
                "A08-Deserialization",
                "A10-SSRF",
            ],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _order_sync_health() -> dict:
    """Order sync pipeline health and statistics."""
    try:
        async with async_session_factory() as session:
            total_syncs = await session.scalar(select(func.count(OrderSyncAudit.id))) or 0
            successful = await session.scalar(
                select(func.count(OrderSyncAudit.id)).where(OrderSyncAudit.sync_status == "success")
            ) or 0
            failed = await session.scalar(
                select(func.count(OrderSyncAudit.id)).where(OrderSyncAudit.sync_status == "failed")
            ) or 0

            # Last successful sync
            last_sync = await session.scalar(
                select(func.max(OrderSyncAudit.created_at)).where(OrderSyncAudit.sync_status == "success")
            )

            # External orders count
            external_orders = await session.scalar(
                select(func.count(Order.id)).where(Order.source_system != "enterprise-crm")
            ) or 0

            # Backlog orders
            backlog = await session.scalar(
                select(func.count(Order.id)).where(Order.backlog_status == "backlog")
            ) or 0

            # Suspicious orders
            suspicious = await session.scalar(
                select(func.count(Order.id)).where(Order.total >= cfg.suspicious_order_total_threshold)
            ) or 0

        success_rate = round((successful / total_syncs * 100), 1) if total_syncs > 0 else 100.0

        return {
            "enabled": cfg.orders_sync_enabled,
            "source": cfg.orders_sync_source_name,
            "interval_seconds": cfg.orders_sync_interval_seconds,
            "stats": {
                "total_sync_operations": int(total_syncs),
                "successful": int(successful),
                "failed": int(failed),
                "success_rate_pct": success_rate,
                "last_successful_sync": last_sync.isoformat() + "Z" if last_sync else None,
            },
            "orders": {
                "external_total": int(external_orders),
                "backlog": int(backlog),
                "suspicious": int(suspicious),
            },
            "thresholds": {
                "suspicious_total": cfg.suspicious_order_total_threshold,
                "backlog_age_minutes": cfg.backlog_order_age_minutes,
            },
        }
    except Exception as e:
        return {"enabled": cfg.orders_sync_enabled, "status": "error", "error": str(e)}
