"""API key management module — OWASP A02: Cryptographic Failures.

Vulnerabilities:
- Weak API key generation (predictable)
- API keys stored in plaintext
- No key rotation mechanism
- Key enumeration via timing attack
"""

import hashlib
import time

from fastapi import APIRouter, Request
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db

router = APIRouter(prefix="/api/keys", tags=["API Keys"])
tracer_fn = get_tracer

# In-memory key store (intentionally insecure)
_api_keys: dict[str, dict] = {}


@router.post("/generate")
async def generate_api_key(request: Request):
    """Generate API key — VULN: predictable key generation."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("api_keys.generate") as span:
        username = body.get("username", "anonymous")

        # VULN: Predictable key generation based on timestamp + username
        key_seed = f"{username}{int(time.time())}"
        api_key = hashlib.md5(key_seed.encode()).hexdigest()

        with security_span("sensitive_data", severity="medium",
                         source_ip=client_ip, username=username,
                         payload="weak api key generation"):
            pass

        _api_keys[api_key] = {
            "username": username,
            "created_at": time.time(),
            "permissions": body.get("permissions", ["read"]),
        }

        push_log("INFO", f"API key generated for {username}", **{
            "api_keys.username": username,
        })
        # VULN: Returns full key in response
        return {"api_key": api_key, "username": username}


@router.get("/validate")
async def validate_api_key(request: Request):
    """Validate API key — VULN: timing attack (non-constant-time comparison)."""
    tracer = tracer_fn()
    key = request.headers.get("x-api-key", "")

    with tracer.start_as_current_span("api_keys.validate") as span:
        # VULN: Non-constant-time comparison enables timing attack
        if key in _api_keys:
            return {"valid": True, "user": _api_keys[key]}
        return {"valid": False}


@router.get("/list")
async def list_api_keys(request: Request):
    """List all API keys — VULN: no auth, exposes all keys."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("api_keys.list"):
        with security_span("sensitive_data", severity="high",
                         source_ip=client_ip,
                         payload="api key listing"):
            log_security_event("sensitive_data", "high",
                "API key listing accessed without authorization",
                source_ip=client_ip)

        # VULN: Exposes all keys in plaintext
        return {"keys": [
            {"key": k, **v} for k, v in _api_keys.items()
        ]}
