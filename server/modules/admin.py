"""Admin panel module — OWASP A01: Broken Access Control + A05: Security Misconfiguration.

Vulnerabilities:
- No authentication on admin endpoints
- Debug/config endpoints exposed
- User privilege escalation
- Server-side information disclosure
"""

import os
import sys

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db
from server.db_compat import DB_VERSION_SQL, DB_ACTIVE_CONNECTIONS_SQL

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])
tracer_fn = get_tracer


@router.get("/users")
async def list_users(request: Request):
    """List all users — VULN: no admin auth check, exposes password hashes."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("admin.list_users") as span:
        with security_span("privilege_escalation", severity="high",
                         source_ip=client_ip,
                         payload="unauthenticated admin user list"):
            log_security_event("privilege_escalation", "high",
                "Admin user list accessed without authentication",
                source_ip=client_ip)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.admin_users"):
                result = await db.execute(text("SELECT * FROM users"))
                rows = result.fetchall()

        # VULN: Exposing password hashes
        users = [dict(r._mapping) for r in rows]
        return {"users": users}


@router.patch("/users/{user_id}/role")
async def change_user_role(user_id: int, request: Request):
    """Change user role — VULN: no auth, privilege escalation."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    new_role = body.get("role", "user")

    with tracer.start_as_current_span("admin.change_role") as span:
        span.set_attribute("admin.target_user", user_id)
        span.set_attribute("admin.new_role", new_role)

        if new_role == "admin":
            with security_span("privilege_escalation", severity="critical",
                             payload=f"user {user_id} -> admin",
                             source_ip=client_ip):
                log_security_event("privilege_escalation", "critical",
                    f"Privilege escalation: user {user_id} promoted to admin",
                    source_ip=client_ip)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.role_update"):
                await db.execute(
                    text("UPDATE users SET role = :role WHERE id = :id"),
                    {"role": new_role, "id": user_id}
                )

        return {"status": "updated", "user_id": user_id, "role": new_role}


@router.get("/config")
async def get_config(request: Request):
    """Get app config — VULN: exposes sensitive configuration including secrets."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("admin.get_config") as span:
        with security_span("security_misconfig", severity="critical",
                         source_ip=client_ip,
                         payload="config endpoint accessed"):
            log_security_event("security_misconfig", "critical",
                "Sensitive configuration exposed via admin endpoint",
                source_ip=client_ip)

        # VULN: Exposing secrets, DB credentials, API keys
        return {
            "app_name": cfg.app_name,
            "app_env": cfg.app_env,
            "database_url": cfg.database_url,  # VULN: DB credentials
            "oci_apm_endpoint": cfg.oci_apm_endpoint,
            "oci_apm_private_datakey": cfg.oci_apm_private_datakey,  # VULN: API key
            "oci_log_id": cfg.oci_log_id,
            "splunk_hec_url": cfg.splunk_hec_url,
            "splunk_hec_token": cfg.splunk_hec_token,  # VULN: token
            "secret_key": cfg.app_secret_key,  # VULN: app secret
            "python_version": sys.version,
            "environment_vars": {k: v for k, v in os.environ.items()},  # VULN: all env vars
        }


@router.get("/debug")
async def debug_info(request: Request):
    """Debug endpoint — VULN: information disclosure."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("admin.debug"):
        return {
            "python_path": sys.path,
            "platform": sys.platform,
            "executable": sys.executable,
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "uid": os.getuid(),
            "hostname": os.uname().nodename,
        }


@router.get("/audit-logs")
async def get_audit_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """View audit logs — VULN: no auth."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("admin.audit_logs"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.audit_logs"):
                result = await db.execute(
                    text(f"SELECT * FROM audit_logs ORDER BY created_at DESC"
                         f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY")
                )
                rows = result.fetchall()

        return {"audit_logs": [dict(r._mapping) for r in rows], "limit": limit, "offset": offset}


@router.get("/db-status")
async def db_status(request: Request):
    """Database status — shows pool stats and connection info."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("admin.db_status") as span:
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
