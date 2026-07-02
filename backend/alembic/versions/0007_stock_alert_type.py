"""alert_type on stock_alerts (buy_signal vs stop_loss)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_alerts",
        sa.Column(
            "alert_type", sa.String(), nullable=False, server_default="buy_signal"
        ),
    )
    op.drop_constraint("uq_stock_alerts_ticker_direction", "stock_alerts", type_="unique")
    op.create_unique_constraint(
        "uq_stock_alerts_ticker_direction_type",
        "stock_alerts",
        ["ticker", "direction", "alert_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_stock_alerts_ticker_direction_type", "stock_alerts", type_="unique"
    )
    op.create_unique_constraint(
        "uq_stock_alerts_ticker_direction", "stock_alerts", ["ticker", "direction"]
    )
    op.drop_column("stock_alerts", "alert_type")
