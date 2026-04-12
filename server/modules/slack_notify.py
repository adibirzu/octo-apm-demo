"""Slack notifier — emit critical events to a Slack incoming webhook.

Minimal, dependency-free (stdlib-only) notifier used by the shop to
surface critical events to an operator channel. Fire-and-forget — never
blocks the request path, never raises into the caller.

Activation: set ``SLACK_WEBHOOK_URL`` to a Slack Incoming Webhook URL.
Optional: ``SLACK_NOTIFY_CHANNEL`` (overrides the webhook's default
channel when the webhook was created with a different one), and
``SLACK_NOTIFY_ENABLED=false`` to hard-disable without removing creds.

Correlation: every event carries an ``oracleApmTraceId`` field so the
ObserveAI Log Analytics entity can join the notification with the
originating trace.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("crm.slack_notify")


def _enabled() -> bool:
    flag = os.getenv("SLACK_NOTIFY_ENABLED", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("SLACK_WEBHOOK_URL", "").strip())


def _channel_override() -> Optional[str]:
    ch = os.getenv("SLACK_NOTIFY_CHANNEL", "").strip()
    return ch or None


def _trace_id(extra: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract the current OTEL trace id if available, falling back to
    an explicit ``oracleApmTraceId`` entry in the event payload."""
    if extra and extra.get("oracleApmTraceId"):
        return str(extra["oracleApmTraceId"])
    try:
        from opentelemetry import trace  # type: ignore

        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


async def notify(
    event: str,
    message: str,
    *,
    severity: str = "info",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Send a Slack notification. No-op when disabled.

    Parameters
    ----------
    event : str
        Short machine-readable event code (``checkout_failure``,
        ``chaos_triggered``, ``order_sync_failure`` …).
    message : str
        Human-readable summary shown in the Slack message.
    severity : str
        ``info`` | ``warning`` | ``error`` | ``critical`` — drives the
        colour bar on the Slack attachment.
    extra : dict, optional
        Additional key-value pairs surfaced as Slack fields and
        preserved for the ObserveAI log correlation.
    """
    if not _enabled():
        return

    trace_id = _trace_id(extra)
    colour = {
        "info": "#2eb67d",
        "warning": "#ecb22e",
        "error": "#e01e5a",
        "critical": "#611f69",
    }.get(severity, "#36a64f")

    fields = [{"title": "event", "value": event, "short": True},
              {"title": "severity", "value": severity, "short": True}]
    if trace_id:
        fields.append({"title": "oracleApmTraceId", "value": trace_id, "short": False})
    if extra:
        for k, v in list(extra.items())[:10]:
            if k == "oracleApmTraceId":
                continue
            fields.append({"title": k, "value": str(v)[:200], "short": True})

    payload: Dict[str, Any] = {
        "text": message,
        "attachments": [
            {
                "color": colour,
                "text": message,
                "fields": fields,
                "footer": "enterprise-crm-portal",
                "mrkdwn_in": ["text"],
            }
        ],
    }
    channel = _channel_override()
    if channel:
        payload["channel"] = channel

    try:
        import httpx

        webhook = os.environ["SLACK_WEBHOOK_URL"]
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(webhook, json=payload)
    except Exception as exc:  # pragma: no cover — must never raise
        logger.debug("slack_notify failed silently (event=%s): %s", event, exc)


def notify_sync(
    event: str, message: str, *, severity: str = "info", extra: Optional[Dict[str, Any]] = None
) -> None:
    """Sync wrapper for use from threadpool / non-async callers."""
    if not _enabled():
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(notify(event, message, severity=severity, extra=extra))
            return
    except RuntimeError:
        pass
    try:
        asyncio.run(notify(event, message, severity=severity, extra=extra))
    except Exception as exc:  # pragma: no cover
        logger.debug("slack_notify_sync failed: %s", exc)
