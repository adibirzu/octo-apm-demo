"""Admin module — users, audit logs, config.

VULNS: No auth on admin endpoints, info disclosure
"""

from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.config import cfg

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def list_users(request: Request):
    """List all users — VULN: No admin auth check, exposes password hashes."""
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_users") as span:
        security_span("info_disclosure", severity="high",
                      source_ip=request.client.host if request.client else "",
                      endpoint="/api/admin/users")

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.admin_users") as db_span:
                result = await db.execute(
                    text("SELECT id, username, email, role, password_hash, is_active, "
                         "last_login, created_at FROM users")
                )
                users = [dict(r) for r in result.mappings().all()]
                db_span.set_attribute("db.row_count", len(users))

        span.set_attribute("admin.user_count", len(users))
        return {"users": users}


@router.get("/audit-logs")
async def list_audit_logs():
    """List audit logs — VULN: No auth."""
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_audit_logs") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.audit_logs") as db_span:
                result = await db.execute(
                    text("SELECT * FROM audit_logs ORDER BY created_at DESC FETCH FIRST 100 ROWS ONLY")
                )
                logs = [dict(r) for r in result.mappings().all()]
                db_span.set_attribute("db.row_count", len(logs))

        span.set_attribute("admin.log_count", len(logs))
        return {"audit_logs": logs}


@router.get("/config")
async def get_config(request: Request):
    """Get application config — VULN: Exposes secrets."""
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.get_config") as span:
        security_span("info_disclosure", severity="critical",
                      source_ip=request.client.host if request.client else "",
                      endpoint="/api/admin/config")

        span.set_attribute("admin.config_requested", True)

        return {
            "app_name": cfg.app_name,
            "environment": cfg.environment,
            "database_url": cfg.database_url,
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
            "oracle_user": cfg.oracle_user,
            "oracle_dsn": cfg.oracle_dsn,
            "splunk_hec_url": cfg.splunk_hec_url,
            # VULN: Exposing secrets
            "apm_private_key": cfg.oci_apm_private_datakey,
            "splunk_token": cfg.splunk_hec_token,
        }


@router.post("/seed")
async def trigger_seed():
    """Manually trigger database seeding (for troubleshooting)."""
    import traceback
    from server.database import seed_data
    try:
        seed_data()
        return {"status": "seeded"}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
