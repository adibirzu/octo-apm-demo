"""Request ID middleware.

Generates an `X-Request-Id` (ULID-style via `uuid4().hex`) if one is absent.
The value is stored on `request.state.request_id`, echoed on the response,
and made available to downstream logging/tracing via a contextvar so that
WAF events and app logs can be joined by the same identifier.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-Id"


def current_request_id() -> str | None:
    """Return the current request's id, if any."""
    return _request_id_ctx.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request carries an `X-Request-Id` header."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming.strip() if incoming else uuid4().hex
        # Bound length — ignore absurd client values.
        if len(request_id) > 128:
            request_id = uuid4().hex
        request.state.request_id = request_id
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        return response
