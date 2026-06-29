"""add scraper_type to watch_items

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watch_items", sa.Column("scraper_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("watch_items", "scraper_type")
