"""unique url/ticker+direction, nullable analysis_results.triggered_price

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-01
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_watch_items_url", "watch_items", ["url"])
    op.create_unique_constraint(
        "uq_stock_alerts_ticker_direction", "stock_alerts", ["ticker", "direction"]
    )
    # manual trigger (POST /api/stocks/{id}/analyze) has no live price fetch — uses
    # alert.last_price, which can be null for an alert that's never fired
    op.alter_column("analysis_results", "triggered_price", nullable=True)


def downgrade() -> None:
    op.alter_column("analysis_results", "triggered_price", nullable=False)
    op.drop_constraint("uq_stock_alerts_ticker_direction", "stock_alerts", type_="unique")
    op.drop_constraint("uq_watch_items_url", "watch_items", type_="unique")
