"""activities table (issue #33)

Durable ledger of Wealthsimple activity-export rows. No unique
constraint — the CSV carries no row id, and two legitimate rows can be
identical apart from description (same-day $0.01 interest postings).
Holdings/average cost/cash are derived on read (services/positions.py),
never stored — there is no Position table.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("activity_sub_type", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("fx_rate", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=False, server_default="0"),
        sa.Column("net_cash_amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activities_account_effective_at", "activities", ["account_id", "effective_at"])


def downgrade() -> None:
    op.drop_index("ix_activities_account_effective_at", table_name="activities")
    op.drop_table("activities")
