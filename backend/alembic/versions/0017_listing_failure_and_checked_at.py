"""add last_scrape_error, last_checked_at to watch_items

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watch_items", sa.Column("last_scrape_error", sa.String(), nullable=True))
    op.add_column("watch_items", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("watch_items", "last_checked_at")
    op.drop_column("watch_items", "last_scrape_error")
