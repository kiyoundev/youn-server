"""product/listing split (issue #24) — Migration A (expand only)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.add_column("watch_items", sa.Column("product_id", sa.Integer(), nullable=True))
    op.add_column(
        "watch_items", sa.Column("last_scrape_status", sa.String(), nullable=True)
    )

    # Backfill: every pre-existing watch_items row becomes a product-of-one,
    # reusing its own id as the new products.id. Safe to re-run: no-op if
    # products already has rows (only ever true on a partially-applied retry).
    op.execute(
        """
        INSERT INTO products (id, name, target_price, alerted_at, created_at)
        SELECT id, name, target_price, alerted_at, created_at FROM watch_items
        WHERE NOT EXISTS (SELECT 1 FROM products)
        """
    )
    op.execute("UPDATE watch_items SET product_id = id WHERE product_id IS NULL")

    # Advance the products id sequence past the reused values so new
    # INSERTs (via the ORM, which doesn't know about the backfill) don't
    # collide with the ids just reused from watch_items.
    op.execute(
        "SELECT setval('products_id_seq', COALESCE((SELECT MAX(id) FROM products), 1))"
    )

    op.alter_column("watch_items", "product_id", nullable=False)
    op.create_foreign_key(
        "fk_watch_items_product_id_products",
        "watch_items",
        "products",
        ["product_id"],
        ["id"],
    )

    # name, target_price, alerted_at columns on watch_items are left
    # untouched — no longer declared on the Listing ORM model, but still
    # physically present. Dropped in a later Migration B (separate issue),
    # once the app is fully verified against the new model.


def downgrade() -> None:
    op.drop_constraint(
        "fk_watch_items_product_id_products", "watch_items", type_="foreignkey"
    )
    op.drop_column("watch_items", "last_scrape_status")
    op.drop_column("watch_items", "product_id")
    op.drop_table("products")
