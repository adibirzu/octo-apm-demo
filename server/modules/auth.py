"""Authentication module — OWASP A07: Identification and Authentication Failures.

Vulnerabilities:
- Weak password hashing (intentionally uses md5 fallback)
- No rate limiting on login endpoint
- JWT with weak secret
- Session fixation via cookie
- Username enumeration through different error messages

Includes IDCS SSO integration via OIDC Authorization Code + PKCE.
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
tracer_fn = get_tracer

# DB-backed session store — shared across all OKE replicas via ATP
_login_attempts: dict[str, list[float]] = {}
import hmac


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Login endpoint — vulnerable to brute force (no rate limiting)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.username", req.username)
        span.set_attribute("auth.client_ip", client_ip)

        # Track attempts (but don't enforce — intentional vuln)
        _login_attempts.setdefault(client_ip, []).append(time.time())

        if len(_login_attempts.get(client_ip, [])) > cfg.max_login_attempts:
            with security_span("broken_auth", severity="high",
                             payload=f"brute force: {len(_login_attempts[client_ip])} attempts",
                             source_ip=client_ip, username=req.username):
                log_security_event("broken_auth", "high",
                    f"Brute force detected from {client_ip}: {len(_login_attempts[client_ip])} attempts",
                    source_ip=client_ip, username=req.username)

        async with get_db() as db:
            # VULN: Username enumeration — different error messages
            with tracer.start_as_current_span("db.user_lookup") as db_span:
                result = await db.execute(
                    text("SELECT id, username, password_hash, role FROM users WHERE username = :u"),
                    {"u": req.username}
                )
                user = result.fetchone()

            if user is None:
                span.set_attribute("auth.result", "user_not_found")
                return {"error": "User not found", "status": "failed"}  # VULN: enumeration

            # VULN: Weak password check (md5 fallback)
            with tracer.start_as_current_span("auth.password_verify") as pw_span:
                md5_hash = hashlib.md5(req.password.encode()).hexdigest()
                if user.password_hash != md5_hash and not _check_bcrypt(req.password, user.password_hash):
                    span.set_attribute("auth.result", "invalid_password")
                    return {"error": "Invalid password", "status": "failed"}  # VULN: enumeration

            # Create session in ATP — shared across all OKE replicas
            session_id = hashlib.md5(f"{user.username}{time.time()}".encode()).hexdigest()
            await db.execute(
                text(
                    "INSERT INTO user_sessions (session_id, user_id, username, role, auth_method) "
                    "VALUES (:sid, :uid, :uname, :role, 'password')"
                ),
                {"sid": session_id, "uid": user.id, "uname": user.username, "role": user.role},
            )

            response.set_cookie("session_id", session_id, httponly=False, samesite="none")

            push_log("INFO", f"User {req.username} logged in", **{
                "auth.username": req.username,
                "auth.role": user.role,
                "http.client_ip": client_ip,
            })

            return {
                "status": "success",
                "session_id": session_id,  # VULN: exposing session ID in response body
                "user": {"id": user.id, "username": user.username, "role": user.role}
            }


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    """Register — vulnerable to mass assignment (role field accepted from request)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.register") as span:
        body = await request.json()

        # VULN: Mass assignment — accepts 'role' from user input
        role = body.get("role", "user")
        if role == "admin":
            with security_span("mass_assignment", severity="critical",
                             payload=f"role escalation attempt: {role}",
                             source_ip=client_ip, username=req.username):
                log_security_event("mass_assignment", "critical",
                    f"Admin role assignment attempt by {req.username}",
                    source_ip=client_ip, username=req.username)

        # VULN: Weak password hashing (md5)
        password_hash = hashlib.md5(req.password.encode()).hexdigest()

        async with get_db() as db:
            with tracer.start_as_current_span("db.user_create"):
                await db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:u, :e, :p, :r)"),
                    {"u": req.username, "e": req.email, "p": password_hash, "r": role}
                )

        return {"status": "created", "username": req.username, "role": role}


