"""add auth_user_sessions table

Revision ID: 0fd671a52791
Revises: f6276391886a
Create Date: 2026-03-30 12:43:01.143451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fd671a52791'
down_revision: Union[str, None] = 'f6276391886a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('auth_user_sessions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('device', sa.String(length=255), nullable=True),
    sa.Column('browser', sa.String(length=255), nullable=True),
    sa.Column('os', sa.String(length=255), nullable=True),
    sa.Column('user_agent_raw', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['auth_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_user_sessions_user_id'), 'auth_user_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_auth_user_sessions_user_id'), table_name='auth_user_sessions')
    op.drop_table('auth_user_sessions')
