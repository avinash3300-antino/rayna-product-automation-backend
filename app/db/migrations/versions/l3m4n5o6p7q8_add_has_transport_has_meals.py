"""Add has_transport and has_meals columns to activities

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-05-04

"""

from alembic import op
import sqlalchemy as sa

revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("has_transport", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "activities",
        sa.Column("has_meals", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_activities_has_transport", "activities", ["has_transport"])
    op.create_index("ix_activities_has_meals", "activities", ["has_meals"])


def downgrade() -> None:
    op.drop_index("ix_activities_has_meals", table_name="activities")
    op.drop_index("ix_activities_has_transport", table_name="activities")
    op.drop_column("activities", "has_meals")
    op.drop_column("activities", "has_transport")
