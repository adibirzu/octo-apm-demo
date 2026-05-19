"""Admin panel module."""

from datetime import datetime, timedelta, timezone
import logging
import os
import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from server.config import cfg
from server.modules._authz import require_admin_user
from server.observability.otel_setup import get_tracer
from server.database import get_db
from server.db_compat import DB_VERSION_SQL, DB_ACTIVE_CONNECTIONS_SQL

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])
tracer_fn = get_tracer
_ALLOWED_ROLES = {"admin", "manager", "viewer", "user", "chaos-operator", "stress-operator"}
logger = logging.getLogger(__name__)

_RETENTION_ORDERED_DELETES = (
    {
        "table": "order_sync_audit",
        "count_sql": "SELECT COUNT(*) FROM order_sync_audit WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM order_sync_audit WHERE created_at < :cutoff",
    },
    {
        "table": "audit_logs",
        "count_sql": "SELECT COUNT(*) FROM audit_logs WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM audit_logs WHERE created_at < :cutoff",
    },
    {
        "table": "user_sessions",
        "count_sql": "SELECT COUNT(*) FROM user_sessions WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM user_sessions WHERE created_at < :cutoff",
    },
    {
        "table": "page_views",
        "count_sql": "SELECT COUNT(*) FROM page_views WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM page_views WHERE created_at < :cutoff",
    },
    {
        "table": "support_tickets",
        "count_sql": "SELECT COUNT(*) FROM support_tickets WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM support_tickets WHERE created_at < :cutoff",
    },
    {
        "table": "shipments",
        "count_sql": (
            "SELECT COUNT(*) FROM shipments WHERE created_at < :cutoff "
            "OR order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)"
        ),
        "delete_sql": (
            "DELETE FROM shipments WHERE created_at < :cutoff "
            "OR order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)"
        ),
    },
    {
        "table": "invoices",
        "count_sql": (
            "SELECT COUNT(*) FROM invoices WHERE created_at < :cutoff "
            "OR order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)"
        ),
        "delete_sql": (
            "DELETE FROM invoices WHERE created_at < :cutoff "
            "OR order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)"
        ),
    },
    {
        "table": "order_items",
        "count_sql": "SELECT COUNT(*) FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)",
        "delete_sql": "DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE created_at < :cutoff)",
    },
    {
        "table": "orders",
        "count_sql": "SELECT COUNT(*) FROM orders WHERE created_at < :cutoff",
        "delete_sql": "DELETE FROM orders WHERE created_at < :cutoff",
    },
)


def _validate_retention_days(value: int) -> int:
    if value < 1 or value > 3650:
        raise HTTPException(status_code=400, detail="older_than_days must be between 1 and 3650")
    return value


def _cutoff_for_days(older_than_days: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=older_than_days)


