"""events.type allows RESTOCK (issue #61)

Widens ck_events_type (created in 0002) so a RESTOCK event can be
inserted. A CHECK constraint can't be altered in place, so it is dropped
and recreated. The constraint exists only in migrations, not on the
Event model.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_events_type", "events", type_="check")
    op.create_check_constraint(
        "ck_events_type",
        "events",
        "type IN ('PRICE_DROP', 'STOCK_THRESHOLD', 'RESTOCK')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_events_type", "events", type_="check")
    op.create_check_constraint(
        "ck_events_type",
        "events",
        "type IN ('PRICE_DROP', 'STOCK_THRESHOLD')",
    )
