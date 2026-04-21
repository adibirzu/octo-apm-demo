"""360 Observability Dashboard — unified monitoring view across all pillars.

Provides API endpoints and data aggregation for a single-pane-of-glass dashboard
covering application health, database performance, integration status, security
events, order sync health, and links to OCI console drill-downs (APM, OPSI,
DB Management, Log Analytics).
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text, case, cast, Float

from server.config import cfg
from server.database import (
    AuditLog, Customer, Invoice, Order, OrderItem, OrderSyncAudit,
    Product, SupportTicket, User, UserSession, async_session_factory,
)
from server.db_compat import HEALTH_CHECK_SQL
from server.observability.correlation import build_correlation_id, current_trace_context, service_metadata
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability-dashboard"])


@router.get("/360")
async def observability_360(request: Request):
    """Full 360-degree observability summary — one call for the dashboard page."""
    tracer = get_tracer()
    correlation_id = build_correlation_id(getattr(getattr(request, "state", None), "correlation_id", ""))
    trace_ctx = current_trace_context()
    start = time.time()

    with tracer.start_as_current_span("observability.360.dashboard") as span:
        span.set_attribute("dashboard.type", "360-monitoring")

        app_health = await _app_health_summary()
        db_health = await _db_health_summary()
        integration_health = await _integration_health_summary()
        security_summary = await _security_summary()
        sync_health = await _order_sync_health()

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
                "opsi": {
                    "console_url": cfg.opsi_console_url or None,
                    "configured": bool(cfg.opsi_console_url),
                },
                "db_management": {
                    "console_url": cfg.db_management_console_url or None,
                    "configured": bool(cfg.db_management_console_url),
                    "atp_ocid": cfg.atp_ocid or None,
                },
            },
            "app_health": app_health,
            "db_health": db_health,
            "integration_health": integration_health,
            "security": security_summary,
            "order_sync": sync_health,
            "dashboard_meta": {
                "query_time_ms": elapsed_ms,
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
