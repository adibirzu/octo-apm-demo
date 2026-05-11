"""Admin-only OCI Coordinator surface for OCTO APM Demo resources.

This module intentionally does not expose a general OCI assistant. It is a
scoped admin helper for the OCTO APM Demo deployment and returns deterministic
guidance backed by local admin/observability endpoints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from server.config import cfg
from server.modules._authz import require_admin_user
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api/admin/coordinator", tags=["Admin Coordinator"])
tracer_fn = get_tracer

_PROJECT_SCOPE = "octo-apm-demo"
_ADMIN_SURFACE = "admin.octodemo.cloud"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
_ALLOWED_RESOURCE_HOSTS = {
    "admin.octodemo.cloud",
    "drones.octodemo.cloud",
    "langfuse.octodemo.cloud",
    "lf.octodemo.cloud",
}
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


class CoordinatorQuery(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    page: str = Field(default="admin", max_length=80, pattern=r"^[A-Za-z0-9_./-]*$")
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


@dataclass(frozen=True)
class CoordinatorSource:
    label: str
    endpoint: str


@dataclass(frozen=True)
class CoordinatorTopic:
    key: str
    label: str
    keywords: tuple[str, ...]
    answer: str
    sources: tuple[CoordinatorSource, ...]
    suggested_actions: tuple[str, ...]


_TOPICS = (
    CoordinatorTopic(
        key="admin-users",
        label="Admin users and access",
        keywords=("admin", "user", "users", "role", "roles", "login", "session", "audit", "password"),
        answer=(
            "Use the Admin page to inspect CRM users, roles, active sessions, and audit events. "
            "The coordinator endpoint is admin-only and stays inside the octo-apm-demo resource scope."
        ),
        sources=(
            CoordinatorSource("Admin users", "/api/admin/users"),
            CoordinatorSource("Audit logs", "/api/admin/audit-logs"),
            CoordinatorSource("Session state", "/api/auth/session"),
            CoordinatorSource("Sanitized runtime config", "/api/admin/config"),
        ),
        suggested_actions=(
            "Review user role changes in audit logs before changing access.",
            "Use the login and session traces to correlate user activity with downstream database calls.",
        ),
    ),
    CoordinatorTopic(
        key="orders-customers",
        label="Orders, customers, and business records",
        keywords=("order", "orders", "customer", "customers", "invoice", "invoices", "ticket", "tickets", "shipping"),
        answer=(
            "For user-to-order investigations, pivot from the user/session to CRM orders, customers, "
            "invoices, and shipping records, then use the trace_id fields to connect actions to ATP queries."
        ),
        sources=(
            CoordinatorSource("Orders", "/api/orders"),
            CoordinatorSource("Customers", "/api/customers"),
            CoordinatorSource("Invoices", "/api/invoices"),
            CoordinatorSource("Shipping", "/api/shipping"),
            CoordinatorSource("Order sync health", "/api/observability/360/sync-health"),
        ),
        suggested_actions=(
            "Open the order detail and inspect trace_id, source_system, payment_status, and backlog_status.",
            "Use order sync health when a shop order is missing or delayed in CRM.",
        ),
    ),
    CoordinatorTopic(
        key="database-traces",
        label="Database, Select AI, and traces",
        keywords=("db", "database", "sql", "query", "queries", "select ai", "selectai", "atp", "octoatp", "octoatp_low"),
        answer=(
            "Database questions are limited to the OCTO ATP target used by octo-apm-demo. "
            "Use DB status and the observability DB health endpoint to map admin actions to SQL spans, "
            "SQL_ID enrichment, and ATP session tagging."
        ),
        sources=(
            CoordinatorSource("Database status", "/api/admin/db-status"),
            CoordinatorSource("DB health", "/api/observability/360/db-health"),
            CoordinatorSource("Observability capabilities", "/api/observability/capabilities"),
        ),
        suggested_actions=(
            "Check db.connection_name and trace_id in logs before opening OCI APM Trace Explorer.",
            "Keep Select AI and DB Query lab activity in admin workflows so the storefront does not carry backend load.",
        ),
    ),
    CoordinatorTopic(
        key="observability",
        label="APM, RUM, logs, and Log Analytics",
        keywords=("apm", "rum", "trace", "traces", "log", "logs", "logging", "analytics", "metric", "metrics", "otel"),
        answer=(
            "Observability checks stay on OCTO APM Demo signals: CRM and drone shop traces, RUM journeys, "
            "OCI Logging records, Log Analytics detections, and Prometheus metrics exposed by this deployment."
        ),
        sources=(
            CoordinatorSource("360 dashboard", "/api/observability/360"),
            CoordinatorSource("Capabilities", "/api/observability/capabilities"),
            CoordinatorSource("Security signals", "/api/observability/360/security"),
            CoordinatorSource("Metrics", "/metrics"),
        ),
        suggested_actions=(
            "Filter logs by service.name, trace_id, workflow.id, app.module, and db.connection_name.",
            "Use RUM page actions to link the login flow to API requests and database spans.",
        ),
    ),
    CoordinatorTopic(
        key="shop-integrations",
        label="Drone shop integrations and payments",
        keywords=("drone", "drones", "shop", "storefront", "catalog", "product", "products", "payment", "payments", "checkout"),
        answer=(
            "The coordinator can discuss the drone shop only as an OCTO APM Demo dependency. "
            "Use integration health, catalog sync, payment simulation signals, and order sync state to trace "
            "shop activity into CRM admin views."
        ),
        sources=(
            CoordinatorSource("Drone shop health", "/api/integrations/drone-shop/health"),
            CoordinatorSource("Drone shop catalog", "/api/integrations/drone-shop/product-catalog"),
            CoordinatorSource("Drone shop order history", "/api/integrations/drone-shop/order-history"),
            CoordinatorSource("Order sync health", "/api/observability/360/sync-health"),
        ),
        suggested_actions=(
            "Verify payment simulation results in order traces before changing checkout controls.",
            "Use catalog sync endpoints from admin, not from the public storefront.",
        ),
    ),
    CoordinatorTopic(
        key="security-simulation",
        label="Security checks and simulation labs",
        keywords=("security", "waf", "attack", "mitre", "cloud guard", "vss", "osquery", "chaos", "simulation", "detection"),
        answer=(
            "Security questions are limited to OCTO APM Demo traces, app security spans, WAF/log events, "
            "Cloud Guard/VSS demo signals, and Log Analytics detection rules already tied to the admin lab."
        ),
        sources=(
            CoordinatorSource("Simulation status", "/api/simulate/status"),
            CoordinatorSource("Security summary", "/api/observability/360/security"),
            CoordinatorSource("Attack lab", "/settings"),
            CoordinatorSource("Audit logs", "/api/admin/audit-logs"),
        ),
        suggested_actions=(
            "Correlate detection rules by trace_id, source.ip, security.attack.type, and workflow.id.",
            "Keep remediation actions approval-gated unless the scenario is a tier-low cleanup.",
        ),
    ),
    CoordinatorTopic(
        key="genai-llm",
        label="GenAI, Langfuse, and LLM telemetry",
        keywords=("ai", "assistant", "genai", "llm", "langfuse", "lf.octodemo.cloud", "select ai", "selectai"),
        answer=(
            "GenAI and LLM telemetry is scoped to OCTO APM Demo: OCI APM spans, Langfuse project events, "
            "and admin-only Select AI or assistant activity. The public drone shop should not run coordinator logic."
        ),
        sources=(
            CoordinatorSource("Observability capabilities", "/api/observability/capabilities"),
            CoordinatorSource("Database status", "/api/admin/db-status"),
            CoordinatorSource("Admin config", "/api/admin/config"),
        ),
        suggested_actions=(
            "Record model/provider, prompt class, token counts, latency, and trace_id on GenAI spans.",
            "Use Langfuse only for drones.octodemo.cloud project data and avoid unrelated project queries.",
        ),
    ),
)

_ADMIN_KEYWORDS = frozenset(
    keyword for topic in _TOPICS for keyword in topic.keywords
)
_ALLOWED_RESOURCE_TERMS = frozenset(
    {
        "octo",
        "octodemo",
        "octo demo",
        "octo-apm-demo",
        "octo apm demo",
        "admin.octodemo.cloud",
        "drones.octodemo.cloud",
        "langfuse.octodemo.cloud",
        "lf.octodemo.cloud",
        "enterprise-crm-portal",
        "octo-drone-shop",
        "octoatp",
        "octoatp_low",
        "oci apm",
        "log analytics",
        "oci logging",
        "workflow gateway",
    }
)
_BLOCKED_SCOPE_PHRASES = (
    "all compartments",
    "every compartment",
    "root compartment",
    "all resources",
    "every resource",
    "entire tenancy",
    "all tenancies",
    "another tenancy",
    "other tenancy",
    "iam user",
    "iam users",
    "identity domain",
    "adibirzu",
    "seven kingdoms",
    "control plane",
    "control-plane",
    "platform backend",
    "generic project",
    "generic tenancy",
    "mushop",
)


@router.get("/scope")
async def coordinator_scope(request: Request):
    """Return the admin coordinator scope after admin authorization."""
    actor = require_admin_user(request)
    host = _require_admin_host(request)
    tracer = tracer_fn()
    with tracer.start_as_current_span("admin.coordinator.scope") as span:
        _set_common_span_attrs(span, actor, host, "admin", allowed=True, topic="scope")
        return _scope_payload()


@router.post("/query")
async def coordinator_query(payload: CoordinatorQuery, request: Request):
    """Answer admin-page questions while refusing unrelated OCI/project scope."""
    actor = require_admin_user(request)
    host = _require_admin_host(request)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    tracer = tracer_fn()
    with tracer.start_as_current_span("admin.coordinator.query") as span:
        scope_allowed, refusal_reason = _scope_allows(message)
        topics = _match_topics(message)
        allowed = scope_allowed and bool(topics)
        topic_key = ",".join(topic.key for topic in topics) if topics else "out_of_scope"
        _set_common_span_attrs(span, actor, host, payload.page or "admin", allowed=allowed, topic=topic_key)
        span.set_attribute("coordinator.message.length", len(message))
        span.set_attribute("coordinator.refusal_reason", refusal_reason)

        if not allowed:
            response = _refusal_response(refusal_reason)
            _log_query(actor, host, payload.page or "admin", allowed=False, topic=topic_key, reason=refusal_reason)
            return response

        response = _answer_response(topics)
        span.set_attribute("coordinator.sources.count", len(response["sources"]))
        _log_query(actor, host, payload.page or "admin", allowed=True, topic=topic_key, reason="")
        return response


def _scope_payload() -> dict:
    return {
        "surface": _ADMIN_SURFACE,
        "scope": _PROJECT_SCOPE,
        "allowed_hosts": sorted(_ALLOWED_RESOURCE_HOSTS),
        "admin_only": True,
        "topics": [
            {"key": topic.key, "label": topic.label}
            for topic in _TOPICS
        ],
        "refusal": "I can only answer questions about OCTO APM Demo admin pages and OCTO DEMO resources.",
    }


def _request_host(request: Request) -> str:
    raw_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.hostname
        or ""
    )
    raw_host = raw_host.split(",", 1)[0].strip().lower()
    if raw_host.startswith("[") and "]" in raw_host:
        return raw_host[1:raw_host.index("]")]
    return raw_host.rsplit(":", 1)[0] if ":" in raw_host else raw_host


def _configured_admin_hosts() -> set[str]:
    hosts = {_ADMIN_SURFACE}
    parsed = urlparse(cfg.crm_base_url or "")
    if parsed.hostname == _ADMIN_SURFACE:
        hosts.add(parsed.hostname)
    return hosts


def _require_admin_host(request: Request) -> str:
    host = _request_host(request)
    if host in _LOCAL_HOSTS or host in _configured_admin_hosts():
        return host
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="OCI Coordinator is only available from admin.octodemo.cloud.",
    )


def _scope_allows(message: str) -> tuple[bool, str]:
    normalized = _normalize(message)
    domains = {domain.lower() for domain in _DOMAIN_RE.findall(message)}
    external_domains = domains.difference(_ALLOWED_RESOURCE_HOSTS)
    if external_domains:
        return False, "external_domain"
    for phrase in _BLOCKED_SCOPE_PHRASES:
        if phrase in normalized:
            return False, "broad_or_unrelated_oci_scope"
    if any(term in normalized for term in _ALLOWED_RESOURCE_TERMS):
        return True, ""
    if any(keyword in normalized for keyword in _ADMIN_KEYWORDS):
        return True, ""
    if any(term in normalized for term in ("oci", "tenancy", "compartment", "resource", "cloud")):
        return False, "missing_octo_scope"
    return False, "unsupported_topic"


def _match_topics(message: str) -> list[CoordinatorTopic]:
    normalized = _normalize(message)
    matches = [
        topic for topic in _TOPICS
        if any(keyword in normalized for keyword in topic.keywords)
    ]
    if not matches and any(term in normalized for term in _ALLOWED_RESOURCE_TERMS):
        return [_TOPICS[3]]
    return matches[:4]


def _normalize(message: str) -> str:
    return " ".join(message.lower().split())


def _answer_response(topics: list[CoordinatorTopic]) -> dict:
    sources: list[dict[str, str]] = []
    actions: list[str] = []
    seen_sources: set[str] = set()
    seen_actions: set[str] = set()
    for topic in topics:
        for source in topic.sources:
            if source.endpoint not in seen_sources:
                seen_sources.add(source.endpoint)
                sources.append({"label": source.label, "endpoint": source.endpoint})
        for action in topic.suggested_actions:
            if action not in seen_actions:
                seen_actions.add(action)
                actions.append(action)

    answer = " ".join(topic.answer for topic in topics)
    answer += " I will only use octo-apm-demo resources for this answer."
    return {
        "allowed": True,
        "surface": _ADMIN_SURFACE,
        "scope": _PROJECT_SCOPE,
        "answer": answer,
        "sources": sources,
        "suggested_actions": actions[:6],
    }


def _refusal_response(reason: str) -> dict:
    return {
        "allowed": False,
        "surface": _ADMIN_SURFACE,
        "scope": _PROJECT_SCOPE,
        "answer": (
            "I can only answer questions about OCTO APM Demo admin pages and OCTO DEMO resources. "
            "Ask about admin users, orders, traces, logs, ATP, the drone shop dependency, security simulations, "
            "or GenAI telemetry for octo-apm-demo."
        ),
        "sources": [],
        "suggested_actions": [
            "Rephrase the question with an OCTO APM Demo resource or admin page.",
            "Use admin.octodemo.cloud for coordinator questions.",
        ],
        "reason": reason,
    }


def _set_common_span_attrs(span, actor: dict, host: str, page: str, *, allowed: bool, topic: str) -> None:
    span.set_attribute("admin.actor", actor.get("username", "unknown"))
    span.set_attribute("admin.page", page)
    span.set_attribute("coordinator.surface", "admin")
    span.set_attribute("coordinator.host", host)
    span.set_attribute("coordinator.scope", _PROJECT_SCOPE)
    span.set_attribute("coordinator.allowed", allowed)
    span.set_attribute("coordinator.topic", topic)


def _log_query(actor: dict, host: str, page: str, *, allowed: bool, topic: str, reason: str) -> None:
    push_log(
        "INFO" if allowed else "WARNING",
        "Admin coordinator query evaluated",
        **{
            "app.module": "admin",
            "app.page.name": page,
            "admin.actor": actor.get("username", "unknown"),
            "coordinator.surface": "admin",
            "coordinator.host": host,
            "coordinator.scope": _PROJECT_SCOPE,
            "coordinator.allowed": allowed,
            "coordinator.topic": topic,
            "coordinator.refusal_reason": reason,
        },
    )
