"""LLM telemetry helpers for the grounded Drone Shop assistant.

The helper records correlation metadata without exporting raw prompts or
responses by default. Operators can enable redacted previews with
LLMETRY_CAPTURE_CONTENT=true for a controlled demo, but hashes, lengths,
tokens, trace IDs, and guardrail outcomes are always enough to join OCI APM,
OCI Logging, ATP rows, and Langfuse observations.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from opentelemetry import trace
from sqlalchemy import text

from server.config import cfg
from server.observability import business_metrics
from server.observability.correlation import current_trace_context
from server.observability.logging_sdk import push_log


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _hash_text(value: object) -> str:
    return sha256(str(value or "").encode("utf-8")).hexdigest()


def _redact_text(value: object, limit: int = 700) -> str:
    text_value = str(value or "")
    text_value = _EMAIL_RE.sub("[redacted-email]", text_value)
    text_value = _CARD_RE.sub("[redacted-card]", text_value)
    text_value = _PHONE_RE.sub("[redacted-phone]", text_value)
    return " ".join(text_value.split())[:limit]


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_label(value: object, fallback: str = "unknown", limit: int = 80) -> str:
    text_value = re.sub(r"[^a-zA-Z0-9_.:/@+-]+", "_", str(value or fallback)).strip("_")
    return (text_value or fallback)[:limit]


def _content_attrs(message: str, answer: str) -> dict[str, str]:
    if not cfg.llmetry_capture_content:
        return {}
    return {
        "llm.prompt.preview_redacted": _redact_text(message),
        "llm.response.preview_redacted": _redact_text(answer),
    }


def _usage_values(usage: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    usage = usage or {}
    input_tokens = _coerce_int(usage.get("input_tokens"))
    output_tokens = _coerce_int(usage.get("output_tokens"))
    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def _span_value(value: object) -> object:
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, (bool, int, float)):
        return value
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, default=str)[:1024]


def _set_span_attrs(span, attrs: dict[str, object]) -> None:
    if not span or not span.is_recording():
        return
    for key, value in attrs.items():
        if value is None:
            continue
        span.set_attribute(key, _span_value(value))


def build_assistant_observation(
    *,
    session_id: str,
    message: str,
    answer: str,
    provider: str,
    model_id: str,
    usage: dict[str, Any] | None,
    documents_grounded: int,
    guardrail_allowed: bool,
    guardrail_reason: str,
    latency_ms: float,
    outcome: str = "success",
    error_type: str = "",
    customer_email: str = "",
) -> tuple[dict[str, Any], dict[str, object]]:
    """Return (event row, span/log attrs) for one assistant observation."""
    trace_ctx = current_trace_context()
    input_tokens, output_tokens, total_tokens = _usage_values(usage)
    provider_label = _safe_label(provider)
    model_label = _safe_label(model_id or provider_label, limit=160)
    customer_domain = customer_email.rsplit("@", 1)[-1].lower() if "@" in customer_email else ""
    prompt_hash = _hash_text(message)
    response_hash = _hash_text(answer)
    prompt_length = len(message or "")
    response_length = len(answer or "")
    project_name = _safe_label(cfg.langfuse_project_name, fallback=cfg.app_name, limit=160)
    public_host = _safe_label(cfg.shop_public_hostname, fallback="", limit=160) if cfg.shop_public_hostname else ""

    event = {
        "session_id": session_id,
        "provider": provider_label,
        "model_id": model_label,
        "operation": "chat",
        "outcome": _safe_label(outcome or "success", limit=40),
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
        "prompt_length": prompt_length,
        "response_length": response_length,
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "documents_grounded": int(documents_grounded or 0),
        "guardrail_allowed": 1 if guardrail_allowed else 0,
        "guardrail_reason": _safe_label(guardrail_reason, limit=80),
        "content_captured": 1 if cfg.llmetry_capture_content else 0,
        "latency_ms": round(float(latency_ms or 0.0), 2),
        "trace_id": trace_ctx["trace_id"],
        "span_id": trace_ctx["span_id"],
        "metadata_json": json.dumps(
            {
                "schema": "octo.llmetry.v1",
                "customer_email_domain": customer_domain,
                "error_type": _safe_label(error_type, fallback="", limit=80) if error_type else "",
                "llmetry_capture_content": cfg.llmetry_capture_content,
                "langfuse_configured": cfg.langfuse_configured,
                "project_name": project_name,
                "shop_public_host": public_host,
            },
            sort_keys=True,
        ),
    }

    attrs: dict[str, object] = {
        "llmetry.schema.version": "1.0",
        "llmetry.content.captured": cfg.llmetry_capture_content,
        "llmetry.latency_ms": event["latency_ms"],
        "llm.request.type": "chat",
        "llm.system": provider_label,
        "llm.model": model_label,
        "llm.prompt.hash": prompt_hash,
        "llm.prompt.length": prompt_length,
        "llm.response.hash": response_hash,
        "llm.response.length": response_length,
        "assistant.session_id": session_id,
        "assistant.project.name": project_name,
        "assistant.public_host": public_host,
        "assistant.provider": provider_label,
        "assistant.model_id": model_label,
        "assistant.documents_grounded": int(documents_grounded or 0),
        "assistant.guardrail.allowed": bool(guardrail_allowed),
        "assistant.guardrail.reason": _safe_label(guardrail_reason, limit=80),
        "assistant.outcome": event["outcome"],
        "llmetry.project.name": project_name,
        "gen_ai.system": provider_label,
        "gen_ai.provider.name": provider_label,
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": model_label,
        "gen_ai.response.model": model_label,
        "oci.auth.mode": _safe_label(cfg.oci_auth_mode, limit=40),
        "oci.genai.endpoint_host": cfg.genai_endpoint_host,
        "langfuse.trace.name": "drone-shop-assistant",
        "langfuse.project.name": project_name,
        "langfuse.environment": _safe_label(cfg.app_env, limit=80),
        "langfuse.release": _safe_label(cfg.app_version, limit=80),
        "langfuse.session.id": session_id,
        "langfuse.observation.type": "generation" if provider_label == "oci_genai" else "span",
        "langfuse.observation.metadata.project": project_name,
        "langfuse.observation.metadata.public_host": public_host,
        "langfuse.observation.metadata.prompt_hash": prompt_hash,
        "langfuse.observation.metadata.response_hash": response_hash,
        "langfuse.observation.metadata.documents_grounded": int(documents_grounded or 0),
        "langfuse.observation.metadata.guardrail_reason": _safe_label(guardrail_reason, limit=80),
        "langfuse.observation.metadata.outcome": event["outcome"],
    }
    if customer_domain:
        attrs["customer.email_domain"] = customer_domain[:120]
        attrs["langfuse.user.id"] = f"domain:{customer_domain[:120]}"
    if error_type:
        attrs["error.type"] = _safe_label(error_type, limit=120)
        attrs["llmetry.error_type"] = _safe_label(error_type, limit=120)
    if input_tokens is not None:
        attrs["llm.token.prompt"] = input_tokens
        attrs["gen_ai.usage.input_tokens"] = input_tokens
    if output_tokens is not None:
        attrs["llm.token.completion"] = output_tokens
        attrs["gen_ai.usage.output_tokens"] = output_tokens
    if total_tokens is not None:
        attrs["llm.token.total"] = total_tokens
        attrs["gen_ai.usage.total_tokens"] = total_tokens
    attrs.update(_content_attrs(message, answer))
    return event, attrs


def record_assistant_observation(
    *,
    span=None,
    emit_log: bool = True,
    record_metric: bool = True,
    **kwargs,
) -> dict[str, Any]:
    if not cfg.llmetry_enabled:
        if record_metric:
            business_metrics.record_assistant_query(
                provider=str(kwargs.get("provider") or "unknown"),
                status=str(kwargs.get("outcome") or "success"),
                latency_ms=kwargs.get("latency_ms"),
            )
        return {}
    event, attrs = build_assistant_observation(**kwargs)
    target_span = span or trace.get_current_span()
    _set_span_attrs(target_span, attrs)
    if target_span and target_span.is_recording():
        target_span.add_event(
            "llmetry.assistant.observation",
            {
                "llm.prompt.hash": event["prompt_hash"],
                "llm.response.hash": event["response_hash"],
                "assistant.provider": event["provider"],
                "assistant.outcome": event["outcome"],
                "llmetry.latency_ms": event["latency_ms"],
            },
        )
    if record_metric:
        business_metrics.record_assistant_query(
            provider=event["provider"],
            status=event["outcome"],
            latency_ms=event["latency_ms"],
            input_tokens=event["input_tokens"] or None,
            output_tokens=event["output_tokens"] or None,
        )
    if emit_log:
        push_log(
            "INFO" if event["outcome"] in {"success", "ok"} else "WARNING",
            "Assistant LLMetry observation",
            **{
                "llmetry.schema.version": "1.0",
                "llmetry.latency_ms": event["latency_ms"],
                "llmetry.content.captured": bool(event["content_captured"]),
                "llm.prompt.hash": event["prompt_hash"],
                "llm.prompt.length": event["prompt_length"],
                "llm.response.hash": event["response_hash"],
                "llm.response.length": event["response_length"],
                "llm.token.prompt": event["input_tokens"],
                "llm.token.completion": event["output_tokens"],
                "assistant.session_id": event["session_id"],
                "assistant.project.name": attrs.get("assistant.project.name"),
                "assistant.public_host": attrs.get("assistant.public_host"),
                "assistant.provider": event["provider"],
                "assistant.model_id": event["model_id"],
                "assistant.documents_grounded": event["documents_grounded"],
                "assistant.guardrail.allowed": bool(event["guardrail_allowed"]),
                "assistant.guardrail.reason": event["guardrail_reason"],
                "assistant.outcome": event["outcome"],
                "llmetry.project.name": attrs.get("llmetry.project.name"),
                "langfuse.configured": cfg.langfuse_configured,
                "langfuse.host": cfg._public_url_or_empty(cfg.langfuse_host) or "",
                "langfuse.project.name": attrs.get("langfuse.project.name"),
            },
        )
    return event


async def persist_assistant_observation(db, event: dict[str, Any]) -> None:
    """Persist sanitized LLMetry metadata. Missing table must not break chat."""
    if not cfg.llmetry_store_enabled or not event:
        return
    try:
        await db.execute(
            text(
                """
                INSERT INTO llmetry_events (
                    session_id, provider, model_id, operation, outcome,
                    prompt_hash, response_hash, prompt_length, response_length,
                    input_tokens, output_tokens, documents_grounded,
                    guardrail_allowed, guardrail_reason, content_captured,
                    latency_ms, trace_id, span_id, metadata_json
                ) VALUES (
                    :session_id, :provider, :model_id, :operation, :outcome,
                    :prompt_hash, :response_hash, :prompt_length, :response_length,
                    :input_tokens, :output_tokens, :documents_grounded,
                    :guardrail_allowed, :guardrail_reason, :content_captured,
                    :latency_ms, :trace_id, :span_id, :metadata_json
                )
                """
            ),
            event,
        )
    except Exception:
        return
