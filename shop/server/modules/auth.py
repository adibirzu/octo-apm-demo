"""Auth module — login and bearer-token profile access."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import insert, text

from server.auth_security import (
    issue_token,
    login_rate_limited,
    register_login_attempt,
    require_authenticated_user,
)
from server.database import AuditLog, get_db
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes, current_trace_context
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_flow_fields(*, username: str, source_ip: str) -> dict[str, object]:
    return {
        "workflow.id": "login",
        "workflow.step": "authenticate",
        "enduser.action": "login.submit",
        "auth.username": username or "anonymous",
        "auth.method": "password",
        "client.address": source_ip,
    }


def _trace_id() -> str:
    return current_trace_context()["trace_id"]


def _login_audit_insert(
    *,
    user_id: int,
    username: str,
    source_ip: str,
    user_agent: str,
    trace_id: str,
):
    """Build the login audit insert with dialect-aware reserved-name quoting."""
    return insert(AuditLog).values(
        user_id=user_id,
        action="login.success",
        resource="auth",
        details=f"auth_method=password; username={username}",
        ip_address=source_ip,
        user_agent=user_agent[:500],
        trace_id=trace_id,
    )


@router.post("/login")
async def login(request: Request, payload: dict):
    """Authenticate a user and issue a signed bearer token."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"
    username = str(payload.get("username", "") or "").strip()
    password = str(payload.get("password", "") or "")

    with tracer.start_as_current_span("auth.login") as span:
        auth_fields = _auth_flow_fields(username=username, source_ip=source_ip)
        apply_span_attributes(span, auth_fields)

        if not username or not password:
            business_metrics.record_login_failure(reason="missing_credentials")
            apply_span_attributes(span, {"http.status_code": 400, "otel.status_code": "ERROR"})
            push_log(
                "WARNING",
                "Login request rejected",
                **{
                    **auth_fields,
                    "auth.result": "missing_credentials",
                    "http.url.path": "/api/auth/login",
                    "http.method": "POST",
                    "http.status_code": 400,
                },
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password are required")

        if login_rate_limited(source_ip):
            business_metrics.record_login_failure(reason="rate_limited")
            security_span(
                "brute_force",
                severity="medium",
                payload=username,
                source_ip=source_ip,
                endpoint="/api/auth/login",
            )
            apply_span_attributes(span, {"auth.result": "rate_limited", "http.status_code": 429, "otel.status_code": "ERROR"})
            push_log(
                "WARNING",
                "Login request rate limited",
                **{
                    **auth_fields,
                    "auth.result": "rate_limited",
                    "http.url.path": "/api/auth/login",
                    "http.method": "POST",
                    "http.status_code": 429,
                },
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.auth_user_lookup") as db_span:
                apply_span_attributes(db_span, auth_fields)
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
                business_metrics.record_login_failure(reason="invalid_credentials")
                security_span(
                    "brute_force",
                    severity="low",
                    payload=username,
                    source_ip=source_ip,
                    endpoint="/api/auth/login",
                )
                apply_span_attributes(
                    span,
                    {
                        "auth.result": "invalid_credentials",
                        "auth.user_found": bool(user),
                        "http.status_code": 401,
                        "otel.status_code": "ERROR",
                    },
                )
                push_log(
                    "WARNING",
                    "Login failed",
                    **{
                        **auth_fields,
                        "auth.result": "invalid_credentials",
                        "auth.user_found": bool(user),
                        "http.url.path": "/api/auth/login",
                        "http.method": "POST",
                        "http.status_code": 401,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                )

            user_fields = {
                **auth_fields,
                "auth.user_id": int(user["id"]),
                "auth.role": str(user["role"]),
                "auth.result": "success",
            }
            with tracer.start_as_current_span("db.query.auth_last_login_update") as db_span:
                apply_span_attributes(db_span, user_fields)
                await db.execute(
                    text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": user["id"]},
                )
            with tracer.start_as_current_span("db.query.auth_audit_log") as db_span:
                apply_span_attributes(db_span, user_fields)
                await db.execute(
                    _login_audit_insert(
                        user_id=int(user["id"]),
                        username=str(user["username"]),
                        source_ip=source_ip,
                        user_agent=request.headers.get("user-agent", ""),
                        trace_id=_trace_id(),
                    )
                )

        register_login_attempt(source_ip, success=True)
        token = issue_token(user_id=int(user["id"]), username=str(user["username"]), role=str(user["role"]))
        business_metrics.record_login_success(method="password")
        apply_span_attributes(
            span,
            {
                "auth.result": "success",
                "auth.user_id": int(user["id"]),
                "auth.role": str(user["role"]),
                "http.status_code": 200,
            },
        )
        push_log(
            "INFO",
            "Login succeeded",
            **{
                **auth_fields,
                "auth.result": "success",
                "auth.user_id": int(user["id"]),
                "auth.role": str(user["role"]),
                "http.url.path": "/api/auth/login",
                "http.method": "POST",
                "http.status_code": 200,
            },
        )
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
