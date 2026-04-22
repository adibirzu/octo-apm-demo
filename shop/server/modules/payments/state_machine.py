"""Order state machine.

Keeps payment-driven transitions legal; refuses shortcuts.

    pending ──► payment_pending ──► paid ──► refunded
        │            │
        │            └──► failed
        │            └──► cancelled
        └──► cancelled

Any transition not listed above raises :class:`IllegalTransition`.
Terminal states (paid/failed/cancelled/refunded) are sinks — the only
exception is ``paid → refunded`` which enables post-settlement refunds.
"""

from __future__ import annotations

import enum
from typing import FrozenSet


class OrderState(str, enum.Enum):
    PENDING = "pending"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class IllegalTransition(ValueError):
    """Raised on ``transition(old, new)`` when the edge is not allowed."""


_LEGAL_TRANSITIONS: dict[OrderState, FrozenSet[OrderState]] = {
    OrderState.PENDING: frozenset({
        OrderState.PAYMENT_PENDING,
        OrderState.CANCELLED,
    }),
    OrderState.PAYMENT_PENDING: frozenset({
        OrderState.PAID,
        OrderState.FAILED,
        OrderState.CANCELLED,
    }),
    OrderState.PAID: frozenset({OrderState.REFUNDED}),
    OrderState.FAILED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REFUNDED: frozenset(),
}


def transition(current: OrderState, target: OrderState) -> OrderState:
    """Return ``target`` if the edge ``current → target`` is legal.

    Self-transitions (``target == current``) are treated as no-ops and
    return ``current`` without raising — handy for idempotent webhook
    retries that deliver the same event twice.
    """
    if target == current:
        return current
    legal = _LEGAL_TRANSITIONS[current]
    if target not in legal:
        raise IllegalTransition(
            f"cannot transition order from {current.value} to {target.value} "
            f"(legal next: {[s.value for s in legal] or 'terminal'})"
        )
    return target


def is_terminal(state: OrderState) -> bool:
    """True if ``state`` has no outgoing edges."""
    return not _LEGAL_TRANSITIONS[state]
