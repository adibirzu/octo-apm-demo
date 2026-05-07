"""Structured logging with OCI Logging SDK + Splunk HEC integration.

External pushes (OCI Logging, Splunk HEC) are dispatched to a background
thread via a queue so they never block the async event loop.
"""

import json
import logging
import queue
import re
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

import httpx
from opentelemetry import trace

from server.config import cfg
from server.observability.correlation import current_trace_context, service_metadata

logger = logging.getLogger(__name__)
_REQUEST_SPAN = ContextVar("octo_request_span", default=None)

# PII masking keeps Log Analytics useful without storing raw customer contact
# details in OCI Logging or external HEC destinations.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_PII_KEYS = frozenset({
    "customer_email",
    "email",
    "customer.email",
    "security.username",
    "customer_phone",
    "phone",
    "customer.phone",
})

_SPAN_EVENT_KEYS = (
    "trace_id",
    "span_id",
    "oracleApmTraceId",
    "oracleApmSpanId",
    "service.name",
    "app.service",
    "app.name",
    "app.module",
    "app.page.name",
    "http.method",
    "http.url.path",
    "http.status_code",
    "http.response_time_ms",
    "correlation.id",
    "workflow_id",
    "workflow_step",
    "workflow.id",
    "workflow.step",
    "request_id",
    "run_id",
    "upstream.trace_id",
    "db.target",
    "db.connection_name",
    "oci.api_gateway.name",
    "oci.api_gateway.deployment_id",
    "oci.api_gateway.scope",
    "oci.api_gateway.route",
    "oci.api_gateway.route_id",
    "oci.api_gateway.route_family",
    "oci.api_gateway.request_id",
    "oci.api_gateway.action",
    "oci.api_gateway.policy.decision",
    "oci.api_gateway.latency_ms",
    "oci.api_gateway.rate_limit.limit",
    "oci.api_gateway.rate_limit.remaining",
    "oci.api_gateway.threat_signal",
    "mitre.technique_id",
    "mitre.tactic",
    "client.address",
    "source.ip",
    "server.address",
    "destination.ip",
    "destination.port",
    "host.name",
    "cloud.instance.id",
    "security.attack.detected",
    "security.attack.id",
    "security.attack.stage",
    "security.attack.type",
    "security.attack.severity",
    "security.severity",
)


def _mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _mask_pii(data: dict) -> dict:
    """Return a new dict with known PII fields masked."""
    masked = {}
    for key, value in data.items():
        if not isinstance(value, str):
            masked[key] = value
            continue
        if key in _PII_KEYS:
            if "@" in value:
                masked[key] = _mask_email(value)
            elif _PHONE_RE.search(value):
                masked[key] = _mask_phone(value)
            else:
                masked[key] = "***"
        elif _EMAIL_RE.search(value):
            masked[key] = _EMAIL_RE.sub(lambda match: _mask_email(match.group(0)), value)
        else:
            masked[key] = value
    return masked


def _span_event_value(value):
    if isinstance(value, (bool, int, float, str)):
        return value[:512] if isinstance(value, str) else value
    if value is None:
        return ""
    return json.dumps(value, default=str)[:512]


def bind_request_span(span):
    """Bind the request/server span so app logs also show on root span details."""
    return _REQUEST_SPAN.set(span)


def reset_request_span(token) -> None:
    _REQUEST_SPAN.reset(token)


def _event_attrs(level: str, message: str, payload: dict) -> dict:
    attrs = {
        "log.severity": level.upper(),
        "log.message": message[:512],
        "log.logger": "security.events",
    }
    for key in _SPAN_EVENT_KEYS:
        if key in payload:
            attrs[key] = _span_event_value(payload[key])
    return attrs


def _record_span_log_event(span, attrs: dict) -> None:
    if span and span.is_recording():
        span.add_event("app.log", attrs)


def _add_current_span_log_event(level: str, message: str, payload: dict) -> None:
    """Attach a compact app log event to active and request-root spans."""
    try:
        attrs = _event_attrs(level, message, payload)
        span = trace.get_current_span()
        _record_span_log_event(span, attrs)
        request_span = _REQUEST_SPAN.get()
        if request_span is not None and request_span is not span:
            _record_span_log_event(request_span, attrs)
    except Exception:
        return

# ── Background log dispatch queue ────────────────────────────────
_log_queue: queue.SimpleQueue[tuple[str, str, dict] | None] = queue.SimpleQueue()


def _log_worker() -> None:
    """Drain the queue and push to OCI / Splunk in a background thread."""
    while True:
        item = _log_queue.get()
        if item is None:  # poison pill → shut down
            break
        level, message, extra = item
        _push_to_oci_logging(level, message, extra)
        _push_to_splunk(level, message, extra)


_worker_thread = threading.Thread(target=_log_worker, daemon=True, name="log-push-worker")
_worker_thread.start()

_security_logger = logging.getLogger("security.events")
_security_logger.setLevel(logging.INFO)
_security_logger.propagate = False

