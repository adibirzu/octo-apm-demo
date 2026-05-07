"""Same-origin proxy for the private Workflow Gateway service."""

from __future__ import annotations

import logging
from typing import Iterable

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from opentelemetry.trace import Status, StatusCode

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
)


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


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_workflow_gateway(path: str, request: Request) -> Response:
    """Proxy browser workflow calls to the private gateway with trace context."""
    if not cfg.workflow_gateway_configured:
        raise HTTPException(status_code=503, detail="Workflow gateway is not configured")
    if not _is_allowed_path(path):
        raise HTTPException(status_code=404, detail="Workflow gateway route is not allowed")

    normalized_path = path.lstrip("/")
    target = f"{cfg.workflow_api_base_url.rstrip('/')}/{normalized_path}"
    tracer = get_tracer("octo-drone-shop.workflow-gateway")

    with tracer.start_as_current_span("workflow_gateway.proxy") as span:
        span.set_attributes(
            {
                "app.module": "workflow-gateway-proxy",
                "workflow.gateway.target_path": normalized_path,
                "workflow.gateway.service_name": cfg.workflow_service_name,
                "http.request.method": request.method,
            }
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                upstream = await client.request(
                    request.method,
                    target,
                    params=request.query_params,
                    content=await request.body() if request.method == "POST" else None,
                    headers=_copy_headers(request, _FORWARDED_HEADERS),
                )
        except httpx.HTTPError as exc:
            span.record_exception(exc)
            span.set_attribute("workflow.gateway.error", exc.__class__.__name__)
            logger.warning("Workflow gateway proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail="Workflow gateway request failed") from exc

        span.set_attribute("http.response.status_code", upstream.status_code)
        span.set_attribute("workflow.gateway.response_bytes", len(upstream.content))
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
