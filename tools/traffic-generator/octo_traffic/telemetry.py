"""OTel plumbing — one place to configure the OTLP/HTTP exporter so the
traffic generator shows up as ``service.name=octo-traffic-generator`` in
OCI APM alongside the shop + CRM services.

When ``otel_exporter_otlp_endpoint`` is empty, tracing is no-op — the
tracer returns NonRecordingSpan objects so the generator can still run
in air-gapped dev environments without hanging on export attempts.
"""

from __future__ import annotations

import os
from typing import Iterable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import TrafficConfig


def _parse_kv(raw: str) -> dict[str, str]:
    """Parse OTel's comma-separated key=value strings."""
    out: dict[str, str] = {}
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _otlp_trace_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith("/v1/traces") or endpoint.endswith("/private/v1/traces"):
        return endpoint
    if "/20200101" in endpoint:
        return f"{endpoint.split('/20200101', 1)[0]}/20200101/opentelemetry/private/v1/traces"
    return f"{endpoint}/v1/traces"


def init_tracing(cfg: TrafficConfig) -> trace.Tracer:
    """Install a global TracerProvider. Safe to call multiple times —
    subsequent calls return the existing provider's tracer."""
    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider):
        return trace.get_tracer(cfg.otel_service_name)

    resource_attrs = _parse_kv(cfg.otel_resource_attributes)
    resource_attrs["service.name"] = cfg.otel_service_name
    resource = Resource.create(resource_attrs)

    provider = TracerProvider(resource=resource)

    endpoint = _otlp_trace_endpoint(
        cfg.otel_exporter_otlp_endpoint
        or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        or os.getenv("OCI_APM_ENDPOINT", "")
    )
    headers = _parse_kv(
        cfg.otel_exporter_otlp_headers
        or os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "")
        or os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    )
    private_key = os.getenv("OCI_APM_PRIVATE_DATAKEY", "")
    if private_key and "Authorization" not in headers:
        headers["Authorization"] = f"dataKey {private_key}"

    if endpoint:
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=headers,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    return trace.get_tracer(cfg.otel_service_name)


def shutdown() -> None:
    """Flush + shut down the tracer provider (call from main() on exit)."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
