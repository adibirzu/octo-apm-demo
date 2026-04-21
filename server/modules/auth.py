"""Authentication module with local login and IDCS SSO support."""

import base64
import hashlib
import logging
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
from server.observability import business_metrics
from server.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
tracer_fn = get_tracer

import hmac

# DB-backed session store — shared across all OKE replicas via ATP
_login_attempts: dict[str, list[float]] = {}
LOGIN_WINDOW_SECONDS = 300


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Login endpoint with rate limiting and httpOnly session cookies."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.username", req.username)
        span.set_attribute("auth.client_ip", client_ip)

        attempts = _login_attempts.setdefault(client_ip, [])
        now = time.time()
        attempts[:] = [ts for ts in attempts if now - ts <= LOGIN_WINDOW_SECONDS]
        if len(attempts) >= cfg.max_login_attempts:
            with security_span(
                "broken_auth",
                severity="high",
                payload=f"rate limit: {len(attempts)} attempts",
                source_ip=client_ip,
                username=req.username,
            ):
                log_security_event(
                    "broken_auth",
                    "high",
                    f"Login rate limit exceeded from {client_ip}",
                    source_ip=client_ip,
                    username=req.username,
                )
            response.status_code = 429
            return {"error": "Too many login attempts. Try again later.", "status": "rate_limited"}

        async with get_db() as db:
            with tracer.start_as_current_span("db.user_lookup") as db_span:
                # Look up by username, then try crm-prefixed variant, then by email
                # Prefer CRM-owned users (crm-enterprise.local email) over Shop users
                result = await db.execute(
                    text("SELECT id, username, password_hash, role FROM users "
                         "WHERE username = :u OR username = :crm_u OR email = :email "
                         "ORDER BY CASE WHEN email LIKE '%@crm-enterprise.local' THEN 0 ELSE 1 END, "
                         "CASE WHEN username = :u THEN 0 WHEN username = :crm_u THEN 1 ELSE 2 END "
                         "FETCH FIRST 1 ROWS ONLY"),
                    {"u": req.username, "crm_u": f"crm-{req.username}", "email": req.username}
                )
                user = result.fetchone()

            if user is None:
                span.set_attribute("auth.result", "user_not_found")
                business_metrics.record_login_failure(reason="user_not_found")
                attempts.append(time.time())
                return {"error": "Invalid credentials", "status": "failed"}

            with tracer.start_as_current_span("auth.password_verify") as pw_span:
                if not _check_bcrypt(req.password, user.password_hash):
                    span.set_attribute("auth.result", "invalid_password")
                    business_metrics.record_login_failure(reason="invalid_password")
                    attempts.append(time.time())
                    return {"error": "Invalid credentials", "status": "failed"}

            # Create session in ATP — shared across all OKE replicas
            session_id = secrets.token_hex(32)
            await db.execute(
                text(
                    "INSERT INTO user_sessions (session_id, user_id, username, role, auth_method) "
                    "VALUES (:sid, :uid, :uname, :role, 'password')"
                ),
                {"sid": session_id, "uid": user.id, "uname": user.username, "role": user.role},
            )

            # Derive secure flag from the request scheme so the cookie works
            # over plain HTTP (OKE LBs without TLS) as well as HTTPS.
            is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                "session_id", session_id,
                httponly=True,
                samesite="lax",
                secure=is_https,
                max_age=cfg.session_timeout_seconds,
            )
            _login_attempts.pop(client_ip, None)

            business_metrics.record_login_success(method="password", role=user.role or "user")
            push_log("INFO", f"User {req.username} logged in", **{
                "auth.username": req.username,
                "auth.role": user.role,
                "http.client_ip": client_ip,
            })

            return {
                "status": "success",
                "user": {"id": user.id, "username": user.username, "role": user.role}
            }


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    """Register a local CRM user with a fixed non-admin role."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.register") as span:
        body = await request.json()

        role = "user"
        requested_role = str(body.get("role", "")).strip().lower()
        if requested_role and requested_role != role:
            with security_span(
                "mass_assignment",
                severity="high",
                payload=f"ignored requested role: {requested_role}",
                source_ip=client_ip,
                username=req.username,
            ):
                log_security_event(
                    "mass_assignment",
                    "high",
                    f"Ignored role assignment attempt by {req.username}",
                    source_ip=client_ip,
                    username=req.username,
                )

        from passlib.hash import bcrypt

        password_hash = bcrypt.hash(req.password)

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
    session_id = request.cookies.get("session_id", "")
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
        business_metrics.record_logout()
    response.delete_cookie("session_id")
    return {"status": "logged_out"}


_session_cache: dict[str, tuple[float, dict]] = {}
_SESSION_CACHE_TTL = 30  # seconds — keeps DB queries low while staying fresh across replicas

# Rate-limit for session-lookup error logging. Without this, a DB outage
# produces one warning per protected request (see KB-435), which drowns the
# log and burns APM quota. We log at most one message per window per
# exception class.
_SESSION_LOOKUP_LOG_WINDOW_S = 60.0
_session_lookup_log_state: dict[str, float] = {}


class SessionLookupUnavailable(Exception):
    """Raised when the session store is reachable but the lookup failed due to
    an infrastructure error (DB down, pool timeout, credential rotation, etc).

    This is deliberately distinct from `get_current_user()` returning `None`:
    - `None`           → the cookie does not match any known session.
    - this exception   → we could not determine whether the session is valid.
    Callers (e.g. the session gate middleware) MUST treat the two differently.
    Conflating them turns every DB hiccup into a fleet-wide forced logout.
    """


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
    except Exception as e:
        # Anti-footgun rules (see KB-435):
        #   1. Never interpolate the exception message — SQLAlchemy's
        #      DatabaseError.__str__ embeds the SQL and its bound parameters,
        #      which would leak the raw session_id (a live credential) into
        #      stdout/APM. We log only the exception class name and the
        #      driver-level error code (ORA-xxxxx) when we can extract it.
        #   2. Never include any portion of the session_id. Even a prefix is
        #      credential-derived material and is useless for correlation.
        #   3. Never return None here — that would conflate "unknown session"
        #      with "can't reach the session store", causing DB outages to
        #      look like mass logouts. Raise a typed exception instead so
        #      the middleware can return 503 and keep users signed in.
        # We rate-limit per exception class so a DB outage doesn't become a
        # per-request warning storm.
        _err_class = type(e).__name__

        # Extract a safe driver code (e.g. ORA-01017) without the SQL text.
        _err_code = ""
        orig = getattr(e, "orig", None)
        for candidate in (orig, e):
            if candidate is None:
                continue
            code = getattr(candidate, "code", None) or getattr(candidate, "full_code", None)
            if code:
                _err_code = str(code)
                break
            # oracledb exceptions expose `args` like (Error(message='ORA-01017: ...'),)
            args = getattr(candidate, "args", None)
            if args:
                first = str(args[0])
                # Pull an ORA-xxxxx token from the start of the message only
                # — never the full message, which can include bind values.
                if first.startswith("ORA-") and ":" in first:
                    _err_code = first.split(":", 1)[0]
                    break

        now = time.time()
        last = _session_lookup_log_state.get(_err_class, 0.0)
        if now - last > _SESSION_LOOKUP_LOG_WINDOW_S:
            _session_lookup_log_state[_err_class] = now
            logger.warning(
                "session lookup failed (rate-limited): class=%s code=%s "
                "(suppressing duplicates for %ss)",
                _err_class, _err_code or "unknown", int(_SESSION_LOOKUP_LOG_WINDOW_S),
            )
        raise SessionLookupUnavailable(f"{_err_class}:{_err_code}") from e

    # Miss: cookie did not resolve to any row, so this really is "no session".
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


# ── OIDC discovery + JWKS cache ───────────────────────────────────
# Fetched once at first SSO login, cached in-process for 1 hour. IDCS rotates
# signing keys rarely so aggressive caching is safe, and refreshing on a
# `kid` miss means we self-heal when rotation eventually happens.
_oidc_discovery_cache: dict[str, tuple[float, dict]] = {}
_jwks_cache: dict[str, tuple[float, dict]] = {}
_OIDC_CACHE_TTL_S = 3600.0


async def _fetch_oidc_discovery(issuer_base: str) -> dict:
    """Fetch and cache the OIDC discovery document for an identity domain."""
    cached = _oidc_discovery_cache.get(issuer_base)
    if cached and time.time() - cached[0] < _OIDC_CACHE_TTL_S:
        return cached[1]
    url = f"{issuer_base}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        doc = resp.json()
    _oidc_discovery_cache[issuer_base] = (time.time(), doc)
    return doc


async def _fetch_jwks(jwks_uri: str, force_refresh: bool = False) -> dict:
    """Fetch and cache the JWKS (public signing keys) from the identity domain."""
    if not force_refresh:
        cached = _jwks_cache.get(jwks_uri)
        if cached and time.time() - cached[0] < _OIDC_CACHE_TTL_S:
            return cached[1]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        jwks = resp.json()
    _jwks_cache[jwks_uri] = (time.time(), jwks)
    return jwks


async def _verify_id_token(
    id_token: str,
    expected_nonce: str,
    expected_audience: str,
) -> dict | None:
    """Fully verify an OIDC ID token.

    Checks, in order:
      1. JWT structure + header (must have `kid` and a supported `alg`).
      2. Signature against the issuer's JWKS (refreshes the JWKS once on kid
         miss so we survive key rotation without a restart).
      3. `iss` matches the discovery document's `issuer` field.
      4. `aud` matches the CRM's registered client_id.
      5. `exp` is in the future (jose does this automatically).
      6. `nonce` matches the value the server sent in the authorize request.

    Returns the verified claims dict on success, or `None` on any failure.
    """
    from jose import jwt, jwk, exceptions as jose_exc

    try:
        discovery = await _fetch_oidc_discovery(cfg.idcs_domain_url)
    except Exception as e:
        logger.warning("OIDC discovery fetch failed: %s", type(e).__name__)
        return None

    jwks_uri = discovery.get("jwks_uri")
    expected_issuer = discovery.get("issuer")
    if not jwks_uri or not expected_issuer:
        logger.warning("OIDC discovery missing jwks_uri or issuer")
        return None

    # Extract kid from the unverified header to select the right JWK
    try:
        unverified_header = jwt.get_unverified_header(id_token)
    except jose_exc.JWTError:
        logger.warning("ID token has malformed header")
        return None
    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg", "RS256")
    if alg not in ("RS256", "RS384", "RS512"):
        logger.warning("ID token uses unsupported alg: %s", alg)
        return None

    # Try cached JWKS first, then refresh on miss
    async def _find_key():
        for force in (False, True):
            try:
                jwks = await _fetch_jwks(jwks_uri, force_refresh=force)
            except Exception as e:
                logger.warning("JWKS fetch failed: %s", type(e).__name__)
                return None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    return key_data
        return None

    key_data = await _find_key()
    if not key_data:
        logger.warning("ID token kid not found in JWKS")
        return None

    try:
        claims = jwt.decode(
            id_token,
            jwk.construct(key_data).to_dict(),
            algorithms=[alg],
            audience=expected_audience,
            issuer=expected_issuer,
            options={"verify_at_hash": False},  # we don't pass access_token
        )
    except jose_exc.ExpiredSignatureError:
        logger.warning("ID token expired")
        return None
    except jose_exc.JWTClaimsError as e:
        logger.warning("ID token claims invalid: %s", type(e).__name__)
        return None
    except jose_exc.JWTError as e:
        logger.warning("ID token signature invalid: %s", type(e).__name__)
        return None

    # Nonce check is not done by jose.decode — verify manually.
    if not expected_nonce or claims.get("nonce") != expected_nonce:
        logger.warning("ID token nonce mismatch")
        return None

    return claims


@router.get("/sso/login")
async def sso_login(request: Request):
    """Initiate OIDC Authorization Code flow with PKCE to IDCS."""
    if not cfg.idcs_configured:
        return {"error": "SSO not configured"}

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    params = {
        "response_type": "code",
        "client_id": cfg.idcs_client_id,
        "redirect_uri": cfg.idcs_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{cfg.idcs_domain_url}/oauth2/v1/authorize?{urlencode(params)}"

    # Store code_verifier + state + nonce in a signed cookie. state, verifier,
    # and nonce are all `token_urlsafe(...)` output (url-safe base64), which
    # never contains `:`, so we can use `:` as a safe separator.
    cookie_value = _sign_value(f"{state}:{code_verifier}:{nonce}")
    redirect = RedirectResponse(url=auth_url)
    # Match the session cookie's security profile: Secure on HTTPS, HttpOnly
    # always (the PKCE cookie is never read from JS), SameSite=lax so it
    # survives the cross-site redirect from IDCS back to us.
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    redirect.set_cookie(
        "_sso_pkce", cookie_value,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=is_https,
    )
    return redirect


@router.get("/sso/callback")
async def sso_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """OIDC callback — verify ID token and mint a CRM session.

    Security-hardened path (see KB-435 follow-up):
      - Full ID token verification: JWKS signature, iss, aud, exp, nonce.
      - Nonce stored server-side in the signed PKCE cookie, verified on
        return to prevent token replay across authorize requests.
      - Session cookie flags mirror the password-login path: Secure on
        HTTPS, SameSite tuned for the scheme, HttpOnly to keep the session
        token out of JS (tightening the intentional 'Session fixation via
        cookie' demo vuln — SSO is the hardened path).
      - Case-insensitive email lookup to avoid duplicate user provisioning
        when IDCS returns differently-cased email on successive logins.
      - Handles shared-ATP username collisions with octo-drone-shop by
        retrying the INSERT with a `crm-` prefix, mirroring the local-login
        fix from commit 146a659.
    """
    tracer = tracer_fn()

    if error:
        push_log("WARN", f"SSO callback error: {error}")
        return RedirectResponse(url=f"/login?error={error}")

    # Recover state + code_verifier + nonce from the signed PKCE cookie.
    pkce_cookie = request.cookies.get("_sso_pkce", "")
    pkce_data = _verify_signed(pkce_cookie) if pkce_cookie else None
    if not pkce_data:
        push_log("WARN", "SSO callback with missing PKCE cookie")
        return RedirectResponse(url="/login?error=invalid_state")

    parts = pkce_data.split(":", 2)
    if len(parts) != 3:
        # Legacy (pre-nonce) cookie format — force re-init of the flow.
        push_log("WARN", "SSO callback with legacy PKCE cookie format")
        return RedirectResponse(url="/login?error=invalid_state")
    stored_state, code_verifier, stored_nonce = parts

    if not hmac.compare_digest(stored_state, state):
        push_log("WARN", "SSO callback with mismatched state")
        return RedirectResponse(url="/login?error=invalid_state")

    with tracer.start_as_current_span("auth.sso_callback") as span:
        # Exchange authorization code for tokens.
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
        if not id_token:
            push_log("WARN", "SSO token response missing id_token")
            return RedirectResponse(url="/login?error=invalid_token")

        # Fully verify the ID token: signature, iss, aud, exp, nonce.
        claims = await _verify_id_token(
            id_token,
            expected_nonce=stored_nonce,
            expected_audience=cfg.idcs_client_id,
        )
        if claims is None:
            push_log("WARN", "SSO ID token validation failed")
            return RedirectResponse(url="/login?error=invalid_token")

        email_raw = claims.get("email") or claims.get("sub") or ""
        email = email_raw.strip().lower()
        display_name = claims.get("name") or claims.get("preferred_username") or email.split("@")[0]
        idcs_sub = claims.get("sub", "")
        base_username = (display_name or "").lower().replace(" ", ".") or email.split("@")[0]

        span.set_attribute("auth.sso_email", email)
        span.set_attribute("auth.sso_sub", idcs_sub)

        # Auto-provision or lookup user. Lookup is case-insensitive on email
        # so mixed-case returns from IDCS don't create duplicates. Provision
        # handles the shared-ATP username collision by retrying with a
        # `crm-` prefix (same strategy as the local login path).
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, username, role FROM users WHERE LOWER(email) = :email"),
                {"email": email},
            )
            user = result.fetchone()

            if user is None:
                # Try the plain username first, then fall back to the prefixed
                # form if the INSERT collides on the unique index.
                insert_sql = text(
                    "INSERT INTO users (username, email, password_hash, role) "
                    "VALUES (:u, :e, :p, :r)"
                )
                placeholder_hash = f"sso:{idcs_sub}"
                try:
                    await db.execute(
                        insert_sql,
                        {"u": base_username, "e": email, "p": placeholder_hash, "r": "user"},
                    )
                    provisioned_username = base_username
                except Exception as first_err:
                    # On unique-constraint failure, retry with the crm- prefix.
                    # Any other DB error is non-recoverable — log and surface.
                    err_msg = str(first_err).upper()
                    if "ORA-00001" not in err_msg and "UNIQUE" not in err_msg:
                        logger.warning(
                            "SSO user provisioning failed with non-unique error: %s",
                            type(first_err).__name__,
                        )
                        raise
                    provisioned_username = f"crm-{base_username}"
                    await db.execute(
                        insert_sql,
                        {"u": provisioned_username, "e": email, "p": placeholder_hash, "r": "user"},
                    )

                result = await db.execute(
                    text("SELECT id, username, role FROM users WHERE LOWER(email) = :email"),
                    {"email": email},
                )
                user = result.fetchone()
                push_log("INFO", f"SSO auto-provisioned user: {provisioned_username}", **{
                    "auth.method": "idcs_sso",
                    "auth.username": provisioned_username,
                    "auth.email": email,
                })

        if user is None:
            # Defensive: provisioning ran but we still can't read the user back.
            push_log("ERROR", "SSO user missing after provisioning")
            return RedirectResponse(url="/login?error=provisioning_failed")

        # Create session in ATP (shared across all OKE replicas).
        # The SSO path uses a strong random session ID instead of the
        # intentionally-weak md5 session id used by the password login demo
        # vuln path.
        session_id = secrets.token_hex(32)
        async with get_db() as sess_db:
            await sess_db.execute(
                text(
                    "INSERT INTO user_sessions (session_id, user_id, username, role, auth_method) "
                    "VALUES (:sid, :uid, :uname, :role, 'sso')"
                ),
                {"sid": session_id, "uid": user.id, "uname": user.username, "role": user.role},
            )

        business_metrics.record_login_success(method="sso", role=user.role or "user")
        push_log("INFO", f"SSO login: {user.username}", **{
            "auth.username": user.username,
            "auth.method": "idcs_sso",
            "auth.idcs_sub": idcs_sub,
            "auth.role": user.role,
        })

        # Set the session cookie with the proper security profile. This was
        # the single bug that made SSO appear to be broken in prod: on HTTPS,
        # `SameSite=None` without `Secure` is silently dropped by Chrome.
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        )
        redirect = RedirectResponse(url="/", status_code=302)
        redirect.set_cookie(
            "session_id", session_id,
            httponly=True,  # SSO path is hardened; JS cannot read the token
            samesite="none" if is_https else "lax",
            secure=is_https,
        )
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
