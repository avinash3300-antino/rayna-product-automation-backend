"""Add daily_availability JSON column to activities

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-05-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("daily_availability", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "daily_availability")
