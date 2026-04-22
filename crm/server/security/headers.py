"""Security headers middleware.

Applies HSTS, CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy.
Idempotent — will not overwrite a header already set upstream.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_DEFAULT_CSP_PARTS = (
    "default-src 'self'",
    "img-src 'self' data: https:",
    "connect-src 'self' https:",
    "style-src 'self' 'unsafe-inline'",  # Jinja templates currently rely on inline styles
    "script-src 'self' 'nonce-{nonce}' https://static.oracle.com",
    "script-src-attr 'unsafe-inline'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
)


def _build_csp(nonce: str, report_uri: str | None) -> str:
    parts = [p.format(nonce=nonce) for p in _DEFAULT_CSP_PARTS]
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
