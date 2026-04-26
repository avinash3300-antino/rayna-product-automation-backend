"""Add scraped pricing columns to activities

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-04-24 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision: str = "i0j1k2l3m4n5"
down_revision: str = "h9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF NOT EXISTS so this is safe on DBs where columns were added manually
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS scraped_prices JSON")
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS local_currency VARCHAR(3)")
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS price_local NUMERIC(10, 2)")


def downgrade() -> None:
    op.drop_column("activities", "price_local")
    op.drop_column("activities", "local_currency")
    op.drop_column("activities", "scraped_prices")
