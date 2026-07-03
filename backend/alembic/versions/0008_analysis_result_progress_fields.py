"""progress + error_reason fields on analysis_results (issue #17)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_results",
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_results",
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_results",
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_results",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "analysis_results",
        sa.Column("error_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "error_reason")
    op.drop_column("analysis_results", "last_heartbeat_at")
    op.drop_column("analysis_results", "tool_calls")
    op.drop_column("analysis_results", "tokens_out")
    op.drop_column("analysis_results", "tokens_in")
    op.drop_column("analysis_results", "llm_calls")
