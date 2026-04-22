"""Security headers middleware.

Applies HSTS, CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy.
Idempotent — will not overwrite a header already set upstream.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

def _origin_from_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _parse_source_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(",", " ").split() if item.strip()]


def _unique_sources(*groups: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
    return ordered


def _script_src_sources() -> list[str]:
    rum_origin = _origin_from_url(os.getenv("OCI_APM_RUM_ENDPOINT", ""))
    extra = _parse_source_list(os.getenv("CSP_SCRIPT_SRC_EXTRA", ""))
    return _unique_sources(["https://static.oracle.com"], [rum_origin] if rum_origin else [], extra)


def _build_csp(nonce: str, report_uri: str | None) -> str:
    script_sources = " ".join(["'self'", f"'nonce-{nonce}'", *_script_src_sources()])
    parts = [
        "default-src 'self'",
        "img-src 'self' data: https:",
        "connect-src 'self' https:",
        "style-src 'self' 'unsafe-inline'",
        f"script-src {script_sources}",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
    if report_uri:
        parts.append(f"report-uri {report_uri}")
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline security response headers on every response."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        csp_report_uri: str | None = None,
        allow_framing_from: str | None = None,
    ) -> None:
        super().__init__(app)
        self._csp_report_uri = csp_report_uri or os.getenv("CSP_REPORT_URI") or None
        self._allow_framing_from = allow_framing_from

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)

        headers = response.headers
        headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if self._allow_framing_from:
            headers.setdefault(
                "Content-Security-Policy-Frame-Ancestors",
                f"frame-ancestors 'self' {self._allow_framing_from}",
            )
            headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        else:
            headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Content-Security-Policy", _build_csp(nonce, self._csp_report_uri))
        return response