# JSON formatter for structured log output
class _JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        log_entry.update(service_metadata())
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        trace_ctx = current_trace_context()
        if trace_ctx["trace_id"]:
            log_entry["trace_id"] = trace_ctx["trace_id"]
            log_entry["span_id"] = trace_ctx["span_id"]
            log_entry["traceparent"] = trace_ctx["traceparent"]
            log_entry["oracleApmTraceId"] = trace_ctx["trace_id"]
            log_entry["oracleApmSpanId"] = trace_ctx["span_id"]
        return json.dumps(log_entry, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JSONFormatter())
_security_logger.addHandler(_handler)

# OCI Logging SDK client (lazy init)
_oci_logging_client = None


def _get_oci_logging_client():
    global _oci_logging_client
    if _oci_logging_client is not None:
        return _oci_logging_client
    if not cfg.logging_configured:
        return None
    try:
        import oci
        auth_mode = cfg.oci_auth_mode
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            _oci_logging_client = oci.loggingingestion.LoggingClient(config={}, signer=signer)
        else:
            # Try resource principal first (OKE workload identity), fall back to config
            try:
                signer = oci.auth.signers.get_resource_principals_signer()
                _oci_logging_client = oci.loggingingestion.LoggingClient(config={}, signer=signer)
            except Exception:
                config = oci.config.from_file()
                _oci_logging_client = oci.loggingingestion.LoggingClient(config)
        return _oci_logging_client
    except Exception:
        return None


def push_log(level: str, message: str, **kwargs):
    """Push a structured log to OCI Logging and optionally Splunk."""
    trace_ctx = current_trace_context()
    if trace_ctx["trace_id"]:
        kwargs["trace_id"] = trace_ctx["trace_id"]
        kwargs["span_id"] = trace_ctx["span_id"]
        kwargs["traceparent"] = trace_ctx["traceparent"]
        kwargs["oracleApmTraceId"] = trace_ctx["trace_id"]
        kwargs["oracleApmSpanId"] = trace_ctx["span_id"]

    kwargs.update(service_metadata())
    kwargs["app.service"] = cfg.otel_service_name
    kwargs["db.target"] = cfg.database_target_label
    if cfg.atp_ocid:
        kwargs["db.ocid"] = cfg.atp_ocid
    if cfg.atp_connection_name:
        kwargs["db.connection_name"] = cfg.atp_connection_name

    safe_kwargs = _mask_pii(kwargs)
    _add_current_span_log_event(level, message, safe_kwargs)

    # Write to structured logger (stdout) — fast, stays synchronous
    record = logging.LogRecord(
        name="security.events", level=getattr(logging, level.upper(), logging.INFO),
        pathname="", lineno=0, msg=message, args=(), exc_info=None,
    )
    record.extra_fields = safe_kwargs
    _security_logger.handle(record)

    # Enqueue external pushes (OCI Logging + Splunk HEC) for background thread
    _log_queue.put((level, message, dict(safe_kwargs)))


def _push_to_oci_logging(level: str, message: str, extra: dict):
    client = _get_oci_logging_client()
    if client is None:
        return
    try:
        import oci
        from oci.loggingingestion.models import PutLogsDetails, LogEntryBatch, LogEntry
        event_time = datetime.now(timezone.utc)
        entry = LogEntry(
            data=json.dumps(
                {
                    "timestamp": event_time.isoformat(),
                    "level": level.upper(),
                    "message": message,
                    **extra,
                },
                default=str,
            ),
            id=f"crm-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            time=event_time,
        )
        batch = LogEntryBatch(
            source=cfg.otel_service_name,
            type=cfg.app_name,
            subject=cfg.brand_name,
            entries=[entry],
        )
        client.put_logs(
            log_id=cfg.oci_log_id,
            put_logs_details=PutLogsDetails(
                specversion="1.0",
                log_entry_batches=[batch],
            ),
        )
    except Exception as exc:
        # Never break the request, but log once per minute so operators know
        # ingestion is broken (see KB-456 for the parallel Monitoring issue).
        global _last_logging_error_ts
        now = time.time()
        if now - _last_logging_error_ts > 60.0:
            _last_logging_error_ts = now
            logger.warning("OCI Logging put_logs failed: %s", exc)


_last_logging_error_ts: float = 0.0


def _push_to_splunk(level: str, message: str, extra: dict):
    if not cfg.splunk_hec_url or not cfg.splunk_hec_token:
        return
    try:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "message": message,
            **extra,
        }
        httpx.post(
            cfg.splunk_hec_url,
            json={"event": event, "sourcetype": "oci:crm:security"},
            headers={"Authorization": f"Splunk {cfg.splunk_hec_token}"},
            timeout=2.0,
        )
    except Exception:
        pass  # fire-and-forget


def log_security_event(
    vuln_type: str,
    severity: str,
    message: str,
    source_ip: str = "",
    username: str = "",
    payload: str = "",
    **extra,
):
    """Log a security event with standard attributes."""
    push_log(
        "WARNING" if severity in ("low", "medium") else "ERROR",
        message,
        **{
            "security.attack.detected": True,
            "security.attack.type": vuln_type,
            "security.attack.severity": severity,
            "security.source_ip": source_ip,
            "security.username": username,
            "security.attack.payload": payload[:512] if payload else "",
            **extra,
        },
    )
