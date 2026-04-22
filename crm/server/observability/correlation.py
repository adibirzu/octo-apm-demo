"""Helpers for trace/log correlation, topology enrichment, and shared service metadata."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from opentelemetry import trace

from server.config import cfg


def current_trace_context() -> dict[str, str]:
    """Return the active trace/span context in OCI-friendly formats."""
    span = trace.get_current_span()
    if not span:
        return {"trace_id": "", "span_id": "", "traceparent": ""}

    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return {"trace_id": "", "span_id": "", "traceparent": ""}

    trace_id = format(ctx.trace_id, "032x")
    span_id = format(ctx.span_id, "016x")
    trace_flags = format(int(ctx.trace_flags), "02x")
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "traceparent": f"00-{trace_id}-{span_id}-{trace_flags}",
    }


def service_metadata() -> dict[str, str]:
    """Return stable service metadata shared across traces and logs."""
    return {
        "service.name": cfg.otel_service_name,
        "service.namespace": cfg.service_namespace,
        "service.version": cfg.app_version,
        "service.instance.id": cfg.service_instance_id,
        "deployment.environment": cfg.app_env,
        "app.name": cfg.app_name,
        "app.brand": cfg.brand_name,
        "app.runtime": cfg.app_runtime,
        "oci.demo.stack": cfg.demo_stack_name,
    }


def build_correlation_id(seed: str = "") -> str:
    """Prefer the active trace ID, then a caller seed, then a generated UUID."""
    trace_ctx = current_trace_context()
    return trace_ctx["trace_id"] or seed or uuid.uuid4().hex


def outbound_headers(correlation_id: str = "") -> dict[str, str]:
    """Headers added to downstream requests to aid troubleshooting."""
    trace_ctx = current_trace_context()
    resolved_correlation_id = build_correlation_id(correlation_id)
    headers = {
        "X-Correlation-Id": resolved_correlation_id,
        "X-Service-Name": cfg.otel_service_name,
        "X-Service-Namespace": cfg.service_namespace,
        "X-Service-Version": cfg.app_version,
        "X-OCTO-Stack": cfg.demo_stack_name,
    }
    if cfg.atp_connection_name:
        headers["X-Database-Connection"] = cfg.atp_connection_name
    if trace_ctx["traceparent"]:
        headers["traceparent"] = trace_ctx["traceparent"]
    return headers


def set_peer_service(span: trace.Span, target_service: str, target_url: str = ""):
    """Set peer.service and related attributes on a span for APM topology rendering.

    OCI APM uses peer.service to draw edges between services in the topology view.
    Without this, outbound calls appear as internal spans with no topology edges.
    """
    if not span or not span.is_recording():
        return
    span.set_attribute("peer.service", target_service)
    span.set_attribute("component", "http")
    if target_url:
        parsed = urlparse(target_url)
        span.set_attribute("server.address", parsed.hostname or parsed.netloc or target_url)
    span.set_attribute("http.request.source_service", cfg.otel_service_name)
