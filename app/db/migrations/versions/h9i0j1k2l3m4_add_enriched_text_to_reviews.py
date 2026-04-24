"""Add enriched_text to product_reviews

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h9i0j1k2l3m4"
down_revision: str = "g8h9i0j1k2l3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_reviews", sa.Column("enriched_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_reviews", "enriched_text")
