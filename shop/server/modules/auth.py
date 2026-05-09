"""Auth module — login and bearer-token profile access."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from opentelemetry import trace
from sqlalchemy import text

from server.auth_security import (
    issue_token,
    login_rate_limited,
    register_login_attempt,
    require_authenticated_user,
)
from server.database import get_db
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


async def _write_login_audit(
    db,
    request: Request,
    *,
    user_id: int | None,
    username: str,
    success: bool,
    reason: str,
    browser_trace_id: str,
) -> None:
    source_ip = request.client.host if request.client else "unknown"
    action = "auth.login.success" if success else "auth.login.failure"
    resource = f"users/{user_id}" if user_id else "auth/login"
    await db.execute(
        text(
            "INSERT INTO audit_logs (user_id, action, details, ip_address, user_agent, trace_id) "
            "VALUES (:user_id, :action, :details, :ip_address, :user_agent, :trace_id)"
        ),
        {
            "user_id": user_id,
            "action": action,
            "details": (
                f"resource={resource}; username={username or 'anonymous'}; result={'success' if success else 'failure'}; "
                f"reason={reason}; browser_trace_id={browser_trace_id or 'n/a'}"
            ),
            "ip_address": source_ip,
            "user_agent": request.headers.get("user-agent", "")[:500],
            "trace_id": _trace_id(),
        },
    )


@router.post("/login")
async def login(request: Request, payload: dict):
    """Authenticate a user and issue a signed bearer token."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"
    username = str(payload.get("username", "") or "").strip()
    password = str(payload.get("password", "") or "")
    browser_trace_id = str(payload.get("browser_trace_id") or request.headers.get("X-Correlation-Id") or "").strip()

    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.username", username or "anonymous")
        span.set_attribute("auth.flow", "password")
        span.set_attribute("auth.success", False)
        span.set_attribute("app.module", "auth")
        span.set_attribute("app.logical_endpoint", "auth.login")
        span.set_attribute("db.system", "oracle")
        span.set_attribute("db.entity", "users")
        span.set_attribute("db.audit.entity", "audit_logs")
        if browser_trace_id:
            span.set_attribute("browser.trace_id", browser_trace_id)

        if not username or not password:
            span.set_attribute("auth.failure_reason", "missing_credentials")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password are required")

        if login_rate_limited(source_ip):
            span.set_attribute("auth.failure_reason", "rate_limited")
            security_span(
                "brute_force",
                severity="medium",
                payload=username,
                source_ip=source_ip,
                endpoint="/api/auth/login",
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

        failed_login = False
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

            valid_password = False
            if user and int(user.get("is_active") or 0) == 1:
                try:
                    valid_password = bcrypt.checkpw(
                        password.encode("utf-8"),
                        str(user["password_hash"]).encode("utf-8"),
                    )
                except ValueError:
                    valid_password = False

            if not valid_password:
                failed_login = True
                known_user_id = int(user["id"]) if user else None
                if known_user_id is not None:
                    span.set_attribute("auth.user_id", known_user_id)
                span.set_attribute("auth.success", False)
                span.set_attribute("auth.failure_reason", "invalid_credentials")
                await _write_login_audit(
                    db,
                    request,
                    user_id=known_user_id,
                    username=username,
                    success=False,
                    reason="invalid_credentials",
                    browser_trace_id=browser_trace_id,
                )
                push_log(
                    "WARNING",
                    "Login attempt failed",
                    **{
                        "auth.method": "password",
                        "auth.username": username or "anonymous",
                        "auth.user_id": known_user_id or 0,
                        "auth.success": False,
                        "auth.failure_reason": "invalid_credentials",
                        "http.url.path": "/api/auth/login",
                        "client.address": source_ip,
                        "source.ip": source_ip,
                        "browser.trace_id": browser_trace_id,
                    },
                )
                register_login_attempt(source_ip, success=False)
                security_span(
                    "brute_force",
                    severity="low",
                    payload=username,
                    source_ip=source_ip,
                    endpoint="/api/auth/login",
                )
            else:
                span.set_attribute("auth.user_id", int(user["id"]))
                span.set_attribute("auth.role", str(user["role"]))
                span.set_attribute("auth.success", True)

                await db.execute(
                    text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": user["id"]},
                )
                await _write_login_audit(
                    db,
                    request,
                    user_id=int(user["id"]),
                    username=str(user["username"]),
                    success=True,
                    reason="password_verified",
                    browser_trace_id=browser_trace_id,
                )
                push_log(
                    "INFO",
                    "Login succeeded",
                    **{
                        "auth.method": "password",
                        "auth.username": str(user["username"]),
                        "auth.user_id": int(user["id"]),
                        "auth.role": str(user["role"]),
                        "auth.success": True,
                        "http.url.path": "/api/auth/login",
                        "client.address": source_ip,
                        "source.ip": source_ip,
                        "browser.trace_id": browser_trace_id,
                    },
                )

        if failed_login:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
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
    tracer = get_tracer()
    with tracer.start_as_current_span("auth.profile") as span:
        token_payload = require_authenticated_user(request)
        span.set_attribute("auth.user_id", int(token_payload["sub"]))
        span.set_attribute("auth.method", token_payload.get("auth_method", "unknown"))

        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, username, email, role, last_login FROM users WHERE id = :id"),
                {"id": int(token_payload["sub"])},
            )
            user = result.mappings().first()

        if not user:
            span.set_attribute("auth.found", False)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        span.set_attribute("auth.username", str(user["username"]))
        span.set_attribute("auth.role", str(user["role"]))
        return dict(user)
