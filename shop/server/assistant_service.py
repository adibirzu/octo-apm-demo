"""Governed Drone Shop assistant execution shared by admin and service calls."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import HTTPException
from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from server.config import cfg
from server.database import get_db
from server.genai_service import chat_with_documents, genai_configured
from server.observability import business_metrics, llmetry
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.storefront import build_grounding_documents, enrich_product, fallback_product_answer

ASSISTANT_SCOPE = "drone_specs"
_ASSISTANT_REFUSAL = (
    "I can only answer questions about OCTO drone specs, payloads, sensors, stock, "
    "pricing, checkout options, and mission fit."
)
_ASSISTANT_ALLOWED_TERMS = {
    "drone", "drones", "uav", "uas", "quadcopter", "octocopter", "vtol", "fpv",
    "platform", "airframe", "payload", "payloads", "sensor", "sensors", "camera",
    "thermal", "lidar", "rtk", "ppk", "gnss", "gimbal", "radio", "mesh", "range",
    "endurance", "flight", "battery", "batteries", "propeller", "props", "motor",
    "esc", "controller", "pixhawk", "mapping", "survey", "inspection", "cinema",
    "agriculture", "public safety", "search", "rescue", "ndaa", "stock", "price",
    "pricing", "cost", "sku", "catalog", "compare", "recommend", "mission",
    "spec", "specs", "shipping", "lead time", "checkout", "payment", "warranty",
    "skydio", "parrot", "anafi", "autel", "wingtra", "trinity", "flyability",
    "elios", "freefly", "astro", "teledyne", "flir", "siras", "gremsy",
    "holybro", "iflight", "foxtech", "tattu", "sony", "doodle",
}
_ASSISTANT_BLOCKED_TERMS = {
    "ignore previous", "ignore the previous", "system prompt", "developer message",
    "secret", "password", "api key", "token", "jailbreak", "malware", "exploit",
    "drop table", "delete from", "credit card number", "ssn",
}
_MAX_MESSAGE_CHARS = 1000
_MAX_PRODUCT_FOCUS_CHARS = 120
_MAX_CUSTOMER_EMAIL_CHARS = 200


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


def _bounded_text(value: object, *, limit: int) -> str:
    text_value = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text_value.split())[:limit]


def _product_terms(products: list[dict[str, Any]]) -> set[str]:
    terms: set[str] = set()
    for product in products:
        sku = str(product.get("sku") or "").strip().lower()
        name = str(product.get("name") or "").strip().lower()
        category = str(product.get("category") or "").strip().lower()
        if sku:
            terms.add(sku)
        if name:
            terms.add(name)
            name_parts = [part for part in name.replace("-", " ").split() if len(part) >= 5]
            if len(name_parts) >= 2:
                terms.update(name_parts[:3])
        if category:
            terms.add(category)
    return terms


def assistant_scope_decision(message: str, products: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    """Return whether the advisor can answer without leaving drone catalog scope."""
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return False, "empty_message"
    if any(term in normalized for term in _ASSISTANT_BLOCKED_TERMS):
        return False, "blocked_term"
    product_terms = _product_terms(products or [])
    if any(term and term in normalized for term in product_terms):
        return True, "catalog_product"
    if any(term in normalized for term in _ASSISTANT_ALLOWED_TERMS):
        return True, "drone_domain_keyword"
    return False, "out_of_scope"


async def assistant_history_payload(session_id: str) -> dict[str, Any]:
    safe_session_id = _bounded_text(session_id, limit=64)
    if not safe_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    async with get_db() as db:
        messages = await db.execute(
            text(
                "SELECT role, content, provider, model_id, created_at "
                "FROM assistant_messages WHERE session_id = :session_id ORDER BY created_at ASC"
            ),
            {"session_id": safe_session_id},
        )
        return {"session_id": safe_session_id, "messages": [dict(row) for row in messages.mappings().all()]}


async def run_assistant_query(
    payload: dict[str, Any],
    *,
    surface: str = "admin",
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one governed assistant turn with ATP grounding and LLMetry spans."""
    message = _bounded_text(payload.get("message"), limit=_MAX_MESSAGE_CHARS + 1)
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if len(message) > _MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail=f"message exceeds {_MAX_MESSAGE_CHARS} characters")

    session_id = _bounded_text(payload.get("session_id") or str(uuid.uuid4()), limit=64) or str(uuid.uuid4())
    product_focus = _bounded_text(payload.get("product_focus"), limit=_MAX_PRODUCT_FOCUS_CHARS)
    customer_email = _bounded_text(payload.get("customer_email"), limit=_MAX_CUSTOMER_EMAIL_CHARS)
    safe_surface = "internal-service" if surface == "internal-service" else "admin"
    span_prefix = "admin" if safe_surface == "admin" else "internal"
    assistant_started = time.monotonic()
    assistant_outcome = "success"
    tracer = get_tracer()

    with tracer.start_as_current_span(f"{span_prefix}.assistant.query") as span:
        apply_span_attributes(span, {
            "assistant.session_id": session_id,
            "assistant.message_length": len(message),
            "assistant.product_focus": product_focus or "all",
            "assistant.customer_email_provided": bool(customer_email),
            "assistant.surface": safe_surface,
            "auth.role": str((actor or {}).get("role", "unknown")),
            "auth.user_id": str((actor or {}).get("sub", "")),
            "app.page.name": "admin",
            "app.module": "admin",
            "app.logical_endpoint": f"{span_prefix}.assistant.query",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })

        async with get_db() as db:
            existing = await db.execute(
                text(
                    "SELECT session_id FROM assistant_sessions WHERE session_id = :session_id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"session_id": session_id},
            )
            if not existing.first():
                try:
                    await db.execute(
                        text(
                            "INSERT INTO assistant_sessions (session_id, customer_email, product_focus, source) "
                            "VALUES (:session_id, :customer_email, :product_focus, :source)"
                        ),
                        {
                            "session_id": session_id,
                            "customer_email": customer_email,
                            "product_focus": product_focus,
                            "source": safe_surface,
                        },
                    )
                except IntegrityError:
                    await db.rollback()

            query = (
                "SELECT id, name, sku, description, price, stock, category, image_url "
                "FROM products WHERE is_active = 1"
            )
            params: dict[str, Any] = {}
            if product_focus:
                query += " AND (lower(name) LIKE lower(:focus) OR lower(category) LIKE lower(:focus))"
                params["focus"] = f"%{product_focus}%"
            query += " ORDER BY price DESC FETCH FIRST 8 ROWS ONLY"
            products_result = await db.execute(text(query), params)
            products = [enrich_product(dict(row)) for row in products_result.mappings().all()]
            documents = build_grounding_documents(products)
            guardrail_allowed, guardrail_reason = assistant_scope_decision(message, products)
            apply_span_attributes(span, {
                "assistant.guardrail.scope": ASSISTANT_SCOPE,
                "assistant.guardrail.allowed": guardrail_allowed,
                "assistant.guardrail.reason": guardrail_reason,
                "assistant.documents_grounded": len(documents),
            })

            await db.execute(
                text(
                    "INSERT INTO assistant_messages (session_id, role, content, provider, model_id, trace_id) "
                    "VALUES (:session_id, 'user', :content, 'client', '', :trace_id)"
                ),
                {
                    "session_id": session_id,
                    "content": message,
                    "trace_id": _trace_id(),
                },
            )

        response_payload = None
        if not guardrail_allowed:
            assistant_outcome = "guardrail_blocked"
            response_payload = {
                "answer": _ASSISTANT_REFUSAL,
                "provider": "guardrail_scope_filter",
                "model_id": "drone-spec-scope",
                "usage": {},
            }
        elif genai_configured():
            with tracer.start_as_current_span(f"{span_prefix}.assistant.genai") as genai_span:
                genai_started = time.monotonic()
                try:
                    apply_span_attributes(genai_span, {
                        "assistant.guardrail.scope": ASSISTANT_SCOPE,
                        "assistant.guardrail.allowed": True,
                        "assistant.documents_grounded": len(documents),
                        "assistant.surface": safe_surface,
                        "gen_ai.system": "oci_genai",
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": cfg.oci_genai_model_id,
                        "llm.system": "oci_genai",
                        "llm.model": cfg.oci_genai_model_id,
                    })
                    response_payload = await chat_with_documents(message, documents)
                    llmetry.record_assistant_observation(
                        span=genai_span,
                        emit_log=False,
                        record_metric=False,
                        session_id=session_id,
                        message=message,
                        answer=response_payload.get("answer", ""),
                        provider=response_payload.get("provider", "oci_genai"),
                        model_id=response_payload.get("model_id", cfg.oci_genai_model_id),
                        usage=response_payload.get("usage") or {},
                        documents_grounded=len(documents),
                        guardrail_allowed=True,
                        guardrail_reason=guardrail_reason,
                        latency_ms=(time.monotonic() - genai_started) * 1000,
                        outcome="success",
                        customer_email=customer_email,
                    )
                except Exception as exc:
                    assistant_outcome = "fallback"
                    genai_span.record_exception(exc)
                    genai_span.set_attribute("assistant.outcome", "error")
                    genai_span.set_attribute("otel.status_code", "ERROR")
                    llmetry.record_assistant_observation(
                        span=genai_span,
                        emit_log=False,
                        record_metric=False,
                        session_id=session_id,
                        message=message,
                        answer="",
                        provider="oci_genai",
                        model_id=cfg.oci_genai_model_id,
                        usage={},
                        documents_grounded=len(documents),
                        guardrail_allowed=True,
                        guardrail_reason=guardrail_reason,
                        latency_ms=(time.monotonic() - genai_started) * 1000,
                        outcome="error",
                        error_type=exc.__class__.__name__,
                        customer_email=customer_email,
                    )
                    push_log(
                        "ERROR",
                        f"OCI GenAI assistant failed: {exc}",
                        **{
                            "assistant.session_id": session_id,
                            "assistant.provider": "oci_genai",
                            "assistant.outcome": "error",
                            "assistant.surface": safe_surface,
                            "llmetry.error_type": exc.__class__.__name__,
                        },
                    )

        if response_payload is None:
            if assistant_outcome == "success":
                assistant_outcome = "fallback"
            response_payload = {
                "answer": fallback_product_answer(message, products),
                "provider": "local_grounded_fallback",
                "model_id": "atp-catalog",
                "usage": {},
            }

        llmetry_event = llmetry.record_assistant_observation(
            span=span,
            emit_log=True,
            record_metric=True,
            session_id=session_id,
            message=message,
            answer=response_payload["answer"],
            provider=response_payload["provider"],
            model_id=response_payload["model_id"],
            usage=response_payload.get("usage") or {},
            documents_grounded=len(documents),
            guardrail_allowed=guardrail_allowed,
            guardrail_reason=guardrail_reason,
            latency_ms=(time.monotonic() - assistant_started) * 1000,
            outcome=assistant_outcome,
            customer_email=customer_email,
        )

        async with get_db() as db:
            await db.execute(
                text(
                    "INSERT INTO assistant_messages (session_id, role, content, provider, model_id, trace_id) "
                    "VALUES (:session_id, 'assistant', :content, :provider, :model_id, :trace_id)"
                ),
                {
                    "session_id": session_id,
                    "content": response_payload["answer"],
                    "provider": response_payload["provider"],
                    "model_id": response_payload["model_id"],
                    "trace_id": _trace_id(),
                },
            )
            await llmetry.persist_assistant_observation(db, llmetry_event)

        span.set_attribute("assistant.provider", response_payload["provider"])
        span.set_attribute("assistant.genai_used", response_payload["provider"] == "oci_genai")
        span.set_attribute("assistant.documents_grounded", len(documents))
        span.set_attribute("assistant.guardrail.allowed", guardrail_allowed)
        span.set_attribute("assistant.guardrail.reason", guardrail_reason)
        span.set_attribute("assistant.guardrail.scope", ASSISTANT_SCOPE)
        usage = response_payload.get("usage") or {}
        if usage.get("input_tokens") is not None:
            span.set_attribute("llm.token.prompt", int(usage["input_tokens"]))
        if usage.get("output_tokens") is not None:
            span.set_attribute("llm.token.completion", int(usage["output_tokens"]))
        if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            span.set_attribute("llm.token.total", int(usage["input_tokens"]) + int(usage["output_tokens"]))
        push_log(
            "INFO",
            "Assistant response generated",
            **{
                "assistant.session_id": session_id,
                "assistant.provider": response_payload["provider"],
                "assistant.model_id": response_payload["model_id"],
                "assistant.guardrail.scope": ASSISTANT_SCOPE,
                "assistant.guardrail.allowed": guardrail_allowed,
                "assistant.guardrail.reason": guardrail_reason,
                "assistant.outcome": assistant_outcome,
                "assistant.surface": safe_surface,
            },
        )
        return {
            "session_id": session_id,
            "answer": response_payload["answer"],
            "provider": response_payload["provider"],
            "model_id": response_payload["model_id"],
            "usage": response_payload.get("usage", {}),
            "documents_used": len(documents),
        }
