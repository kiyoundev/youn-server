"""fx_rates table (issue #45)

Cached FX rates, one row per non-CAD currency this app supports (USD, KRW),
refreshed daily by refresh_fx_rates_job. currency is the primary key — a
single upserted row per currency, not a history table. CAD needs no row;
its rate is always 1.0, handled at the read layer.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(), primary_key=True),
        sa.Column("rate_to_cad", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fx_rates")
