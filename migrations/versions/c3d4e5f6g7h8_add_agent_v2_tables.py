"""add_agent_v2_tables

Revision ID: c3d4e5f6g7h8
Revises: b3c4d5e6f7g8
Create Date: 2025-12-14 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -------------------------------------------------------------------------
    # 0. Add api_version column to sessions table
    # -------------------------------------------------------------------------
    op.add_column(
        "sessions",
        sa.Column("api_version", sa.String(10), nullable=False, server_default="v0"),if_not_exists=True
    )

    # -------------------------------------------------------------------------
    # 1. Add error_message column to agent_run_tasks table
    # -------------------------------------------------------------------------
    op.add_column(
        "agent_run_tasks",
        sa.Column("error_message", sa.Text(), nullable=True),
        if_not_exists=True
    )

    # -------------------------------------------------------------------------
    # 2. Create agent_run_messages table
    # -------------------------------------------------------------------------
    op.create_table(
        "agent_run_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("run_input", postgresql.JSONB(), nullable=True),
        sa.Column("messages", postgresql.JSONB(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("additional_info", postgresql.JSONB(), nullable=True),
        sa.Column("tools", postgresql.JSONB(), nullable=True),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_messages"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_agent_run_messages_session_id",
            ondelete="CASCADE",
        ),
        if_not_exists=True
    )

    # Indexes for agent_run_messages
    op.create_index(
        "ix_agent_run_messages_session_id",
        "agent_run_messages",
        ["session_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_messages_run_id",
        "agent_run_messages",
        ["run_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_messages_session_run",
        "agent_run_messages",
        ["session_id", "run_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_messages_created_at",
        "agent_run_messages",
        ["created_at"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_messages_status",
        "agent_run_messages",
        ["status"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_messages_parent_run_id",
        "agent_run_messages",
        ["parent_run_id"],
        if_not_exists=True
    )

    # -------------------------------------------------------------------------
    # 3. Create agent_run_events table
    # -------------------------------------------------------------------------
    op.create_table(
        "agent_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_events"),
        if_not_exists=True
    )

    # Indexes for agent_run_events
    op.create_index(
        "ix_agent_run_events_session_id",
        "agent_run_events",
        ["session_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_events_run_id",
        "agent_run_events",
        ["run_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_events_session_run",
        "agent_run_events",
        ["session_id", "run_id"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_events_name",
        "agent_run_events",
        ["name"],
        if_not_exists=True
    )
    op.create_index(
        "ix_agent_run_events_created_at",
        "agent_run_events",
        ["created_at"],
        if_not_exists=True
    )

    # -------------------------------------------------------------------------
    # 3. Create sandboxes table
    # -------------------------------------------------------------------------
    op.create_table(
        "sandboxes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="e2b"),
        sa.Column("provider_sandbox_id", sa.String(), nullable=True),
        sa.Column("provider_data", postgresql.JSONB(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="not_initialized"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sandboxes"),
        sa.UniqueConstraint("session_id", name="uq_sandboxes_session_id"),
        if_not_exists=True
        )

    # Indexes for sandboxes
    op.create_index(
        "idx_sandboxes_status",
        "sandboxes",
        ["status"],
        if_not_exists=True
    )
    op.create_index(
        "idx_sandboxes_provider_sandbox_id",
        "sandboxes",
        ["provider_sandbox_id"],
        if_not_exists=True
    )
    op.create_index(
        "idx_sandboxes_session_id",
        "sandboxes",
        ["session_id"],
        if_not_exists=True
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Drop sandboxes table and indexes
    op.drop_index("idx_sandboxes_session_id", table_name="sandboxes")
    op.drop_index("idx_sandboxes_provider_sandbox_id", table_name="sandboxes")
    op.drop_index("idx_sandboxes_status", table_name="sandboxes")
    op.drop_table("sandboxes")

    # Drop agent_run_events table and indexes
    op.drop_index("ix_agent_run_events_created_at", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_name", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_session_run", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_run_id", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_session_id", table_name="agent_run_events")
    op.drop_table("agent_run_events")

    # Drop agent_run_messages table and indexes
    op.drop_index("ix_agent_run_messages_parent_run_id", table_name="agent_run_messages")
    op.drop_index("ix_agent_run_messages_status", table_name="agent_run_messages")
    op.drop_index("ix_agent_run_messages_created_at", table_name="agent_run_messages")
    op.drop_index("ix_agent_run_messages_session_run", table_name="agent_run_messages")
    op.drop_index("ix_agent_run_messages_run_id", table_name="agent_run_messages")
    op.drop_index("ix_agent_run_messages_session_id", table_name="agent_run_messages")
    op.drop_table("agent_run_messages")

    # Drop error_message column from agent_run_tasks
    op.drop_column("agent_run_tasks", "error_message")

    # Drop api_version column from sessions
    op.drop_column("sessions", "api_version")
