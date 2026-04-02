"""Add session_summaries table for agent conversation summaries

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create session_summaries table with indexes."""
    # Create session_summaries table
    op.create_table(
        "session_summaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("topics", JSONB(), nullable=True),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_summaries"),
        if_not_exists=True,
    )

    # Create unique index on session_id for fast lookups and ensuring one summary per session
    op.create_index(
        "ix_session_summaries_session_id",
        "session_summaries",
        ["session_id"],
        unique=True,
        if_not_exists=True,
    )

    # Create composite index on (session_id, agent_run_id) for efficient queries
    op.create_index(
        "ix_session_summaries_session_id_agent_run_id",
        "session_summaries",
        ["session_id", "agent_run_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop session_summaries table and indexes."""
    op.drop_index(
        "ix_session_summaries_session_id_agent_run_id",
        table_name="session_summaries",
    )
    op.drop_index(
        "ix_session_summaries_session_id",
        table_name="session_summaries",
    )
    op.drop_table("session_summaries")
