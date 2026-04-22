"""Admin panel module."""

import os
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from server.config import cfg
from server.modules._authz import require_admin_user
from server.observability.otel_setup import get_tracer
from server.database import get_db
from server.db_compat import DB_VERSION_SQL, DB_ACTIVE_CONNECTIONS_SQL

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])
tracer_fn = get_tracer
_ALLOWED_ROLES = {"admin", "manager", "viewer", "user", "chaos-operator"}


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
