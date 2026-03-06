"""Request tracing middleware — adds span attributes to every request."""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from opentelemetry import trace
from server.observability.otel_setup import get_tracer


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tracer = get_tracer("mushop")
        with tracer.start_as_current_span("middleware.entry") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url.path", request.url.path)
            span.set_attribute("http.client_ip",
                               request.client.host if request.client else "unknown")
            span.set_attribute("service.name", "mushop-cloudnative")

            start = time.monotonic()
            response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000

            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.duration_ms", round(duration_ms, 2))
            if response.status_code >= 500:
                span.set_status(trace.StatusCode.ERROR)

        return response
