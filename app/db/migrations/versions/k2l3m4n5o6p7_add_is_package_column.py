"""Add is_package column to activities

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-05-04

"""

from alembic import op
import sqlalchemy as sa

revision = "k2l3m4n5o6p7"
down_revision = "j1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("is_package", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_activities_is_package", "activities", ["is_package"])


def downgrade() -> None:
    op.drop_index("ix_activities_is_package", table_name="activities")
    op.drop_column("activities", "is_package")
