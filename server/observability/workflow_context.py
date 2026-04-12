"""Workflow-context propagation.

Stamps every request with a logical `workflow_id` (e.g. `checkout`,
`browse-catalog`) derived from the request path. The value is exposed via
a contextvar, an OTel span attribute, and a log record field so that OCI
Log Analytics searches can group across services without parsing URLs.

The registry is intentionally small and expressed as tuples of
`(pattern, workflow_id, step)` to keep the hot path O(n) over a short list.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:  # OpenTelemetry is optional in some test contexts.
    from opentelemetry import trace

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - defensive
    _OTEL_AVAILABLE = False


@dataclass(frozen=True)
class WorkflowContext:
    workflow_id: str
    step: str


_ctx: ContextVar[WorkflowContext | None] = ContextVar("workflow_ctx", default=None)


def current_workflow() -> WorkflowContext | None:
    return _ctx.get()


WorkflowRule = tuple[re.Pattern[str], str, str]


def _compile(rules: Iterable[tuple[str, str, str]]) -> tuple[WorkflowRule, ...]:
    return tuple((re.compile(pat), wf, step) for pat, wf, step in rules)


# Default registry — extended by project-level registry if provided.
DEFAULT_RULES: tuple[WorkflowRule, ...] = _compile(
    [
        (r"^/shop(?:/|$)", "browse-catalog", "catalog"),
        (r"^/api/products", "browse-catalog", "product-list"),
        (r"^/api/cart", "add-to-cart", "cart"),
        (r"^/api/orders", "checkout", "order"),
        (r"^/api/payments", "checkout", "payment"),
        (r"^/api/shipments", "checkout", "shipment"),
        (r"^/api/customers", "crm-lead-capture", "customer"),
        (r"^/api/campaigns", "admin-analytics", "campaigns"),
        (r"^/api/analytics", "admin-analytics", "analytics"),
        (r"^/api/admin/chaos", "chaos-control", "admin"),
    ]
)


def resolve_workflow(path: str, extra: tuple[WorkflowRule, ...] = ()) -> WorkflowContext:
    for pattern, wf, step in (*extra, *DEFAULT_RULES):
        if pattern.match(path):
            return WorkflowContext(workflow_id=wf, step=step)
    return WorkflowContext(workflow_id="other", step="unmapped")


class WorkflowContextMiddleware(BaseHTTPMiddleware):
    """Attach a `WorkflowContext` to every request."""

    def __init__(self, app, *, extra_rules: tuple[WorkflowRule, ...] = ()) -> None:
        super().__init__(app)
        self._extra = extra_rules

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        wf = resolve_workflow(request.url.path, self._extra)
        request.state.workflow = wf
        token = _ctx.set(wf)
        if _OTEL_AVAILABLE:
            span = trace.get_current_span()
            if span is not None:
                span.set_attribute("workflow.id", wf.workflow_id)
                span.set_attribute("workflow.step", wf.step)
        try:
            response = await call_next(request)
        finally:
            _ctx.reset(token)
        response.headers.setdefault("X-Workflow-Id", wf.workflow_id)
        return response
