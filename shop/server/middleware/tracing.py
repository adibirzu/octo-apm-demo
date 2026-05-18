"""Request tracing middleware — enrich request spans with page/runtime context."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from server.config import cfg
from server.observability.correlation import (
    apply_span_attributes,
    build_correlation_id,
    current_trace_context,
    infer_page_identity,
    runtime_snapshot,
)
from server.observability.logging_sdk import bind_request_span, push_log, reset_request_span
from server.observability.otel_setup import get_tracer
from server.observability.db_session_tagging import set_db_context
from server.observability.purchase_journey import purchase_context_from_request, purchase_span_attributes
from server.observability.workflow_context import resolve_workflow


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tracer = get_tracer(cfg.otel_service_name)
        request_span_token = bind_request_span(trace.get_current_span())
        client_ip = request.client.host if request.client else "unknown"
        page_name, module_name = infer_page_identity(request.url.path)
        request.state.correlation_id = build_correlation_id(request.headers.get("x-correlation-id", ""))
        workflow = getattr(request.state, "workflow", None) or resolve_workflow(request.url.path)
        workflow_fields = {
            "workflow.id": getattr(workflow, "workflow_id", ""),
            "workflow.step": getattr(workflow, "step", ""),
        }
        purchase_context = purchase_context_from_request(request)
        purchase_fields = purchase_span_attributes(purchase_context)
        request.state.purchase_context = purchase_context
        request.state.purchase_fields = purchase_fields

        try:
            with tracer.start_as_current_span("middleware.entry") as span:
                start = time.monotonic()
                apply_span_attributes(
                    span,
                    {
                        "component": "fastapi",
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
                        **workflow_fields,
                        **purchase_fields,
                        **runtime_snapshot(),
                    },
                )
                if purchase_fields:
                    span.add_event("shop.user_action", purchase_fields)

                # Tag Oracle DB sessions with request context for OPSI/DB Management correlation
                trace_ctx_for_db = current_trace_context()
                set_db_context(
                    action=(purchase_context.get("user_action") or f"{request.method} {request.url.path}")[:64],
                    client_identifier=trace_ctx_for_db["trace_id"],
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
                            **workflow_fields,
                            **purchase_fields,
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
                        **workflow_fields,
                        **purchase_fields,
                    },
                )
                response.headers["X-Correlation-Id"] = request.state.correlation_id
                if trace_ctx["trace_id"]:
                    response.headers["X-Trace-Id"] = trace_ctx["trace_id"]
                if trace_ctx["span_id"]:
                    response.headers["X-Span-Id"] = trace_ctx["span_id"]

                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                elif response.status_code >= 400:
                    span.add_event("http.client_error", {
                        "http.status_code": response.status_code,
                        "http.url.path": request.url.path,
                    })

                log_level = "WARNING" if duration_ms >= 2000 or response.status_code >= 400 else "INFO"
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
                        **workflow_fields,
                        **purchase_fields,
                    },
                )

            return response
        finally:
            reset_request_span(request_span_token)
