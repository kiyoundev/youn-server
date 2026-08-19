"""product-level active, drop per-listing active (issue #48)

Consolidates pause/resume to a single `products.active` column. The only
control surface that ever wrote `watch_items.active` (the watchlist page's
pause Switch) always wrote every listing under a product in lockstep, so the
independent per-listing granularity the old column allowed was never
actually exercised by any UI path — confirmed lossless via a direct query
against production data before writing this migration:

    SELECT product_id, count(*) FILTER (WHERE active) AS active_count, count(*) AS total_count
    FROM watch_items
    GROUP BY product_id
    HAVING count(*) FILTER (WHERE active) NOT IN (0, count(*));

(returned zero rows — every product today is already fully-active or
fully-inactive under the old per-listing model).

Not split into expand/contract across two deploys (unlike #24's 0009/0011
precedent) — the backfill was confirmed lossless ahead of time and this is a
solo-maintained project with no rolling-deploy constraint.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # Backfill: a product is active iff it has at least one currently-active
    # listing — matches compute_status's pre-migration "all listings inactive
    # -> paused" rule exactly.
    op.execute(
        """
        UPDATE products SET active = false
        WHERE id NOT IN (SELECT DISTINCT product_id FROM watch_items WHERE active = true)
        """
    )
    op.drop_column("watch_items", "active")


def downgrade() -> None:
    # Best-effort only — the per-listing granularity this drops can't be
    # reconstructed; every listing comes back active=true regardless of what
    # it was before the drop, except listings under a now-inactive product,
    # which come back active=false to match their parent (the strongest
    # guarantee downgrade can offer once that granularity is gone).
    op.add_column(
        "watch_items",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(
        """
        UPDATE watch_items SET active = false
        WHERE product_id IN (SELECT id FROM products WHERE active = false)
        """
    )
    op.drop_column("products", "active")
