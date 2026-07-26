"""add strategy version to backtest runs

Revision ID: 20260726_0008
Revises: 20260726_0007
Create Date: 2026-07-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0008"
down_revision: str | None = "20260726_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("strategy_version", sa.String(length=32), nullable=False, server_default="1.0.0"),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "strategy_version")
