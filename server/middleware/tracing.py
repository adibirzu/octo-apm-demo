"""Request tracing middleware — enrich request spans with page/runtime context."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from opentelemetry.trace import Status, StatusCode

from server.config import cfg
from server.observability.correlation import (
    apply_span_attributes,
    build_correlation_id,
    current_trace_context,
    infer_page_identity,
    runtime_snapshot,
)
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tracer = get_tracer(cfg.otel_service_name)
        client_ip = request.client.host if request.client else "unknown"
        page_name, module_name = infer_page_identity(request.url.path)
        request.state.correlation_id = build_correlation_id(request.headers.get("x-correlation-id", ""))

        with tracer.start_as_current_span("middleware.entry") as span:
            start = time.monotonic()
            apply_span_attributes(
                span,
                {
                    "http.method": request.method,
                    "http.url.path": request.url.path,
                    "url.full": str(request.url),
                    "url.scheme": request.url.scheme,
                    "http.route_group": module_name,
                    "http.user_agent": request.headers.get("user-agent", ""),
                    "http.referer": request.headers.get("referer", ""),
                    "http.client_ip": client_ip,
                    "network.protocol.version": request.scope.get("http_version", ""),
                    "request.content_type": request.headers.get("content-type", ""),
                    "request.content_length": request.headers.get("content-length", ""),
                    "correlation.id": request.state.correlation_id,
                    "app.page.name": getattr(request.state, "page_name", page_name),
                    "app.module": getattr(request.state, "module_name", module_name),
                    "db.target": cfg.database_target_label,
                    "db.connection_name": cfg.oracle_dsn,
                    **runtime_snapshot(),
                },
            )

            try:
                response = await call_next(request)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                push_log(
                    "ERROR",
                    "Unhandled request exception",
                    **{
                        "http.url.path": request.url.path,
                        "http.method": request.method,
                        "http.client_ip": client_ip,
                        "error.message": str(exc),
                        "correlation.id": request.state.correlation_id,
                        "app.page.name": getattr(request.state, "page_name", page_name),
                        "app.module": getattr(request.state, "module_name", module_name),
                    },
                )
                raise

            duration_ms = (time.monotonic() - start) * 1000
            trace_ctx = current_trace_context()

            apply_span_attributes(
                span,
                {
                    "http.status_code": response.status_code,
                    "http.duration_ms": round(duration_ms, 2),
                    "http.response_time_ms": round(duration_ms, 2),
                    "app.page.name": getattr(request.state, "page_name", page_name),
                    "app.module": getattr(request.state, "module_name", module_name),
                    "app.template": getattr(request.state, "template_name", ""),
                    "trace_id": trace_ctx["trace_id"],
                },
            )
            response.headers["X-Correlation-Id"] = request.state.correlation_id
            if trace_ctx["trace_id"]:
                response.headers["X-Trace-Id"] = trace_ctx["trace_id"]
            if trace_ctx["span_id"]:
                response.headers["X-Span-Id"] = trace_ctx["span_id"]

            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))

            log_level = "WARNING" if duration_ms >= 2000 else "INFO"
            push_log(
                log_level,
                "Request completed",
                **{
                    "http.url.path": request.url.path,
                    "http.method": request.method,
                    "http.status_code": response.status_code,
                    "http.response_time_ms": round(duration_ms, 2),
                    "http.client_ip": client_ip,
                    "correlation.id": request.state.correlation_id,
                    "app.page.name": getattr(request.state, "page_name", page_name),
                    "app.module": getattr(request.state, "module_name", module_name),
                    "performance.slow_request": duration_ms >= 2000,
                },
            )

        return response
