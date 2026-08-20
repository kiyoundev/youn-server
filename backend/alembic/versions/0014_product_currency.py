"""product.currency (issue #45)

Nullable ISO 4217 code ("USD"/"CAD"/"KRW"), app-constrained at the Pydantic
layer only (no DB CHECK constraint — same looseness as other string-typed
fields in this codebase, e.g. Listing.retailer). NULL means "not yet
resolved" — same semantics as Product.name is None (#44): fill-only-if-null
from scrape inference, explicit user PATCH always overwrites. No backfill —
existing rows are sample/mock data, start NULL, resolve on next scrape.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("currency", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "currency")
