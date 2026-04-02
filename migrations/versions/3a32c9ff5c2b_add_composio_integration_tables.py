"""Add Composio integration tables

Revision ID: 3a32c9ff5c2b
Revises: f1a2b3c4d5e6
Create Date: 2026-01-09 08:59:30.601831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3a32c9ff5c2b'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create composio_profiles table for Composio SDK integration
    op.create_table('composio_profiles',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('profile_name', sa.String(), nullable=False),
    sa.Column('toolkit_slug', sa.String(), nullable=False),
    sa.Column('toolkit_name', sa.String(), nullable=False),
    sa.Column('auth_config_id', sa.String(), nullable=False),
    sa.Column('connected_account_id', sa.String(), nullable=False),
    sa.Column('mcp_server_id', sa.String(), nullable=False),
    sa.Column('composio_user_id', sa.String(), nullable=False),
    sa.Column('encrypted_mcp_url', sa.String(), nullable=False),
    sa.Column('redirect_url', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False, server_default='pending'),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('enabled_tools', postgresql.JSONB(), nullable=False, server_default='[]'),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'profile_name', name='uq_composio_profile_name')
    )
    op.create_index(op.f('ix_composio_profiles_toolkit_slug'), 'composio_profiles', ['toolkit_slug'], unique=False)
    op.create_index(op.f('ix_composio_profiles_user_id'), 'composio_profiles', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop composio_profiles table
    op.drop_index(op.f('ix_composio_profiles_user_id'), table_name='composio_profiles')
    op.drop_index(op.f('ix_composio_profiles_toolkit_slug'), table_name='composio_profiles')
    op.drop_table('composio_profiles')
