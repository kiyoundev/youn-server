"""fx_rate_history table (issue #74)

One row per (currency, date) ever resolved for a past USD->CAD lookup,
additive alongside fx_rates (which stays the single upserted-in-place row
per currency used for the live rate). No fetched_at - a historical rate is
either known or it isn't, never "stale" the way the live rate can be.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fx_rate_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rate_to_cad", sa.Float(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_fx_rate_history_currency_date", "fx_rate_history", ["currency", "date"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_fx_rate_history_currency_date", "fx_rate_history", type_="unique")
    op.drop_table("fx_rate_history")
