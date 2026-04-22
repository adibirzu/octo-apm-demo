"""Webhook ingestion route — one endpoint per provider.

The provider is the source-of-truth for the payment event; we verify
signature, classify the event, then drive the order state machine.

Returns:
    200 — event was valid (duplicate deliveries short-circuit legally)
    400 — invalid signature (provider will retry; that's fine)
    404 — order referenced by provider_reference is unknown

Design decisions:
- We do NOT 500 on internal failures — the provider retries on 5xx
  and that just amplifies transient problems. 200 after best-effort
  side effects is the right shape.
- Signature verification happens BEFORE any DB lookup. A forged
  payload should never touch the database.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status
from opentelemetry import trace

from .base import InvalidSignature, PaymentEventKind
from .events import emit_order_state_change
from .state_machine import IllegalTransition, OrderState, transition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments/webhooks", tags=["payments"])


def _event_kind_to_target_state(kind: PaymentEventKind) -> OrderState | None:
    return {
        PaymentEventKind.SUCCEEDED: OrderState.PAID,
        PaymentEventKind.FAILED: OrderState.FAILED,
        PaymentEventKind.CANCELLED: OrderState.CANCELLED,
        PaymentEventKind.REFUNDED: OrderState.REFUNDED,
        PaymentEventKind.PENDING: None,  # informational — no state change
    }.get(kind)


@router.post("/{provider_name}")
async def receive_webhook(provider_name: str, request: Request) -> Response:
    from server.modules.payments.registry import get_provider  # lazy — avoids circular

    provider = get_provider(provider_name)
    if provider is None:
        return Response(
            content=f'{{"error":"unknown provider: {provider_name}"}}',
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            media_type="application/json",
        )

    body = await request.body()
    try:
        event = provider.verify_webhook(body=body, headers=dict(request.headers))
    except InvalidSignature as exc:
        logger.warning("webhook.invalid_signature", extra={"provider": provider_name, "error": str(exc)})
        return Response(
            content='{"error":"invalid signature"}',
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    target = _event_kind_to_target_state(event.kind)
    if target is None:
        # Informational event (e.g. payment_intent.processing) — ack.
        return Response(status_code=status.HTTP_200_OK)

    span = trace.get_current_span()
    trace_id_hex = ""
    if span is not None and span.get_span_context().trace_id:
        trace_id_hex = format(span.get_span_context().trace_id, "032x")

    # Order lookup + state transition
    from server.database import Order, get_db
    async with get_db() as db:
        order = await _find_order_by_provider_reference(db, provider.name, event.provider_reference)
        if order is None:
            logger.info(
                "webhook.unknown_order",
                extra={"provider": provider.name, "ref": event.provider_reference},
            )
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        current = OrderState(order.status) if order.status in OrderState.__members__.values() else OrderState.PENDING
        try:
            new_state = transition(current, target)
        except IllegalTransition as exc:
            logger.warning(
                "webhook.illegal_transition",
                extra={"order_id": order.id, "from": current.value, "to": target.value, "error": str(exc)},
            )
            # Provider delivered an event that doesn't apply — ack anyway
            # so they stop retrying.
            return Response(status_code=status.HTTP_200_OK)

        if new_state != current:
            order.status = new_state.value
            await db.commit()
            emit_order_state_change(
                order_id=order.id,
                previous_state=current,
                new_state=new_state,
                amount_minor_units=event.amount_minor_units,
                currency=event.currency,
                provider=provider.name,
                provider_reference=event.provider_reference,
                trace_id=trace_id_hex,
            )

    return Response(status_code=status.HTTP_200_OK)


async def _find_order_by_provider_reference(db, provider: str, ref: str):
    """Locate an Order whose ``payment_provider_reference`` matches ``ref``.

    Reference lookup lives in the Order model; we expect an index on
    ``payment_provider_reference`` in production for O(1) webhook
    handling.
    """
    from sqlalchemy import select
    from server.database import Order

    result = await db.execute(
        select(Order).where(Order.payment_provider_reference == ref)
    )
    return result.scalar_one_or_none()
