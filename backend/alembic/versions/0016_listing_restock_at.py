"""add restock_at to watch_items

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watch_items", sa.Column("restock_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("watch_items", "restock_at")
