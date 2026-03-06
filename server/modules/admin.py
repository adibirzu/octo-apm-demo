"""Admin module — governed access to users, audit logs, and runtime status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from server.auth_security import require_role
from server.config import cfg
from server.database import Base, get_db, seed_data, sync_engine
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(request: Request) -> dict:
    return require_role(request, "admin")


@router.get("/users")
async def list_users(request: Request):
    """List users with non-sensitive account metadata."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_users") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])

        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, username, email, role, is_active, last_login, created_at "
                    "FROM users ORDER BY created_at DESC"
                )
            )
            users = [dict(r) for r in result.mappings().all()]

        span.set_attribute("admin.user_count", len(users))
        return {"users": users}


@router.get("/audit-logs")
async def list_audit_logs(request: Request):
    """List recent audit log entries."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_audit_logs") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM audit_logs ORDER BY created_at DESC FETCH FIRST 100 ROWS ONLY")
            )
            logs = [dict(r) for r in result.mappings().all()]

        span.set_attribute("admin.log_count", len(logs))
        return {"audit_logs": logs}


@router.get("/config")
async def get_config(request: Request):
    """Return deployment state without exposing live secrets."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.get_config") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.config_requested", True)

        return {
            "app_name": cfg.app_name,
            "environment": cfg.environment,
            "app_runtime": cfg.app_runtime,
            "database_backend": "oracle_atp" if cfg.use_oracle else "postgresql",
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
            "logging_configured": cfg.logging_configured,
            "splunk_configured": bool(cfg.splunk_hec_url and cfg.splunk_hec_token),
            "genai_configured": bool(cfg.oci_compartment_id and cfg.oci_genai_endpoint and cfg.oci_genai_model_id),
            "crm_configured": bool(cfg.enterprise_crm_url),
        }


def _guard_mutation(request: Request) -> dict:
    admin_user = _require_admin(request)
    if cfg.environment == "production" or cfg.app_runtime == "oke":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative data reset is disabled in production",
        )
    return admin_user


@router.post("/seed")
async def trigger_seed(request: Request):
    """Manually trigger seeding outside production environments."""
    admin_user = _guard_mutation(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.seed") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        seed_data()
    return {"status": "seeded"}


@router.post("/reseed")
async def trigger_reseed(request: Request):
    """Recreate all tables and reseed outside production environments."""
    admin_user = _guard_mutation(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.reseed") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        if sync_engine is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database sync engine unavailable")

        Base.metadata.drop_all(sync_engine)
        Base.metadata.create_all(sync_engine)
        seed_data()
    return {"status": "reseeded"}
