"""Structured logging with OCI Logging SDK + Splunk HEC integration.

Supports trace-log correlation for OCI Log Analytics via oracleApmTraceId.
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

from opentelemetry import trace

from server.config import cfg
from server.observability.correlation import current_trace_context, service_metadata
from server.observability.workflow_context import current_workflow
from server.security.request_id import current_request_id


_REQUEST_SPAN = ContextVar("octo_request_span", default=None)


# ── PII masking ──────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PII_KEYS = frozenset({
    "customer_email", "email", "customer.email", "security.username",
    "customer_phone", "phone", "customer.phone",
    "payment.card_number", "card_number", "card.number",
    "payment.card_cvv", "card_cvv", "card.cvv", "cvv",
})
_CARD_MASK_EXEMPT_KEYS = frozenset({
    "trace_id",
    "span_id",
    "oracleApmTraceId",
    "oracleApmSpanId",
    "traceparent",
    "request_id",
    "correlation.id",
    "workflow_id",
    "workflow_step",
    "run_id",
    "orders.order_id",
    "order_id",
    "source_order_id",
    "payment.gateway.request_id",
    "payment.network.transaction_id",
})

_SPAN_EVENT_KEYS = (
    "trace_id",
    "span_id",
    "oracleApmTraceId",
    "oracleApmSpanId",
    "service.name",
    "app.service",
    "peer.service",
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
    "shop.journey_id",
    "shop.session_id",
    "browser.trace_id",
    "enduser.action",
    "checkout.step",
    "request_id",
    "run_id",
    "upstream.trace_id",
    "db.target",
    "db.connection_name",
    "payment.provider",
    "payment.status",
    "payment.risk_score",
    "payment.gateway.name",
    "payment.gateway.provider",
    "payment.gateway.version",
    "payment.gateway.request_id",
    "payment.gateway.step",
    "payment.gateway.step_index",
    "payment.gateway.phase",
    "payment.gateway.step_status",
    "payment.gateway.step_latency_ms",
    "payment.gateway.step_count",
    "payment.gateway.request_shape",
    "payment.gateway.authorization_type",
    "payment.gateway.decryption_method",
    "payment.gateway.emulated",
    "payment.gateway.final",
    "payment.method",
    "payment.network",
    "payment.amount_minor_units",
    "payment.currency",
    "payment.wallet_type",
    "payment.wallet_token_hash",
    "payment.wallet.provider",
    "payment.wallet.type",
    "payment.wallet.tokenization_type",
    "payment.wallet.gateway",
    "payment.wallet.token_hash",
    "payment.wallet.gateway_merchant_id_hash",
    "payment.wallet.cryptogram.present",
    "payment.wallet.encrypted_payload.present",
    "payment.wallet.encrypted_payload.format",
    "payment.wallet.token_type",
    "payment.wallet.merchant_session.validated",
    "payment.token.safe",
    "payment.card_brand",
    "payment.card_last4",
    "payment.card.brand",
    "payment.card.last4",
    "payment.card.tokenized",
    "payment.card.fingerprint",
    "payment.card.avs.result",
    "payment.card.cvv.result",
    "payment.card.pan_present",
    "payment.card.cvv_present",
    "payment.card.entry_mode",
    "payment.3ds.program",
    "payment.3ds.eci",
    "payment.3ds.authentication_value.present",
    "payment.3ds.flow",
    "payment.google_pay.api_version",
    "payment.google_pay.api_version_minor",
    "payment.google_pay.payment_method_data.type",
    "payment.google_pay.card_network",
    "payment.google_pay.allowed_auth_methods",
    "payment.google_pay.tokenization_data.type",
    "payment.google_pay.signed_message.format",
    "payment.apple_pay.merchant_validation.status",
    "payment.apple_pay.validation_url",
    "payment.apple_pay.session.emulated",
    "payment.apple_pay.merchant_identifier_hash",
    "payment.apple_pay.payment_data.version",
    "payment.apple_pay.payment_method.network",
    "payment.apple_pay.payment_method.type",
    "payment.apple_pay.header.transaction_id_hash",
    "payment.apple_pay.header.ephemeral_public_key.present",
    "payment.apple_pay.header.public_key_hash.present",
    "payment.apple_pay.signature.present",
    "payment.apple_pay.data.present",
    "payment.apple_pay.payment_processing_certificate",
    "payment.verification.provider",
    "payment.verification.status",
    "payment.verification.decision",
    "payment.verification.risk_score",
    "payment.verification.error_code",
    "payment.verification.periodic_review",
    "payment.verification.latency_ms",
    "payment.antifraud.input_score",
    "payment.processor.name",
    "payment.processor.status",
    "payment.processor.decision",
    "payment.processor.error_code",
    "payment.processor.latency_ms",
    "payment.processor.response_code",
    "payment.processor.gateway_code",
    "payment.network.route",
    "payment.network.response_code",
    "payment.network.gateway_code",
    "payment.network.transaction_id",
    "payment.network.token.present",
    "payment.network.cryptogram.validated",
    "payment.acquirer.name",
    "payment.interception.detected",
    "payment.redirect.detected",
    "assistant.session_id",
    "assistant.provider",
    "assistant.model_id",
    "assistant.documents_grounded",
    "assistant.guardrail.scope",
    "assistant.guardrail.allowed",
    "assistant.guardrail.reason",
    "assistant.outcome",
    "llmetry.schema.version",
    "llmetry.latency_ms",
    "llmetry.content.captured",
    "llmetry.error_type",
    "llm.request.type",
    "llm.system",
    "llm.model",
    "llm.prompt.hash",
    "llm.prompt.length",
    "llm.response.hash",
    "llm.response.length",
    "llm.token.prompt",
    "llm.token.completion",
    "llm.token.total",
    "gen_ai.system",
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens",
    "langfuse.configured",
    "langfuse.trace.name",
    "langfuse.session.id",
    "langfuse.observation.type",
    "java_apm.path",
    "java_apm.service.name",
    "java_apm.status_code",
    "java_apm.latency_ms",
    "java_apm.error_type",
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

_LOGAN_ALIAS_FIELDS = {
    "service.name": "service_name",
    "service.namespace": "service_namespace",
    "service.instance.id": "service_instance_id",
    "deployment.environment": "deployment_environment",
    "http.method": "http_method",
    "http.url.path": "url_path",
    "http.status_code": "http_status_code",
    "http.response_time_ms": "http_response_time_ms",
    "shop.journey_id": "shop_journey_id",
    "shop.session_id": "session_id",
    "browser.trace_id": "browser_trace_id",
    "enduser.action": "enduser_action",
    "checkout.step": "checkout_step",
    "auth.user_id": "user_id",
    "security.username_hash": "user_id_hash",
    "db.target": "db_target",
    "db.connection_name": "db_connection_name",
    "orders.order_id": "order_id",
    "payment.provider": "payment_provider",
    "payment.status": "payment_status",
    "payment.method": "payment_method",
    "payment.network": "payment_network",
    "payment.risk_score": "payment_risk_score",
    "payment.amount_minor_units": "payment_amount_minor_units",
    "payment.currency": "payment_currency",
    "payment.wallet_token_hash": "payment_wallet_token_hash",
    "payment.card_brand": "payment_card_brand",
    "payment.card_last4": "payment_card_last4",
    "payment.gateway.request_id": "payment_gateway_request_id",
    "payment.gateway.name": "payment_gateway_name",
    "payment.gateway.provider": "payment_gateway_provider",
    "payment.gateway.version": "payment_gateway_version",
    "payment.gateway.step": "payment_gateway_step",
    "payment.gateway.step_index": "payment_gateway_step_index",
    "payment.gateway.phase": "payment_gateway_phase",
    "payment.gateway.step_status": "payment_gateway_step_status",
    "payment.gateway.step_latency_ms": "payment_gateway_step_latency_ms",
    "payment.gateway.step_count": "payment_gateway_step_count",
    "payment.processor.response_code": "payment_processor_response_code",
    "payment.processor.gateway_code": "payment_processor_gateway_code",
    "payment.network.transaction_id": "payment_network_transaction_id",
    "payment.card.avs.result": "payment_card_avs_result",
    "payment.card.cvv.result": "payment_card_cvv_result",
    "payment.3ds.program": "payment_3ds_program",
    "payment.3ds.eci": "payment_3ds_eci",
    "payment.3ds.flow": "payment_3ds_flow",
    "java_apm.path": "java_apm_path",
    "java_apm.service.name": "java_apm_service_name",
    "java_apm.status_code": "java_apm_status_code",
    "java_apm.latency_ms": "java_apm_latency_ms",
    "java_apm.error_type": "java_apm_error_type",
    "payment.processor.name": "payment_processor_name",
    "peer.service": "peer_service",
    "llmetry.error_type": "llmetry_error_type",
    "oci.api_gateway.threat_signal": "oci_api_gateway_threat_signal",
    "mitre.technique_id": "mitre_technique_id",
    "osquery.finding": "osquery_finding",
    "security.attack.id": "attack_id",
    "security.attack.type": "attack_type",
    "security.attack.severity": "attack_severity",
}


def _mask_email(email: str) -> str:
    """user@example.com → u***@example.com"""
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _mask_phone(phone: str) -> str:
    """+1-555-867-5309 → ***5309"""
    digits = re.sub(r"\D", "", phone)
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _mask_card_number(card_number: str) -> str:
    digits = re.sub(r"\D", "", card_number)
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def _mask_card_mentions(value: str) -> str:
    return _CARD_RE.sub(lambda match: _mask_card_number(match.group(0)), value)


def _mask_pii(data: dict) -> dict:
    """Return a new dict with PII fields masked. Does not mutate input."""
    masked = {}
    for key, value in data.items():
        if not isinstance(value, str):
            masked[key] = value
            continue
        if key in _CARD_MASK_EXEMPT_KEYS:
            masked[key] = value
            continue
        if key in _PII_KEYS:
            if "@" in value:
                masked[key] = _mask_email(value)
            elif "cvv" in key.lower():
                masked[key] = "***"
            elif key.lower() in {"payment.card_number", "card_number", "card.number"}:
                masked[key] = _mask_card_number(value)
            elif _PHONE_RE.search(value):
                masked[key] = _mask_phone(value)
            else:
                masked[key] = "***"
        elif _EMAIL_RE.search(value):
            masked[key] = _mask_card_mentions(_EMAIL_RE.sub(lambda match: _mask_email(match.group(0)), value))
        elif _CARD_RE.search(value):
            masked[key] = _mask_card_mentions(value)
        else:
            masked[key] = value
    return masked


def _span_event_value(value):
    if isinstance(value, (bool, int, float, str)):
        return value[:512] if isinstance(value, str) else value
    if value is None:
        return ""
    return json.dumps(value, default=str)[:512]


def _with_logan_aliases(payload: dict) -> dict:
    aliases = {
        alias: payload[key]
        for key, alias in _LOGAN_ALIAS_FIELDS.items()
        if key in payload and alias not in payload
    }
    return {**payload, **aliases}


def _build_oci_log_payload(level: str, message: str, extra: dict, event_time: datetime) -> dict:
    event_payload = _with_logan_aliases(
        {
            "timestamp": event_time.isoformat(),
            "level": level.upper(),
            "message": message,
            **extra,
        }
    )
    plain_message = str(event_payload.get("message", message))
    logan_payload = {
        **event_payload,
        "event.message": plain_message,
        "event_message": plain_message,
        "log_message": plain_message,
    }
    return {
        **logan_payload,
        "message": json.dumps(logan_payload, default=str, separators=(",", ":"), sort_keys=True),
    }


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

logger = logging.getLogger(__name__)

_log_queue: queue.SimpleQueue[tuple[str, str, dict] | None] = queue.SimpleQueue()


def _log_worker() -> None:
    while True:
        item = _log_queue.get()
        if item is None:
            break
        level, message, extra = item
        _push_to_oci_logging(level, message, extra)
        _push_to_splunk(level, message, extra)


_worker_thread = threading.Thread(target=_log_worker, daemon=True, name="octo-shop-log-push")
_worker_thread.start()

_security_logger = logging.getLogger("security.events")
_security_logger.setLevel(logging.INFO)
_security_logger.propagate = False


class _JSONFormatter(logging.Formatter):
    """JSON formatter that injects OTel trace context for Log Analytics correlation."""

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
        return json.dumps(_with_logan_aliases(log_entry), default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JSONFormatter())
_security_logger.addHandler(_handler)

# OCI Logging SDK client (lazy init)
_oci_logging_client = None

# Rate-limited error log for put_logs failures (per-process, not thread-safe
# by design — a missed tick is cheaper than a lock on every push).
_last_logging_error_ts: float = 0.0


def _get_oci_logging_client():
    global _oci_logging_client
    if _oci_logging_client is not None:
        return _oci_logging_client
    if not cfg.logging_configured:
        return None
    try:
        import oci
        auth_mode = cfg.oci_auth_mode if hasattr(cfg, "oci_auth_mode") else "auto"
        if auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            _oci_logging_client = oci.loggingingestion.LoggingClient(config={}, signer=signer)
        else:
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
    """Push a structured log to OCI Logging and optionally Splunk.

    Injects trace_id and oracleApmTraceId for APM ↔ Log Analytics correlation.
    PII fields (email, phone) are masked before external push.
    """
    try:
        workflow = current_workflow()
        if workflow is not None:
            kwargs.setdefault("workflow.id", workflow.workflow_id)
            kwargs.setdefault("workflow.step", workflow.step)
            kwargs.setdefault("workflow_id", workflow.workflow_id)
            kwargs.setdefault("workflow_step", workflow.step)
    except Exception:  # noqa: S110
        pass

    try:
        request_id = current_request_id()
        if request_id and not kwargs.get("request_id"):
            kwargs["request_id"] = request_id
    except Exception:  # noqa: S110
        pass

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
    if cfg.oracle_dsn:
        kwargs["db.connection_name"] = cfg.oracle_dsn

    # Mask PII before logging to external systems
    safe_kwargs = _mask_pii(kwargs)
    _add_current_span_log_event(level, message, safe_kwargs)

    # Write to structured logger (stdout)
    record = logging.LogRecord(
        name="security.events", level=getattr(logging, level.upper(), logging.INFO),
        pathname="", lineno=0, msg=message, args=(), exc_info=None,
    )
    record.extra_fields = safe_kwargs
    _security_logger.handle(record)

    _log_queue.put((level, message, dict(safe_kwargs)))


def _push_to_oci_logging(level: str, message: str, extra: dict):
    client = _get_oci_logging_client()
    if client is None:
        return
    try:
        import oci
        from oci.loggingingestion.models import PutLogsDetails, LogEntryBatch, LogEntry
        event_time = datetime.now(timezone.utc)
        payload = _build_oci_log_payload(level, message, extra, event_time)
        entry = LogEntry(
            data=json.dumps(payload, default=str),
            id=f"octo-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
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
        # ingestion is broken. Silent-fail was masking real problems in prod
        # (KB-456: wrong Monitoring endpoint went undetected for days).
        global _last_logging_error_ts
        now = time.time()
        if now - _last_logging_error_ts > 60.0:
            _last_logging_error_ts = now
            logger.warning("OCI Logging put_logs failed: %s", exc)


def _push_to_splunk(level: str, message: str, extra: dict):
    if not cfg.splunk_hec_url or not cfg.splunk_hec_token:
        return
    try:
        import httpx
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "message": message,
            **extra,
        }
        # SPLUNK_HEC_URL already includes /services/collector/event
        url = cfg.splunk_hec_url.rstrip("/")
        if not url.endswith("/services/collector/event"):
            url = f"{url}/services/collector/event"
        httpx.post(
            url,
            json={"event": event, "sourcetype": f"oci:{cfg.otel_service_name}:security"},
            headers={"Authorization": f"Splunk {cfg.splunk_hec_token}"},
            verify=False,  # nosec B501 - local Splunk HEC uses self-signed certs in the demo; fire-and-forget  # noqa: S501
            timeout=2.0,
        )
    except Exception:  # noqa: S110
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
    """Log a security event with standard attributes for Log Analytics correlation."""
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
