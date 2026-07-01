"""partial unique index: at most one pending/running analysis per ticker

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-01
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_analysis_results_ticker_running",
        "analysis_results",
        ["ticker"],
        unique=True,
        postgresql_where="status IN ('pending', 'running')",
    )


def downgrade() -> None:
    op.drop_index("uq_analysis_results_ticker_running", table_name="analysis_results")
