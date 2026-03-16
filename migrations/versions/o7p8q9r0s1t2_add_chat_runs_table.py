"""Add chat_runs table and backfill from agent_run_tasks.

Phase 1 of expand-contract migration: creates chat_runs and copies
chat-session rows from agent_run_tasks.  The originals are kept in
agent_run_tasks so that existing readers (session endpoints) continue
to work.  A future migration will delete them once all readers have
been migrated to use chat_runs.

Revision ID: o7p8q9r0s1t2
Revises: n6o7p8q9r0s1
Create Date: 2026-03-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "o7p8q9r0s1t2"
down_revision: Union[str, None] = "n6o7p8q9r0s1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create chat_runs table
    op.create_table(
        "chat_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_runs_session_id", "chat_runs", ["session_id"])
    op.create_index("ix_chat_runs_status", "chat_runs", ["status"])
    op.create_index(
        "ix_chat_runs_session_status", "chat_runs", ["session_id", "status"]
    )

    # 2. Backfill: copy agent_run_tasks rows for chat sessions into chat_runs.
    #    Originals are intentionally kept in agent_run_tasks (expand phase).
    op.execute(
        """
        INSERT INTO chat_runs (id, session_id, user_message_id, status, error_message, version, created_at, updated_at)
        SELECT art.id, art.session_id, art.user_message_id, art.status, art.error_message, art.version, art.created_at, art.updated_at
        FROM agent_run_tasks art
        JOIN sessions s ON s.id = art.session_id
        WHERE s.agent_type = 'chat'
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Originals still exist in agent_run_tasks — just drop the copy.
    op.drop_index("ix_chat_runs_session_status", table_name="chat_runs")
    op.drop_index("ix_chat_runs_status", table_name="chat_runs")
    op.drop_index("ix_chat_runs_session_id", table_name="chat_runs")
    op.drop_table("chat_runs")
