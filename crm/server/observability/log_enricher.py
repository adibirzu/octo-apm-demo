"""Logging filter that enriches records with workflow + request context.

Install via `logging.getLogger().addFilter(WorkflowLogEnricher())` to have
every structured log record include `workflow_id`, `workflow_step`, and
`request_id` when present. Existing record fields are never overwritten.
"""

from __future__ import annotations

import logging

from server.observability.workflow_context import current_workflow
from server.security.request_id import current_request_id


class WorkflowLogEnricher(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        wf = current_workflow()
        if wf is not None:
            if not hasattr(record, "workflow_id"):
                record.workflow_id = wf.workflow_id
            if not hasattr(record, "workflow_step"):
                record.workflow_step = wf.step
        rid = current_request_id()
        if rid and not hasattr(record, "request_id"):
            record.request_id = rid
        return True


def install_enricher(root: logging.Logger | None = None) -> WorkflowLogEnricher:
    """Idempotently install the filter on the given (or root) logger."""
    target = root or logging.getLogger()
    for existing in target.filters:
        if isinstance(existing, WorkflowLogEnricher):
            return existing
    enricher = WorkflowLogEnricher()
    target.addFilter(enricher)
    return enricher
