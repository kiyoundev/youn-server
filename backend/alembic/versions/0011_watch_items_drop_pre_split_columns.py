"""product/listing split (issue #24) — Migration B (contract)

Drops the columns Migration A (0009) deliberately left behind on
watch_items — name, target_price, alerted_at — now that all three live on
products instead and the app has been verified against the new model.

Both products and watch_items are empty at the time this migration was
written (confirmed directly), so there's no data to lose. Every insert into
watch_items has been failing on name's NOT NULL constraint since 0009
shipped, since the current Listing ORM model never sets it.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("watch_items", "name")
    op.drop_column("watch_items", "target_price")
    op.drop_column("watch_items", "alerted_at")


def downgrade() -> None:
    # Best-effort only — original NOT NULL constraints and any data can't be
    # restored on rollback, since the whole point of this migration is that
    # those columns were already dead by the time it ran.
    op.add_column("watch_items", sa.Column("name", sa.String(), nullable=True))
    op.add_column("watch_items", sa.Column("target_price", sa.Float(), nullable=True))
    op.add_column(
        "watch_items", sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True)
    )
