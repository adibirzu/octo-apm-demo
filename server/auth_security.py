"""Authentication helpers for signed bearer tokens and basic rate limiting.

Security model
==============
- The HMAC-SHA256 signing key for issued bearer tokens is derived from
  ``AUTH_TOKEN_SECRET`` only.
- In production (``ENVIRONMENT=production``), :func:`server.config.Config.validate`
  refuses to start if the env var is missing — there is no silent fallback to
  database credentials or hardcoded literals (CRIT-1).
- Outside production, a per-process random secret is generated once on first
  use so local ``docker-compose up`` keeps working without ceremony. A loud
  warning is logged so operators know tokens won't survive a process restart.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets as _secrets
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, status

from server.config import cfg

logger = logging.getLogger(__name__)

LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 8
TOKEN_TTL_SECONDS = 60 * 60 * 8

_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_ephemeral_secret: bytes | None = None


def _resolve_secret_material() -> str:
    global _ephemeral_secret
    explicit = (cfg.auth_token_secret or os.getenv("AUTH_TOKEN_SECRET", "")).strip()
    if explicit:
        return explicit

    if cfg.is_production:
        # Defence in depth — Config.validate() should already have raised, but
        # this guarantees we never sign with a known/empty key in prod.
        raise RuntimeError(
            "AUTH_TOKEN_SECRET is required in production but was not provided."
        )

    if _ephemeral_secret is None:
        _ephemeral_secret = _secrets.token_bytes(32)
        logger.warning(
            "AUTH_TOKEN_SECRET not set — generated an ephemeral signing key for "
            "this process. Tokens will be invalidated on restart. Set "
            "AUTH_TOKEN_SECRET in production-like environments."
        )
    return _ephemeral_secret.hex()


def _secret_bytes() -> bytes:
    return hashlib.sha256(_resolve_secret_material().encode("utf-8")).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _sign(value: str) -> str:
    digest = hmac.new(_secret_bytes(), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


SESSION_COOKIE_NAME = "octo_session"


def issue_token(
    *,
    user_id: int,
    username: str,
    role: str,
    auth_method: str = "password",
    ttl_seconds: int = TOKEN_TTL_SECONDS,
) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "auth_method": auth_method,
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None

    if not hmac.compare_digest(signature, _sign(body)):
        return None

    try:
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    if int(payload.get("exp", 0) or 0) <= int(time.time()):
        return None
    return payload


def login_rate_limited(source_ip: str) -> bool:
    now = time.time()
    attempts = _login_attempts[source_ip]
    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def register_login_attempt(source_ip: str, success: bool) -> None:
    if success:
        _login_attempts.pop(source_ip, None)
        return

    attempts = _login_attempts[source_ip]
    attempts.append(time.time())


def _extract_token(request: Request) -> str | None:
    """Extract a bearer token from either the Authorization header or the
    ``octo_session`` httpOnly cookie (set by the SSO callback).

    Returns ``None`` if neither source contains a token.
    """
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "", 1).strip() or None

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    return cookie_token or None


def get_bearer_token(request: Request) -> str:
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return token


def require_authenticated_user(request: Request) -> dict[str, Any]:
    token = get_bearer_token(request)
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


def require_sso_user(request: Request) -> dict[str, Any]:
    """Require a valid token that was issued through the IDCS SSO flow.

    The ``auth_method`` claim is embedded at token-issue time by
    ``server.modules.sso`` and cannot be forged (HMAC-signed).
    """
    payload = require_authenticated_user(request)
    if payload.get("auth_method") != "sso":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires IDCS SSO authentication",
        )
    return payload


def require_role(request: Request, *roles: str) -> dict[str, Any]:
    payload = require_authenticated_user(request)
    if roles and payload.get("role") not in set(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return payload
