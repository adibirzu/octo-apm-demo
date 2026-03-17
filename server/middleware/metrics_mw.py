"""HTTP metrics middleware — records RED metrics for every request."""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from server.observability.metrics import http_metrics


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        route = request.url.path
        method = request.method
        http_metrics.request_started(route, method)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            http_metrics.request_finished(route, method)
            raise
        duration_ms = (time.monotonic() - start) * 1000
        http_metrics.record_request(route, method, response.status_code, duration_ms)
        http_metrics.request_finished(route, method)
        return response
