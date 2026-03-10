"""Add chat_runs table and migrate chat data from agent_run_tasks.

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

    # 2. Backfill: copy agent_run_tasks rows for chat sessions into chat_runs
    op.execute(
        """
        INSERT INTO chat_runs (id, session_id, user_message_id, status, error_message, version, created_at, updated_at)
        SELECT art.id, art.session_id, art.user_message_id, art.status, art.error_message, art.version, art.created_at, art.updated_at
        FROM agent_run_tasks art
        JOIN sessions s ON s.id = art.session_id
        WHERE s.agent_type = 'chat'
        """
    )

    # 3. Delete the now-migrated rows from agent_run_tasks
    op.execute(
        """
        DELETE FROM agent_run_tasks
        WHERE session_id IN (SELECT id FROM sessions WHERE agent_type = 'chat')
        """
    )


def downgrade() -> None:
    # Move chat_runs data back to agent_run_tasks
    op.execute(
        """
        INSERT INTO agent_run_tasks (id, session_id, user_message_id, status, error_message, version, created_at, updated_at)
        SELECT id, session_id, user_message_id, status, error_message, version, created_at, updated_at
        FROM chat_runs
        """
    )

    op.drop_index("ix_chat_runs_session_status", table_name="chat_runs")
    op.drop_index("ix_chat_runs_status", table_name="chat_runs")
    op.drop_index("ix_chat_runs_session_id", table_name="chat_runs")
    op.drop_table("chat_runs")
