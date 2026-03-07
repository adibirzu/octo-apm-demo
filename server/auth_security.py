"""Authentication helpers for signed bearer tokens and basic rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, status

from server.config import cfg

LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 8
TOKEN_TTL_SECONDS = 60 * 60 * 8

_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def _secret_bytes() -> bytes:
    basis = (
        cfg.auth_token_secret
        or cfg.oracle_password
        or cfg.splunk_hec_token
        or cfg.oracle_dsn
        or f"{cfg.app_name}:{cfg.environment}:octo-default-secret"
    )
    return hashlib.sha256(basis.encode("utf-8")).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _sign(value: str) -> str:
    digest = hmac.new(_secret_bytes(), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def issue_token(*, user_id: int, username: str, role: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
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


def get_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return auth_header.replace("Bearer ", "", 1).strip()


def require_authenticated_user(request: Request) -> dict[str, Any]:
    token = get_bearer_token(request)
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
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