@router.get("/session")
async def get_session(request: Request):
    """Return session info from ATP database."""
    session_id = request.cookies.get("session_id") or request.query_params.get("session_id", "")
    if not session_id:
        return {"authenticated": False}
    async with get_db() as db:
        result = await db.execute(
            text("SELECT user_id, username, role, auth_method FROM user_sessions WHERE session_id = :sid"),
            {"sid": session_id},
        )
        row = result.mappings().first()
    if not row:
        return {"authenticated": False}
    return {"authenticated": True, "user_id": row["user_id"], "username": row["username"], "role": row["role"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id", "")
    if session_id:
        async with get_db() as db:
            await db.execute(text("DELETE FROM user_sessions WHERE session_id = :sid"), {"sid": session_id})
    response.delete_cookie("session_id")
    return {"status": "logged_out"}


_session_cache: dict[str, tuple[float, dict]] = {}
_SESSION_CACHE_TTL = 30  # seconds — keeps DB queries low while staying fresh across replicas


def get_current_user(request: Request) -> dict | None:
    """Look up session in local cache, then fall back to ATP database."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id", "")
    if not session_id:
        return None

    # Check local cache first
    cached = _session_cache.get(session_id)
    if cached:
        ts, user_data = cached
        if time.time() - ts < _SESSION_CACHE_TTL:
            return user_data

    # Synchronous DB lookup (called from sync middleware context)
    try:
        from server.database import sync_engine
        from sqlalchemy import text as sa_text
        with sync_engine.connect() as conn:
            row = conn.execute(
                sa_text("SELECT user_id, username, role FROM user_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).mappings().first()
        if row:
            user_data = {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}
            _session_cache[session_id] = (time.time(), user_data)
            return user_data
    except Exception:
        pass

    _session_cache.pop(session_id, None)
    return None


def _check_bcrypt(password: str, hash_str: str) -> bool:
    try:
        from passlib.hash import bcrypt
        return bcrypt.verify(password, hash_str)
    except Exception:
        return False


# ── IDCS SSO (OIDC Authorization Code + PKCE) ────────────────────
# PKCE state is stored in a signed cookie so it works across replicas.


def _sign_value(value: str) -> str:
    """Create HMAC signature for a value using the app secret."""
    sig = hmac.new(cfg.app_secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{value}.{sig}"


def _verify_signed(signed: str) -> str | None:
    """Verify and extract value from signed string."""
    if "." not in signed:
        return None
    value, sig = signed.rsplit(".", 1)
    expected = hmac.new(cfg.app_secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        return None
    return value


@router.get("/sso/login")
async def sso_login():
    """Initiate OIDC Authorization Code flow with PKCE to IDCS."""
    if not cfg.idcs_configured:
        return {"error": "SSO not configured"}

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    params = {
        "response_type": "code",
        "client_id": cfg.idcs_client_id,
        "redirect_uri": cfg.idcs_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{cfg.idcs_domain_url}/oauth2/v1/authorize?{urlencode(params)}"

    # Store code_verifier + state in a signed cookie (works across replicas)
    cookie_value = _sign_value(f"{state}:{code_verifier}")
    redirect = RedirectResponse(url=auth_url)
    redirect.set_cookie("_sso_pkce", cookie_value, httponly=True, max_age=600, samesite="lax")
    return redirect


@router.get("/sso/callback")
async def sso_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """OIDC callback — exchange authorization code for tokens."""
    tracer = tracer_fn()

    if error:
        push_log("WARN", f"SSO callback error: {error}")
        return RedirectResponse(url=f"/login?error={error}")

    # Recover code_verifier from signed cookie
    pkce_cookie = request.cookies.get("_sso_pkce", "")
    pkce_data = _verify_signed(pkce_cookie) if pkce_cookie else None
    if not pkce_data or ":" not in pkce_data:
        push_log("WARN", "SSO callback with missing PKCE cookie")
        return RedirectResponse(url="/login?error=invalid_state")

    stored_state, code_verifier = pkce_data.split(":", 1)
    if not hmac.compare_digest(stored_state, state):
        push_log("WARN", "SSO callback with mismatched state")
        return RedirectResponse(url="/login?error=invalid_state")

    with tracer.start_as_current_span("auth.sso_callback") as span:
        # Exchange authorization code for tokens
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                f"{cfg.idcs_domain_url}/oauth2/v1/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg.idcs_redirect_uri,
                    "code_verifier": code_verifier,
                },
                auth=(cfg.idcs_client_id, cfg.idcs_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_resp.status_code != 200:
            span.set_attribute("auth.sso_error", token_resp.text[:500])
            push_log("ERROR", f"SSO token exchange failed: {token_resp.status_code}", **{
                "auth.sso_status": token_resp.status_code,
                "auth.sso_error": token_resp.text[:200],
            })
            return RedirectResponse(url="/login?error=token_exchange_failed")

        tokens = token_resp.json()
        id_token = tokens.get("id_token", "")

        # Decode ID token claims (unverified — demo app)
        claims = _decode_jwt_claims(id_token)
        if not claims:
            return RedirectResponse(url="/login?error=invalid_token")

        email = claims.get("email", claims.get("sub", ""))
        display_name = claims.get("name", claims.get("preferred_username", email.split("@")[0]))
        idcs_sub = claims.get("sub", "")
        username = display_name.lower().replace(" ", ".") if display_name else email.split("@")[0]

        span.set_attribute("auth.sso_email", email)
        span.set_attribute("auth.sso_sub", idcs_sub)

        # Auto-provision or lookup user in CRM database
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, username, role FROM users WHERE email = :email"),
                {"email": email}
            )
            user = result.fetchone()

            if user is None:
                await db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:u, :e, :p, :r)"),
                    {"u": username, "e": email, "p": f"sso:{idcs_sub}", "r": "user"}
                )
                result = await db.execute(
                    text("SELECT id, username, role FROM users WHERE email = :email"),
                    {"email": email}
                )
                user = result.fetchone()
                push_log("INFO", f"SSO auto-provisioned user: {username}", **{
                    "auth.method": "idcs_sso",
                    "auth.username": username,
                    "auth.email": email,
                })

        # Create session in ATP (shared across all OKE replicas)
        session_id = hashlib.md5(f"{user.username}{time.time()}".encode()).hexdigest()
        async with get_db() as sess_db:
            await sess_db.execute(
                text(
                    "INSERT INTO user_sessions (session_id, user_id, username, role, auth_method) "
                    "VALUES (:sid, :uid, :uname, :role, 'sso')"
                ),
                {"sid": session_id, "uid": user.id, "uname": user.username, "role": user.role},
            )

        push_log("INFO", f"SSO login: {user.username}", **{
            "auth.username": user.username,
            "auth.method": "idcs_sso",
            "auth.idcs_sub": idcs_sub,
            "auth.role": user.role,
        })

        redirect = RedirectResponse(url="/", status_code=302)
        redirect.set_cookie("session_id", session_id, httponly=False, samesite="none")
        redirect.delete_cookie("_sso_pkce")
        return redirect


@router.get("/sso/status")
async def sso_status():
    """Check if SSO is configured."""
    return {
        "configured": cfg.idcs_configured,
        "provider": "OCI Identity Domain (IDCS)" if cfg.idcs_configured else None,
        "domain_url": cfg.idcs_domain_url if cfg.idcs_configured else None,
    }


def _decode_jwt_claims(token: str) -> dict | None:
    """Decode JWT claims without signature verification (demo app)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Decode the payload (second part)
        payload = parts[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        import json
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
