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
            "database_backend": "oracle_atp",
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


@router.post("/users")
async def create_user(request: Request, payload: dict):
    """Create a new user in the Oracle database."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    
    username = str(payload.get("username", "")).strip()
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    role = str(payload.get("role", "user")).strip()
    
    if not username or not password or not email:
        raise HTTPException(status_code=400, detail="Username, email, and password required")
        
    import bcrypt
    from server.observability.logging_sdk import push_log

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    with tracer.start_as_current_span("admin.create_user") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.target_user", username)
        
        async with get_db() as db:
            await db.execute(
                text("INSERT INTO users (username, email, password_hash, role, is_active) VALUES (:username, :email, :password, :role, 1)"),
                {"username": username, "email": email, "password": hashed, "role": role}
            )
            # Log the action in the audit table
            await db.execute(
                text("INSERT INTO audit_logs (user_id, action, resource, details) VALUES (:user_id, 'create_user', 'users', :details)"),
                {"user_id": admin_user["id"], "details": f"Created user {username}"}
            )
            
        push_log("INFO", f"Admin {admin_user['username']} created new user {username}", **{"admin.target_user": username})
        return {"status": "success", "message": f"User {username} created"}


@router.post("/partners")
async def create_partner(request: Request, payload: dict):
    """Create a new partner (shop) in the Oracle database."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    
    name = str(payload.get("name", "")).strip()
    address = str(payload.get("address", "")).strip()
    contact_email = str(payload.get("contact_email", "")).strip()
    contact_phone = str(payload.get("contact_phone", "")).strip()
    
    if not name or not address:
        raise HTTPException(status_code=400, detail="Name and address are required")
        
    from server.observability.logging_sdk import push_log
    
    with tracer.start_as_current_span("admin.create_partner") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.target_partner", name)
        
        async with get_db() as db:
            await db.execute(
                text("INSERT INTO shops (name, address, coordinates, contact_email, contact_phone, is_active) "
                     "VALUES (:name, :address, '0,0', :email, :phone, 1)"),
                {"name": name, "address": address, "email": contact_email, "phone": contact_phone}
            )
            # Log the action
            await db.execute(
                text("INSERT INTO audit_logs (user_id, action, resource, details) VALUES (:user_id, 'create_partner', 'shops', :details)"),
                {"user_id": admin_user["id"], "details": f"Created partner location {name}"}
            )
            
        push_log("INFO", f"Admin {admin_user['username']} created new partner {name}", **{"admin.target_partner": name})
        return {"status": "success", "message": f"Partner {name} created"}
