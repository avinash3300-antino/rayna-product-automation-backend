"""Add tour_variants JSON column to activities

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-05-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "m4n5o6p7q8r9"
down_revision = "l3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("tour_variants", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "tour_variants")