async def _retention_plan(db, *, cutoff: datetime, apply: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in _RETENTION_ORDERED_DELETES:
        count_result = await db.execute(text(spec["count_sql"]), {"cutoff": cutoff})
        count = int(count_result.scalar() or 0)
        deleted = 0
        if apply and count:
            delete_result = await db.execute(text(spec["delete_sql"]), {"cutoff": cutoff})
            deleted = int(delete_result.rowcount if delete_result.rowcount is not None and delete_result.rowcount >= 0 else count)
        rows.append({"table": spec["table"], "matching_rows": count, "deleted_rows": deleted})
    return rows


@router.get("/users")
async def list_users(request: Request):
    """List users without exposing password hashes."""
    tracer = tracer_fn()
    actor = require_admin_user(request)

    with tracer.start_as_current_span("admin.list_users") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.admin_users"):
                result = await db.execute(
                    text(
                        "SELECT id, username, email, role, is_active, created_at, last_login "
                        "FROM users ORDER BY created_at DESC"
                    )
                )
                rows = result.fetchall()

        users = [dict(r._mapping) for r in rows]
        return {"users": users}


@router.patch("/users/{user_id}/role")
async def change_user_role(user_id: int, request: Request):
    """Change user role with explicit admin authorization."""
    tracer = tracer_fn()
    actor = require_admin_user(request)
    body = await request.json()
    new_role = str(body.get("role", "user")).strip().lower() or "user"
    if new_role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Unsupported role")

    with tracer.start_as_current_span("admin.change_role") as span:
        span.set_attribute("admin.target_user", user_id)
        span.set_attribute("admin.new_role", new_role)
        span.set_attribute("admin.actor", actor.get("username", "unknown"))

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.role_update"):
                await db.execute(
                    text("UPDATE users SET role = :role WHERE id = :id"),
                    {"role": new_role, "id": user_id}
                )

        return {"status": "updated", "user_id": user_id, "role": new_role}


@router.get("/config")
async def get_config(request: Request):
    """Return a sanitized runtime summary for administrators."""
    tracer = tracer_fn()
    actor = require_admin_user(request)

    with tracer.start_as_current_span("admin.get_config") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        return {
            "runtime": cfg.safe_runtime_summary(),
            "database_url": cfg.masked_database_url(),
            "oci_apm_endpoint": cfg.oci_apm_endpoint or None,
            "oci_log_id": cfg.oci_log_id or None,
            "splunk_hec_url": cfg.splunk_hec_url or None,
            "python_version": sys.version,
        }


@router.get("/debug")
async def debug_info(request: Request):
    """Minimal debug metadata for administrators."""
    tracer = tracer_fn()
    actor = require_admin_user(request)

    with tracer.start_as_current_span("admin.debug"):
        return {
            "actor": actor.get("username"),
            "platform": sys.platform,
            "python_version": sys.version,
            "executable": os.path.basename(sys.executable),
            "pid": os.getpid(),
            "hostname": os.uname().nodename,
        }


@router.get("/audit-logs")
async def get_audit_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """View audit logs with admin authorization."""
    tracer = tracer_fn()
    actor = require_admin_user(request)

    with tracer.start_as_current_span("admin.audit_logs") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.audit_logs"):
                result = await db.execute(
                    text(
                        "SELECT id, user_id, action, resource, details, ip_address, user_agent, trace_id, created_at "
                        "FROM audit_logs ORDER BY created_at DESC "
                        "OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
                    ),
                    {"offset": offset, "limit": limit},
                )
                rows = result.fetchall()

        return {"audit_logs": [dict(r._mapping) for r in rows], "limit": limit, "offset": offset}


@router.get("/data-retention/preview")
async def preview_data_retention(
    request: Request,
    older_than_days: int = Query(default=30, ge=1, le=3650),
):
    """Preview admin cleanup counts without deleting rows."""
    tracer = tracer_fn()
    actor = require_admin_user(request)
    older_than_days = _validate_retention_days(older_than_days)
    cutoff = _cutoff_for_days(older_than_days)

    with tracer.start_as_current_span("admin.data_retention.preview") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        span.set_attribute("retention.older_than_days", older_than_days)
        span.set_attribute("retention.cutoff", cutoff.isoformat())
        async with get_db() as db:
            tables = await _retention_plan(db, cutoff=cutoff, apply=False)

        total = sum(row["matching_rows"] for row in tables)
        span.set_attribute("retention.matching_rows", total)
        return {
            "dry_run": True,
            "older_than_days": older_than_days,
            "cutoff": cutoff.isoformat(),
            "total_matching_rows": total,
            "tables": tables,
        }


@router.post("/data-retention/cleanup")
async def cleanup_data_retention(request: Request):
    """Delete demo operational rows older than the requested age."""
    tracer = tracer_fn()
    actor = require_admin_user(request)
    body = await request.json()
    try:
        older_than_days = _validate_retention_days(int(body.get("older_than_days", 30)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="older_than_days must be an integer")
    dry_run = bool(body.get("dry_run", False))
    cutoff = _cutoff_for_days(older_than_days)

    with tracer.start_as_current_span("admin.data_retention.cleanup") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        span.set_attribute("retention.older_than_days", older_than_days)
        span.set_attribute("retention.cutoff", cutoff.isoformat())
        span.set_attribute("retention.dry_run", dry_run)
        async with get_db() as db:
            tables = await _retention_plan(db, cutoff=cutoff, apply=not dry_run)

        total_deleted = sum(row["deleted_rows"] for row in tables)
        span.set_attribute("retention.deleted_rows", total_deleted)
        logger.info(
            "admin data retention cleanup actor=%s older_than_days=%s dry_run=%s deleted_rows=%s",
            actor.get("username", "unknown"),
            older_than_days,
            dry_run,
            total_deleted,
        )
        return {
            "dry_run": dry_run,
            "older_than_days": older_than_days,
            "cutoff": cutoff.isoformat(),
            "total_deleted_rows": total_deleted,
            "tables": tables,
        }


@router.get("/db-status")
async def db_status(request: Request):
    """Database status — shows pool stats and connection info."""
    tracer = tracer_fn()
    actor = require_admin_user(request)

    with tracer.start_as_current_span("admin.db_status") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.db_version"):
                result = await db.execute(text(DB_VERSION_SQL))
                version = result.scalar()
            with tracer.start_as_current_span("db.query.db_connections"):
                result = await db.execute(text(DB_ACTIVE_CONNECTIONS_SQL))
                active_connections = result.scalar()

        return {
            "database_target": cfg.database_target_label,
            "database_version": version,
            "active_connections": active_connections,
            "pool_size": cfg.db_pool_size,
            "max_overflow": cfg.db_max_overflow,
        }
