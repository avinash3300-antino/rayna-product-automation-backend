"""Add pgvector extension and activity_embeddings table

Revision ID: e6f7g8h9i0j1
Revises: d5e6f7g8h9i0
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "e6f7g8h9i0j1"
down_revision: Union[str, None] = "d5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create activity_embeddings table
    op.create_table(
        "activity_embeddings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "activity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 3. Create index for fast cosine similarity search
    op.execute(
        "CREATE INDEX ix_activity_embeddings_cosine "
        "ON activity_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_activity_embeddings_cosine", table_name="activity_embeddings")
    op.drop_table("activity_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
