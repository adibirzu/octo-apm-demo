"""KG-022 — index on orders.payment_provider_reference for O(1) webhook lookup.

Revision ID: a1paymentref
Revises: None (baseline)
Create Date: 2026-04-23

Webhook path looks up Orders by `payment_provider_reference`. Without
this index, every webhook is a full table scan on ATP.
"""

from __future__ import annotations

from alembic import op

revision = "a1paymentref"
down_revision = "a0paymentprovidercols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_orders_payment_provider_reference",
        "orders",
        ["payment_provider_reference"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_payment_provider_reference", table_name="orders")
