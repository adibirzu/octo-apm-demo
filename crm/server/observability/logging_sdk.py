"""Structured logging with OCI Logging SDK + Splunk HEC integration.

External pushes (OCI Logging, Splunk HEC) are dispatched to a background
thread via a queue so they never block the async event loop.
"""

import json
import logging
import queue
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from server.config import cfg
from server.observability.correlation import current_trace_context, service_metadata

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

    # Write to structured logger (stdout) — fast, stays synchronous
    record = logging.LogRecord(
        name="security.events", level=getattr(logging, level.upper(), logging.INFO),
        pathname="", lineno=0, msg=message, args=(), exc_info=None,
    )
    record.extra_fields = kwargs
    _security_logger.handle(record)

    # Enqueue external pushes (OCI Logging + Splunk HEC) for background thread
    _log_queue.put((level, message, dict(kwargs)))


def _push_to_oci_logging(level: str, message: str, extra: dict):
    client = _get_oci_logging_client()
    if client is None:
        return
    try:
        import oci
        from oci.loggingingestion.models import PutLogsDetails, LogEntryBatch, LogEntry
        entry = LogEntry(
            data=json.dumps({"message": message, **extra}, default=str),
            id=f"crm-{int(time.time() * 1000)}",
            time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )
        batch = LogEntryBatch(
            defaultloglevel=level.upper(),
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
