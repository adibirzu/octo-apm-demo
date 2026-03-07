"""Auth module — login and bearer-token profile access."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from server.auth_security import (
    issue_token,
    login_rate_limited,
    register_login_attempt,
    require_authenticated_user,
)
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, payload: dict):
    """Authenticate a user and issue a signed bearer token."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"
    username = str(payload.get("username", "") or "").strip()
    password = str(payload.get("password", "") or "")

    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.username", username or "anonymous")

        if not username or not password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password are required")

        if login_rate_limited(source_ip):
            security_span(
                "brute_force",
                severity="medium",
                payload=username,
                source_ip=source_ip,
                endpoint="/api/auth/login",
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, username, email, role, password_hash, is_active "
                    "FROM users WHERE lower(username) = lower(:username) "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"username": username},
            )
            user = result.mappings().first()

            valid_password = bool(
                user
                and int(user.get("is_active") or 0) == 1
                and bcrypt.checkpw(password.encode("utf-8"), str(user["password_hash"]).encode("utf-8"))
            )

            if not valid_password:
                register_login_attempt(source_ip, success=False)
                security_span(
                    "brute_force",
                    severity="low",
                    payload=username,
                    source_ip=source_ip,
                    endpoint="/api/auth/login",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                )

            await db.execute(
                text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :id"),
                {"id": user["id"]},
            )

        register_login_attempt(source_ip, success=True)
        token = issue_token(user_id=int(user["id"]), username=str(user["username"]), role=str(user["role"]))
        return {
            "status": "success",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            },
            "token": token,
        }


@router.get("/profile")
async def profile(request: Request):
    """Return the currently authenticated user profile."""
    token_payload = require_authenticated_user(request)

    async with get_db() as db:
        result = await db.execute(
            text("SELECT id, username, email, role, last_login FROM users WHERE id = :id"),
            {"id": int(token_payload["sub"])},
        )
        user = result.mappings().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return dict(user)
