"""Add payment_provider + payment_provider_reference columns to orders.

Revision ID: a0paymentprovidercols
Revises: None
Create Date: 2026-04-20

Webhook path (server/modules/payments/webhooks.py) looks up orders by
``payment_provider_reference``. The column was referenced in application
code + the subsequent index migration (a1paymentref) without being
added first, which would have broken a cold ATP bootstrap. This
migration closes the gap.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a0paymentprovidercols"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("payment_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("payment_provider_reference", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_provider_reference")
    op.drop_column("orders", "payment_provider")
