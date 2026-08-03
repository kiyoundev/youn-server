"""add ondelete=CASCADE to watch_items.product_id FK (issue #24 review follow-up)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-03
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_watch_items_product_id_products", "watch_items", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_watch_items_product_id_products",
        "watch_items",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_watch_items_product_id_products", "watch_items", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_watch_items_product_id_products",
        "watch_items",
        "products",
        ["product_id"],
        ["id"],
    )
