"""Helpers for trace/log correlation and request/runtime enrichment."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import resource
import socket
import struct
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


def compute_oracle_sql_id(sql_text: str) -> str:
    """Compute Oracle SQL_ID from SQL text using the same algorithm as the DB engine.

    Produces the same 13-character identifier visible in V$SQL.SQL_ID and AWR reports.
    """
    md5 = hashlib.md5((sql_text + "\0").encode("utf-8")).digest()
    hi, lo = struct.unpack(">II", md5[8:16])
    sqln = (hi << 32) | lo
    alphabet = "0123456789abcdfghjkmnpqrstuvwxyz"
    chars = []
    for _ in range(13):
        chars.append(alphabet[sqln & 0x1F])
        sqln >>= 5
    return "".join(reversed(chars))


def sql_attributes(statement: str, *, connection_name: str = "", database_target: str = "") -> dict[str, object]:
    """Return normalized SQL metadata for span enrichment.

    Emits OCI APM Trace Explorer attributes (DbStatement, DbOracleSqlId) so the
    SQL drilldown works for both octo-drone-shop and octo-drone-shop-oke deployments
    against Autonomous Database.
    """
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

    is_oracle = database_target != "postgresql"
    db_system = "oracle" if is_oracle else "postgresql"

    attrs: dict[str, object] = {
        "db.system": db_system,
        "db.operation": operation,
        "db.statement.preview": normalized[:240],
        "db.statement.length": len(normalized),
        "db.sql.table_names": unique_tables,
        # OCI APM Trace Explorer SQL drilldown attributes
        "DbStatement": normalized,
        # OCI APM topology: component identifies the technology in the span list
        "component": db_system,
    }

    # Oracle ATP — compute SQL_ID for cross-referencing with AWR/SQL Monitor/V$SQL
    if is_oracle and normalized:
        attrs["DbOracleSqlId"] = compute_oracle_sql_id(normalized)

    if connection_name:
        attrs["db.connection_name"] = connection_name
        # Extract service name from TNS DSN for APM database identification
        if is_oracle:
            service_name = _extract_oracle_service_name(connection_name)
            attrs["db.name"] = service_name
            # peer.service makes the DB appear as a separate node in APM topology
            attrs["peer.service"] = f"OracleATP:{service_name}"
        else:
            attrs["peer.service"] = f"PostgreSQL:{connection_name}"
    if database_target:
        attrs["db.target"] = database_target
    return attrs


def _extract_oracle_service_name(dsn: str) -> str:
    """Extract the service name from an Oracle DSN/TNS connect string."""
    match = re.search(r"service_name\s*=\s*([^\s)]+)", dsn, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: tnsnames-style alias (e.g., "octodroneshop_tp")
    if dsn and "(" not in dsn:
        return dsn.split("/")[0].strip()
    return dsn[:64] if dsn else ""
