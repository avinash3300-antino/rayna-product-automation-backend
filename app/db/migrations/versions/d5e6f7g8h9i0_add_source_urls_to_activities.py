"""Add source_urls JSON column to activities

Revision ID: d5e6f7g8h9i0
Revises: c4d5e6f7g8h9
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "d5e6f7g8h9i0"
down_revision: Union[str, None] = "c4d5e6f7g8h9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable JSON column — existing rows get NULL (safe)
    op.add_column(
        "activities",
        sa.Column("source_urls", JSON, nullable=True),
    )
    # Backfill: set source_urls = [source_url] for all existing rows
    op.execute(
        "UPDATE activities SET source_urls = json_build_array(source_url) "
        "WHERE source_urls IS NULL"
    )


def downgrade() -> None:
    op.drop_column("activities", "source_urls")
