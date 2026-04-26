"""Add enriched_reviewer_name to product_reviews

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j1k2l3m4n5o6"
down_revision: str = "i0j1k2l3m4n5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF NOT EXISTS so this is safe on DBs where the column was added manually
    op.execute(
        "ALTER TABLE product_reviews ADD COLUMN IF NOT EXISTS enriched_reviewer_name VARCHAR(255)"
    )


def downgrade() -> None:
    op.drop_column("product_reviews", "enriched_reviewer_name")
