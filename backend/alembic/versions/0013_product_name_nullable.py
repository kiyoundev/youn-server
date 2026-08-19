"""product.name nullable (issue #44)

Product name becomes optional at creation — filled in from the first
successful scrape's inferred product_title if the user leaves it blank
(see process_item, jobs.py). Purely additive: existing rows already have
non-null names, so no backfill needed on upgrade().

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-19
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("products", "name", nullable=True)


def downgrade() -> None:
    # Best-effort only — any product left with name=NULL (never got a first
    # successful scrape, or the user never typed one) needs a real value
    # before the NOT NULL constraint can come back, or this raises.
    op.execute("UPDATE products SET name = 'Untitled' WHERE name IS NULL")
    op.alter_column("products", "name", nullable=False)
