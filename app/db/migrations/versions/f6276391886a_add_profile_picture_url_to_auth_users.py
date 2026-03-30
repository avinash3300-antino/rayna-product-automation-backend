"""add profile_picture_url to auth_users

Revision ID: f6276391886a
Revises: 84d7354d60b9
Create Date: 2026-03-30 12:03:10.373896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6276391886a'
down_revision: Union[str, None] = '84d7354d60b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('auth_users', sa.Column('profile_picture_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('auth_users', 'profile_picture_url')
