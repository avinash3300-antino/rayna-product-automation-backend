"""add country_name country_flag enabled_categories to catalog_destinations

Revision ID: a1b2c3d4e5f6
Revises: 0fd671a52791
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0fd671a52791'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('catalog_destinations', sa.Column('country_name', sa.String(), nullable=True))
    op.add_column('catalog_destinations', sa.Column('country_flag', sa.String(), nullable=True))
    op.add_column('catalog_destinations', sa.Column('enabled_categories', JSON(), server_default='["hotels","attractions","transfers","restaurants"]', nullable=True))


def downgrade() -> None:
    op.drop_column('catalog_destinations', 'enabled_categories')
    op.drop_column('catalog_destinations', 'country_flag')
    op.drop_column('catalog_destinations', 'country_name')
