"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("retailer", sa.String(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "stock_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("run_analysis", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "watch_item_id",
            sa.Integer(),
            sa.ForeignKey("watch_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_alert_id",
            sa.Integer(),
            sa.ForeignKey("stock_alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("triggered_price", sa.Float(), nullable=False),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("price_target", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("price_history")
    op.drop_table("events")
    op.drop_table("stock_alerts")
    op.drop_table("watch_items")
