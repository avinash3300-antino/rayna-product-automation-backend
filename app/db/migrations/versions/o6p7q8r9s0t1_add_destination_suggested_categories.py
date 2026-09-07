"""Add destination_suggested_categories table

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-06-10

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "o6p7q8r9s0t1"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "destination_suggested_categories",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "destination_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog_destinations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("auth_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dest_categories_lookup",
        "destination_suggested_categories",
        ["destination_id", "product_type", "deleted_at"],
    )
    op.create_index(
        "uq_dest_categories_active_name",
        "destination_suggested_categories",
        ["destination_id", "product_type", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_dest_categories_active_name",
        table_name="destination_suggested_categories",
    )
    op.drop_index(
        "ix_dest_categories_lookup",
        table_name="destination_suggested_categories",
    )
    op.drop_table("destination_suggested_categories")
