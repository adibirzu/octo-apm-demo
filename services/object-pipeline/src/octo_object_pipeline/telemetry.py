"""OpenTelemetry setup for object-pipeline API and commands."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

logger = logging.getLogger(__name__)
_initialized = False
_clients_instrumented = False


def _parse_kv(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for chunk in (raw or "").split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _otlp_trace_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith("/v1/traces") or endpoint.endswith("/private/v1/traces"):
        return endpoint
    if "/20200101" in endpoint:
        return f"{endpoint.split('/20200101', 1)[0]}/20200101/opentelemetry/private/v1/traces"
    return f"{endpoint}/v1/traces"


def _exporter_config() -> tuple[str, dict[str, str]]:
    endpoint = (
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OCI_APM_ENDPOINT")
        or ""
    )
    headers = _parse_kv(
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS")
        or os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
        or ""
    )
    private_key = os.getenv("OCI_APM_PRIVATE_DATAKEY", "")
    if private_key and "Authorization" not in headers:
        headers["Authorization"] = f"dataKey {private_key}"
    return _otlp_trace_endpoint(endpoint), headers


def init_otel(
    *,
    service_name: str = "octo-object-pipeline",
    service_version: str = "1.0.0",
    resource_attributes: dict[str, Any] | None = None,
) -> trace.Tracer:
    global _initialized
    if _initialized:
        return trace.get_tracer(service_name, service_version)

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        logger.debug("OpenTelemetry SDK unavailable", exc_info=True)
        return trace.get_tracer(service_name, service_version)

    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider):
        _instrument_clients()
        _initialized = True
        return trace.get_tracer(service_name, service_version)

    attrs = {
        "service.name": service_name,
        "service.version": service_version,
        "service.namespace": "octo",
        "service.instance.id": (
            os.getenv("SERVICE_INSTANCE_ID")
            or os.getenv("POD_NAME")
            or os.getenv("HOSTNAME")
            or "unknown"
        ),
        "deployment.environment": os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")),
        "cloud.provider": "oci",
        "oci.demo.stack": os.getenv("DEMO_STACK_NAME", "octo-apm-demo"),
    }
    attrs.update(_parse_kv(os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")))
    attrs.update(resource_attributes or {})

    provider = TracerProvider(resource=Resource.create(attrs))
    endpoint, headers = _exporter_config()
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )
        logger.info("OTel trace exporter configured for %s", service_name)
    else:
        logger.info("OTel trace exporter disabled for %s", service_name)

    trace.set_tracer_provider(provider)
    _instrument_clients()
    _initialized = True
    return trace.get_tracer(service_name, service_version)


def _instrument_clients() -> None:
    global _clients_instrumented
    if _clients_instrumented:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.debug("HTTPX instrumentation unavailable", exc_info=True)
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception:
        logger.debug("logging instrumentation unavailable", exc_info=True)
    _clients_instrumented = True


def instrument_fastapi_app(app, *, service_name: str, service_version: str = "1.0.0") -> None:
    if getattr(app.state, "_octo_otel_instrumented", False):
        return
    init_otel(service_name=service_name, service_version=service_version)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        def _request_hook(span, scope):
            if span and span.is_recording() and scope.get("type") == "http":
                span.set_attribute("component", service_name)
                span.set_attribute("service.namespace", "octo")

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=os.getenv("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS", r"/health$,/metrics$"),
            server_request_hook=_request_hook,
            exclude_spans=["receive", "send"],
        )
        app.state._octo_otel_instrumented = True
    except Exception:
        logger.debug("FastAPI instrumentation unavailable", exc_info=True)


@contextmanager
def script_span(name: str, *, service_name: str = "octo-object-pipeline", attributes: dict[str, Any] | None = None):
    tracer = init_otel(service_name=service_name)
    with tracer.start_as_current_span(f"script.{name}") as span:
        for key, value in (attributes or {}).items():
            if value not in ("", None):
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_attribute("otel.status_code", "ERROR")
            raise
        finally:
            provider = trace.get_tracer_provider()
            force_flush = getattr(provider, "force_flush", None)
            if callable(force_flush):
                force_flush(timeout_millis=5000)
