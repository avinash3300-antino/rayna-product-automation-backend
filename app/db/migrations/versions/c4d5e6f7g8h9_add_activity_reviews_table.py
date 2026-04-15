"""Add activity_reviews table

Revision ID: c4d5e6f7g8h9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-10
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "c4d5e6f7g8h9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "activity_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("reviewer_name", sa.String(200), nullable=False),
        sa.Column("reviewer_avatar_url", sa.String(500), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_title", sa.String(500), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=False),
        sa.Column("review_date", sa.String(100), nullable=True),
        sa.Column("source_platform", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column(
            "verified", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "language", sa.String(10), nullable=False, server_default="'en'"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("activity_reviews")
