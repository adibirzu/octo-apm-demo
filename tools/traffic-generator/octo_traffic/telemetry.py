"""OTel plumbing — one place to configure the OTLP/HTTP exporter so the
traffic generator shows up as ``service.name=octo-traffic-generator`` in
OCI APM alongside the shop + CRM services.

When ``otel_exporter_otlp_endpoint`` is empty, tracing is no-op — the
tracer returns NonRecordingSpan objects so the generator can still run
in air-gapped dev environments without hanging on export attempts.
"""

from __future__ import annotations

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

    if cfg.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=cfg.otel_exporter_otlp_endpoint,
            headers=_parse_kv(cfg.otel_exporter_otlp_headers),
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
