"""Order-state-machine transitions.

The shop's Order has historically been a single "status" string. Phase 2
tightens it into an explicit state machine so payment webhooks can only
drive legal transitions:

    pending ──► payment_pending ──► paid
                                  ╲
                                   └► failed

Direct jumps (pending → paid, paid → failed) are rejected.
``refund`` + ``cancel`` are terminal-branch transitions; they may only
fire from ``paid`` and ``payment_pending`` respectively.
"""

from __future__ import annotations

import pytest

from server.modules.payments.state_machine import (
    IllegalTransition,
    OrderState,
    transition,
)


def test_happy_path_pending_to_paid() -> None:
    assert transition(OrderState.PENDING, OrderState.PAYMENT_PENDING) == OrderState.PAYMENT_PENDING
    assert transition(OrderState.PAYMENT_PENDING, OrderState.PAID) == OrderState.PAID


def test_payment_failed_branch() -> None:
    assert transition(OrderState.PENDING, OrderState.PAYMENT_PENDING) == OrderState.PAYMENT_PENDING
    assert transition(OrderState.PAYMENT_PENDING, OrderState.FAILED) == OrderState.FAILED


def test_refund_only_from_paid() -> None:
    assert transition(OrderState.PAID, OrderState.REFUNDED) == OrderState.REFUNDED
    with pytest.raises(IllegalTransition):
        transition(OrderState.PAYMENT_PENDING, OrderState.REFUNDED)


def test_cancel_only_from_pending_or_payment_pending() -> None:
    assert transition(OrderState.PENDING, OrderState.CANCELLED) == OrderState.CANCELLED
    assert transition(OrderState.PAYMENT_PENDING, OrderState.CANCELLED) == OrderState.CANCELLED
    with pytest.raises(IllegalTransition):
        transition(OrderState.PAID, OrderState.CANCELLED)


def test_terminal_states_reject_all_transitions() -> None:
    for terminal in (OrderState.PAID, OrderState.FAILED, OrderState.CANCELLED, OrderState.REFUNDED):
        for target in OrderState:
            if target == terminal:
                continue  # self-transition is no-op
            if terminal == OrderState.PAID and target == OrderState.REFUNDED:
                continue  # paid → refunded is legal, asserted above
            with pytest.raises(IllegalTransition):
                transition(terminal, target)


def test_direct_pending_to_paid_rejected() -> None:
    """Guards against a bug where a webhook handler forgets to set
    payment_pending first."""
    with pytest.raises(IllegalTransition):
        transition(OrderState.PENDING, OrderState.PAID)
