"""Request tracing middleware — adds custom spans for auth, validation, DB, business logic."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import log_security_event, push_log
from server.observability.correlation import build_correlation_id, current_trace_context
from server.observability.security_spans import security_span
from server.observability.db_session_tagging import set_db_context


class TracingMiddleware(BaseHTTPMiddleware):
    """Adds custom spans to every request for deep trace visibility.

    Produces at minimum 3 spans per request (middleware_entry, auth_check, response_finalize).
    Combined with FastAPI auto-instrumentation, route handler spans, DB spans, and
    security spans, each request generates 8+ spans.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        tracer = get_tracer()
        start = time.time()
        client_ip = request.client.host if request.client else "unknown"
        request_id = request.headers.get("x-correlation-id", "")

        with tracer.start_as_current_span("middleware.entry") as entry_span:
            entry_span.set_attribute("component", "fastapi")
            entry_span.set_attribute("http.client_ip", client_ip)
            entry_span.set_attribute("http.user_agent", request.headers.get("user-agent", ""))
            entry_span.set_attribute("http.url.path", request.url.path)
            entry_span.set_attribute("http.method", request.method)
            request.state.correlation_id = build_correlation_id(request_id)

            # Span 2: Auth context extraction
            with tracer.start_as_current_span("auth.check") as auth_span:
                auth_header = request.headers.get("authorization", "")
                session_cookie = request.cookies.get("session_id", "")
                auth_span.set_attribute("auth.has_token", bool(auth_header))
                auth_span.set_attribute("auth.has_session", bool(session_cookie))
                auth_span.set_attribute("auth.method",
                    "bearer" if auth_header.startswith("Bearer") else
                    "basic" if auth_header.startswith("Basic") else
                    "session" if session_cookie else "none"
                )

            # Span 3: Request validation
            with tracer.start_as_current_span("request.validate") as val_span:
                content_type = request.headers.get("content-type", "")
                content_length = request.headers.get("content-length", "0")
                val_span.set_attribute("request.content_type", content_type)
                val_span.set_attribute("request.content_length", content_length)
                waf_score = request.headers.get("x-oci-waf-score", "")
                waf_action = request.headers.get("x-oci-waf-action", "")
                if waf_score or waf_action:
                    val_span.set_attribute("security.waf.score", waf_score or "unknown")
                    val_span.set_attribute("security.waf.action", waf_action or "unknown")
                    with security_span(
                        "security_misconfig",
                        severity="medium",
                        payload=f"waf_score={waf_score}, waf_action={waf_action}",
                        source_ip=client_ip,
                    ):
                        log_security_event(
                            "security_misconfig",
                            "medium",
                            "WAF signal observed on inbound request",
                            source_ip=client_ip,
                            payload=f"waf_score={waf_score}, waf_action={waf_action}",
                            correlation_id=request.state.correlation_id,
                        )

            # Tag Oracle DB sessions with request context for OPSI/DB Management correlation
            trace_ctx_for_db = current_trace_context()
            set_db_context(
                action=f"{request.method} {request.url.path}"[:64],
                client_identifier=trace_ctx_for_db["trace_id"],
            )

            # Call the actual route handler (generates its own spans)
            try:
                response = await call_next(request)
            except Exception as exc:
                push_log("ERROR", "Unhandled request exception", **{
                    "http.url.path": request.url.path,
                    "http.method": request.method,
                    "http.client_ip": client_ip,
                    "error.message": str(exc),
                    "correlation.id": request.state.correlation_id,
                })
                raise

            # Span 4: Response finalization
            with tracer.start_as_current_span("response.finalize") as resp_span:
                duration = time.time() - start
                resp_span.set_attribute("http.status_code", response.status_code)
                resp_span.set_attribute("http.response_time_ms", round(duration * 1000, 2))
                resp_span.set_attribute("correlation.id", request.state.correlation_id)

                trace_ctx = current_trace_context()
                request.state.trace_id = trace_ctx["trace_id"]
                request.state.span_id = trace_ctx["span_id"]
                response.headers["X-Correlation-Id"] = request.state.correlation_id
                if trace_ctx["trace_id"]:
                    response.headers["X-Trace-Id"] = trace_ctx["trace_id"]
                if trace_ctx["span_id"]:
                    response.headers["X-Span-Id"] = trace_ctx["span_id"]

                # Log slow requests
                if duration > 2.0:
                    push_log("WARNING", "Slow request detected", **{
                        "http.url.path": request.url.path,
                        "http.response_time_ms": round(duration * 1000, 2),
                        "http.client_ip": client_ip,
                        "performance.slow_request": True,
                        "correlation.id": request.state.correlation_id,
                    })
                else:
                    push_log("INFO", "Request completed", **{
                        "http.url.path": request.url.path,
                        "http.method": request.method,
                        "http.status_code": response.status_code,
                        "http.response_time_ms": round(duration * 1000, 2),
                        "correlation.id": request.state.correlation_id,
                    })

            return response
