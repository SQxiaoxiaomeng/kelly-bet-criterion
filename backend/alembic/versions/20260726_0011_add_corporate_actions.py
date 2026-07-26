"""add corporate actions

Revision ID: 20260726_0011
Revises: 20260726_0010
Create Date: 2026-07-26 00:11:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0011"
down_revision: str | None = "20260726_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("cash_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("instrument_id", "action_type", "ex_date", "source", name="uq_corporate_action_source"),
    )
    op.create_table(
        "corporate_action_applications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("sim_accounts.id"), nullable=False),
        sa.Column("corporate_action_id", sa.String(length=36), sa.ForeignKey("corporate_actions.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "corporate_action_id", name="uq_action_application"),
    )


def downgrade() -> None:
    op.drop_table("corporate_action_applications")
    op.drop_table("corporate_actions")
