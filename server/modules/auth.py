"""Auth module — login, register, session management.

VULNS: Brute force (no rate limit), auth bypass (weak token), info disclosure
"""

from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, payload: dict):
    """Login — VULN: No rate limiting, verbose error messages."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.login") as span:
        username = payload.get("username", "")
        password = payload.get("password", "")
        span.set_attribute("auth.username", username)

        async with get_db() as db:
            # VULN: SQL injection in username lookup
            result = await db.execute(
                text(f"SELECT id, username, email, role, password_hash FROM users "
                     f"WHERE username = '{username}'")
            )
            user = result.mappings().first()

        if not user:
            # VULN: Info disclosure — reveals whether username exists
            security_span("brute_force", severity="low",
                          payload=username, source_ip=source_ip,
                          endpoint="/api/auth/login")
            return {"error": f"User '{username}' not found", "status": "failed"}

        # VULN: Plaintext password comparison fallback
        if password == "admin123" and user["username"] == "admin":
            return {
                "status": "success",
                "user": {"id": user["id"], "username": user["username"],
                         "email": user["email"], "role": user["role"]},
                "token": f"mushop-token-{user['id']}-{user['role']}",
            }

        return {"error": "Invalid password", "status": "failed"}


@router.get("/profile")
async def profile(request: Request):
    """Get user profile — VULN: Auth bypass with predictable token."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token or not token.startswith("mushop-token-"):
        security_span("auth_bypass", severity="medium",
                      payload=token,
                      source_ip=request.client.host if request.client else "",
                      endpoint="/api/auth/profile")
        return {"error": "Unauthorized"}

    # VULN: Token is just "mushop-token-{id}-{role}" — trivially forgeable
    parts = token.split("-")
    user_id = int(parts[2]) if len(parts) > 2 else 0

    async with get_db() as db:
        result = await db.execute(
            text("SELECT id, username, email, role FROM users WHERE id = :id"),
            {"id": user_id},
        )
        user = result.mappings().first()

    if not user:
        return {"error": "User not found"}
    return dict(user)
