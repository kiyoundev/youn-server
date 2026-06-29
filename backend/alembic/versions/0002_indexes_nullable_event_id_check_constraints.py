"""indexes, nullable event_id, check constraints

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FK indexes — PostgreSQL does not auto-index FK columns
    op.create_index("ix_price_history_watch_item_id", "price_history", ["watch_item_id"])
    op.create_index("ix_price_history_checked_at", "price_history", ["watch_item_id", "checked_at"])
    op.create_index("ix_analysis_results_stock_alert_id", "analysis_results", ["stock_alert_id"])
    op.create_index("ix_analysis_results_event_id", "analysis_results", ["event_id"])

    # event_id nullable — manual trigger (POST /api/stocks/{id}/analyze) has no triggering event
    op.alter_column("analysis_results", "event_id", nullable=True)

    # Check constraints — catch invalid status/type values at DB level
    op.create_check_constraint(
        "ck_events_status",
        "events",
        "status IN ('pending', 'processed', 'failed')",
    )
    op.create_check_constraint(
        "ck_events_type",
        "events",
        "type IN ('PRICE_DROP', 'STOCK_THRESHOLD')",
    )
    op.create_check_constraint(
        "ck_analysis_results_status",
        "analysis_results",
        "status IN ('pending', 'running', 'done', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_analysis_results_status", "analysis_results")
    op.drop_constraint("ck_events_type", "events")
    op.drop_constraint("ck_events_status", "events")

    op.alter_column("analysis_results", "event_id", nullable=False)

    op.drop_index("ix_analysis_results_event_id")
    op.drop_index("ix_analysis_results_stock_alert_id")
    op.drop_index("ix_price_history_checked_at")
    op.drop_index("ix_price_history_watch_item_id")
