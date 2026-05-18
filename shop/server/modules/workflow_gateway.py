"""Same-origin proxy for the private Workflow Gateway service."""

from __future__ import annotations

import logging
import json
from typing import Iterable
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from opentelemetry.trace import Status, StatusCode

from server.auth_security import require_admin_or_internal_service
from server.config import cfg
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow-gateway", tags=["workflow-gateway"])

_ALLOWED_PREFIXES = (
    "api/workflows/",
    "api/components/",
    "api/query-lab/",
    "api/selectai/",
)
_FORWARDED_HEADERS = (
    "authorization",
    "content-type",
    "traceparent",
    "tracestate",
    "x-correlation-id",
    "x-request-id",
    "x-session-id",
    "x-internal-service-key",
)
_MAX_PROXY_BODY_BYTES = 16_384
_MAX_SELECTAI_PROMPT_CHARS = 1000
_ALLOWED_SELECTAI_ACTIONS = {"showsql", "narrate", "chat"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def _is_allowed_path(path: str) -> bool:
    normalized = path.lstrip("/")
    return any(normalized.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def _copy_headers(request: Request, names: Iterable[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in names:
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _operation_for_path(path: str) -> str:
    if path.startswith("api/selectai/"):
        return "selectai.generate"
    if path.startswith("api/query-lab/run"):
        return "query_lab.run"
    if path.startswith("api/query-lab/executions"):
        return "query_lab.executions"
    if path.startswith("api/workflows/overview"):
        return "workflow.overview"
    if path.startswith("api/components/"):
        return "component.snapshots"
    return "workflow.proxy"


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


def _admin_surface_hosts() -> set[str]:
    hosts = set(_LOCAL_HOSTS)
    crm_host = (getattr(cfg, "crm_public_hostname", "") or "").strip().lower()
    if crm_host:
        hosts.add(crm_host)
    crm_url = (getattr(cfg, "crm_public_url", "") or "").strip()
    if crm_url:
        parsed = urlparse(crm_url)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    dns_domain = (getattr(cfg, "dns_domain", "") or "").strip().lower()
    if dns_domain:
        hosts.add(f"admin.{dns_domain}")
        hosts.add(f"crm.{dns_domain}")
    return hosts


def _require_admin_surface_host(request: Request) -> str:
    host = _request_host(request)
    if host in _admin_surface_hosts():
        return host
    raise HTTPException(
        status_code=403,
        detail="Workflow Gateway admin labs are only available from the admin surface.",
    )


def _json_payload(content: bytes | None) -> dict:
    if not content:
        return {}
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_proxy_payload(path: str, content: bytes | None) -> dict:
    if content and len(content) > _MAX_PROXY_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Workflow gateway request body is too large")
    payload = _json_payload(content)
    if path.startswith("api/selectai/"):
        prompt = str(payload.get("prompt") or "").strip()
        action = str(payload.get("action") or "showsql").strip().lower() or "showsql"
        if len(prompt) > _MAX_SELECTAI_PROMPT_CHARS:
            raise HTTPException(status_code=400, detail=f"prompt exceeds {_MAX_SELECTAI_PROMPT_CHARS} characters")
        if action not in _ALLOWED_SELECTAI_ACTIONS:
            raise HTTPException(status_code=400, detail="action must be showsql, narrate, or chat")
    return payload


def _apply_operation_attributes(span, *, path: str, request: Request, payload: dict, principal: dict) -> None:
    operation = _operation_for_path(path)
    span.set_attributes(
        {
            "app.module": "admin-workflow-gateway",
            "app.logical_endpoint": f"admin.{operation}",
            "workflow.gateway.operation": operation,
            "workflow.gateway.target_path": path,
            "workflow.gateway.service_name": cfg.workflow_service_name,
            "workflow.gateway.admin_required": True,
            "http.request.method": request.method,
            "auth.role": str(principal.get("role", "unknown")),
        }
    )
    if operation == "selectai.generate":
        action = str(payload.get("action") or request.query_params.get("action") or "showsql").strip().lower()
        prompt = str(payload.get("prompt") or "")
        span.set_attributes(
            {
                "selectai.configured": cfg.selectai_configured,
                "selectai.profile_name": cfg.selectai_profile_name or "not-configured",
                "selectai.action": action or "showsql",
                "selectai.prompt_length": len(prompt),
                "db.system": "oracle",
                "db.operation": "DBMS_CLOUD_AI.GENERATE",
                "db.oracle.selectai.profile": cfg.selectai_profile_name or "not-configured",
            }
        )
        span.add_event(
            "selectai.proxy.request",
            {
                "selectai.action": action or "showsql",
                "selectai.prompt_length": len(prompt),
                "selectai.configured": bool(cfg.selectai_configured),
            },
        )
    elif operation == "query_lab.run":
        span.set_attribute("workflow.query_name", str(payload.get("query_name") or "unknown")[:120])


def _apply_upstream_attributes(span, upstream: httpx.Response) -> None:
    try:
        payload = upstream.json()
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if not isinstance(result, dict):
        return
    if result.get("status"):
        span.set_attribute("workflow.status", str(result.get("status"))[:80])
    if result.get("duration_ms") is not None:
        try:
            span.set_attribute("db.client.execution_time_ms", float(result.get("duration_ms")))
        except (TypeError, ValueError):
            pass
    if result.get("row_count") is not None:
        try:
            span.set_attribute("db.row_count", int(result.get("row_count")))
        except (TypeError, ValueError):
            pass
    if result.get("trace_id"):
        span.set_attribute("workflow.gateway.upstream_trace_id", str(result.get("trace_id"))[:64])


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_workflow_gateway(path: str, request: Request) -> Response:
    """Proxy browser workflow calls to the private gateway with trace context."""
    principal = require_admin_or_internal_service(request)
    admin_host = ""
    if principal.get("role") != "service":
        admin_host = _require_admin_surface_host(request)
    if not cfg.workflow_gateway_configured:
        raise HTTPException(status_code=503, detail="Workflow gateway is not configured")
    if not _is_allowed_path(path):
        raise HTTPException(status_code=404, detail="Workflow gateway route is not allowed")

    normalized_path = path.lstrip("/")
    content = await request.body() if request.method == "POST" else None
    payload = _validate_proxy_payload(normalized_path, content)
    target = f"{cfg.workflow_api_base_url.rstrip('/')}/{normalized_path}"
    tracer = get_tracer("octo-drone-shop.workflow-gateway")

    with tracer.start_as_current_span(f"workflow_gateway.{_operation_for_path(normalized_path)}") as span:
        _apply_operation_attributes(span, path=normalized_path, request=request, payload=payload, principal=principal)
        span.set_attribute("workflow.gateway.admin_surface_host", admin_host or "internal-service")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                upstream = await client.request(
                    request.method,
                    target,
                    params=request.query_params,
                    content=content,
                    headers=_copy_headers(request, _FORWARDED_HEADERS),
                )
        except httpx.HTTPError as exc:
            span.record_exception(exc)
            span.set_attribute("workflow.gateway.error", exc.__class__.__name__)
            logger.warning("Workflow gateway proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail="Workflow gateway request failed") from exc

        span.set_attribute("http.response.status_code", upstream.status_code)
        span.set_attribute("workflow.gateway.response_bytes", len(upstream.content))
        _apply_upstream_attributes(span, upstream)
        if upstream.status_code >= 400:
            span.set_status(Status(StatusCode.ERROR, str(upstream.status_code)))

    headers = {}
    content_type = upstream.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
    )
