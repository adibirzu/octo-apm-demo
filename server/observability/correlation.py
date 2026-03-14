"""Helpers for trace/log correlation and request/runtime enrichment."""

from __future__ import annotations

import os
import platform
import re
import resource
import socket
import uuid

from opentelemetry import trace

from server.config import cfg

_PAGE_RULES: tuple[tuple[str, str, str], ...] = (
    ("/", "dashboard", "dashboard"),
    ("/shop", "shop", "shop"),
    ("/services", "services", "services"),
    ("/catalogue", "catalogue", "catalogue"),
    ("/orders", "orders", "orders"),
    ("/shipping", "shipping", "shipping"),
    ("/campaigns", "campaigns", "campaigns"),
    ("/analytics", "analytics", "analytics"),
    ("/admin", "admin", "admin"),
    ("/login", "login", "auth"),
    ("/api/products", "catalogue", "catalogue"),
    ("/api/orders", "orders", "orders"),
    ("/api/shipping", "shipping", "shipping"),
    ("/api/campaigns", "campaigns", "campaigns"),
    ("/api/analytics", "analytics", "analytics"),
    ("/api/admin", "admin", "admin"),
    ("/api/shop", "shop", "shop"),
    ("/api/services", "services", "services"),
    ("/api/auth", "login", "auth"),
    ("/ready", "readiness", "health"),
    ("/health", "health", "health"),
)


def current_trace_context() -> dict[str, str]:
    """Return active trace/span identifiers in OCI-friendly formats."""
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
    """Return stable service metadata shared across spans and logs."""
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
    trace_ctx = current_trace_context()
    return trace_ctx["trace_id"] or seed or uuid.uuid4().hex


def infer_page_identity(path: str) -> tuple[str, str]:
    """Best-effort mapping from path to page + module names."""
    normalized = path or "/"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    for prefix, page_name, module_name in _PAGE_RULES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return page_name, module_name
    return "unknown", "unknown"


def runtime_snapshot() -> dict[str, str | int | float]:
    """Cheap process/runtime details safe to emit on every request."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "host.name": socket.gethostname(),
        "process.pid": os.getpid(),
        "process.runtime.name": "python",
        "process.runtime.version": platform.python_version(),
        "process.max_rss_kb": int(getattr(usage, "ru_maxrss", 0) or 0),
        "process.cpu.user_seconds": round(float(getattr(usage, "ru_utime", 0.0) or 0.0), 4),
        "process.cpu.system_seconds": round(float(getattr(usage, "ru_stime", 0.0) or 0.0), 4),
    }


def apply_span_attributes(span, attributes: dict[str, object]) -> None:
    """Set non-empty attributes without raising on bad values."""
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        span.set_attribute(key, value)


def sql_attributes(statement: str, *, connection_name: str = "", database_target: str = "") -> dict[str, object]:
    """Return normalized SQL metadata for span enrichment."""
    normalized = re.sub(r"\s+", " ", (statement or "").strip())
    operation = normalized.split(" ", 1)[0].upper() if normalized else "UNKNOWN"
    tables = []
    for pattern in (
        r"\bFROM\s+([A-Z0-9_$.]+)",
        r"\bJOIN\s+([A-Z0-9_$.]+)",
        r"\bUPDATE\s+([A-Z0-9_$.]+)",
        r"\bINTO\s+([A-Z0-9_$.]+)",
    ):
        tables.extend(re.findall(pattern, normalized.upper()))
    unique_tables = ",".join(dict.fromkeys(tables).keys())
    attrs: dict[str, object] = {
        "db.system": "oracle",
        "db.operation": operation,
        "db.statement.preview": normalized[:240],
        "db.statement.length": len(normalized),
        "db.sql.table_names": unique_tables,
    }
    if connection_name:
        attrs["db.connection_name"] = connection_name
    if database_target:
        attrs["db.target"] = database_target
    return attrs
