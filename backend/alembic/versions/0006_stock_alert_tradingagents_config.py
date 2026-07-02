"""per-alert TradingAgents config on stock_alerts; report_path replaces stop_loss

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_alerts", sa.Column("deep_think_llm", sa.String(), nullable=True))
    op.add_column("stock_alerts", sa.Column("quick_think_llm", sa.String(), nullable=True))
    op.add_column("stock_alerts", sa.Column("anthropic_effort", sa.String(), nullable=True))
    op.add_column("stock_alerts", sa.Column("max_debate_rounds", sa.Integer(), nullable=True))
    op.add_column(
        "stock_alerts", sa.Column("max_risk_discuss_rounds", sa.Integer(), nullable=True)
    )
    op.add_column("stock_alerts", sa.Column("analysts", sa.String(), nullable=True))

    op.add_column("analysis_results", sa.Column("report_path", sa.String(), nullable=True))
    op.drop_column("analysis_results", "stop_loss")


def downgrade() -> None:
    op.add_column("analysis_results", sa.Column("stop_loss", sa.Float(), nullable=True))
    op.drop_column("analysis_results", "report_path")

    op.drop_column("stock_alerts", "analysts")
    op.drop_column("stock_alerts", "max_risk_discuss_rounds")
    op.drop_column("stock_alerts", "max_debate_rounds")
    op.drop_column("stock_alerts", "anthropic_effort")
    op.drop_column("stock_alerts", "quick_think_llm")
    op.drop_column("stock_alerts", "deep_think_llm")
