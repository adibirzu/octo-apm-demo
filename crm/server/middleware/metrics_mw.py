"""Metrics middleware — records HTTP RED metrics for every request.

Placed in the middleware stack to capture route, method, status, and duration
for all requests including error responses.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.observability.metrics import http_metrics


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records HTTP request count, duration histogram, and in-flight gauge."""

    async def dispatch(self, request: Request, call_next) -> Response:
        route = request.url.path
        method = request.method

        http_metrics.request_started(route, method)
        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code

            # Use the matched route template if available (avoids cardinality explosion)
            route_obj = request.scope.get("route")
            if route_obj and getattr(route_obj, "path", None):
                route = route_obj.path

            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            http_metrics.request_finished(route, method)
            http_metrics.record_request(route, method, status_code, duration_ms)
