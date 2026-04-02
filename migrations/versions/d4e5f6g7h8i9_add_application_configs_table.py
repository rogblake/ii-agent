"""Add application_configs table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2025-01-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create application_configs table."""
    op.create_table(
        "application_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", JSONB(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_application_configs"),
        sa.UniqueConstraint("key", name="uq_application_configs_key"),
    )
    op.create_index(
        "idx_application_configs_is_secret",
        "application_configs",
        ["is_secret"],
    )

    # Seed initial agent v1 settings
    op.execute(
        """
        INSERT INTO application_configs (key, value, is_secret, version, created_at, updated_at)
        VALUES (
            'agent_v1_version_toggle',
            'false'::jsonb,
            false,
            0,
            NOW(),
            NOW()
        )
        """
    )


def downgrade() -> None:
    """Drop application_configs table."""
    op.drop_index("idx_application_configs_is_secret", table_name="application_configs")
    op.drop_table("application_configs")
