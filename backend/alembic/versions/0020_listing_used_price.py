"""add used_price to watch_items (issue #60)

A nullable, informational price: the used offer an Amazon listing shows
while its new offer is sold out. Never a tracked price — nothing reads it
for charts, alerts or comparisons.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watch_items", sa.Column("used_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("watch_items", "used_price")
