"""HTTP metrics middleware — records RED metrics for every request."""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from server.observability.metrics import http_metrics
from server.observability.oci_monitoring import increment_requests, increment_errors


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        route = request.url.path
        method = request.method
        http_metrics.request_started(route, method)
        increment_requests()
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            http_metrics.request_finished(route, method)
            increment_errors()
            raise
        duration_ms = (time.monotonic() - start) * 1000
        http_metrics.record_request(route, method, response.status_code, duration_ms)
        http_metrics.request_finished(route, method)
        if response.status_code >= 500:
            increment_errors()
        return response
