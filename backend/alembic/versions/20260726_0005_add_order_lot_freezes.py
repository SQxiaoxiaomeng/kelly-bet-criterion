"""add order lot freezes

Revision ID: 20260726_0005
Revises: 20260726_0004
Create Date: 2026-07-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0005"
down_revision: str | None = "20260726_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_lot_freezes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("sim_orders.id"), nullable=False),
        sa.Column("position_lot_id", sa.String(length=36), sa.ForeignKey("position_lots.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_lot_freezes")
