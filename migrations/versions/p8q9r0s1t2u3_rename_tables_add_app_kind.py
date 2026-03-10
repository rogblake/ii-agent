"""Rename tables to explicit domain prefixes, add app_kind, drop dead columns.

Chat tables:
- conversation_summaries -> chat_summaries
- provider_containers -> chat_provider_containers
- provider_files -> chat_provider_files
- provider_vector_stores -> chat_provider_vector_stores

Agent tables:
- events -> agent_events
- sandboxes -> agent_sandboxes
- session_summaries -> agent_summaries
- agent_run_events -> agent_event_log

Sessions:
- Add app_kind column (backfill from agent_type)
- Drop dead columns: prompt_tokens, completion_tokens, cost, summary_message_id

Revision ID: p8q9r0s1t2u3
Revises: o7p8q9r0s1t2
Create Date: 2026-03-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "p8q9r0s1t2u3"
down_revision: Union[str, None] = "o7p8q9r0s1t2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== Chat table renames ====================
    op.rename_table("conversation_summaries", "chat_summaries")
    op.rename_table("provider_containers", "chat_provider_containers")
    op.rename_table("provider_files", "chat_provider_files")
    op.rename_table("provider_vector_stores", "chat_provider_vector_stores")

    # ==================== Agent table renames ====================
    op.rename_table("events", "agent_events")
    op.rename_table("sandboxes", "agent_sandboxes")
    op.rename_table("session_summaries", "agent_summaries")
    op.rename_table("agent_run_events", "agent_event_log")

    # ==================== Sessions: add app_kind ====================
    op.add_column(
        "sessions",
        sa.Column("app_kind", sa.String(), nullable=False, server_default="agent"),
    )
    op.execute("UPDATE sessions SET app_kind = 'chat' WHERE agent_type = 'chat'")
    op.create_index("idx_sessions_app_kind", "sessions", ["app_kind"])

    # ==================== Sessions: drop dead columns ====================
    op.drop_column("sessions", "prompt_tokens")
    op.drop_column("sessions", "completion_tokens")
    op.drop_column("sessions", "cost")
    op.drop_column("sessions", "summary_message_id")

    # ==================== Update self-referencing FK on chat_summaries ====================
    # The parent_summary_id FK pointed to conversation_summaries.id
    # PostgreSQL automatically updates this when the table is renamed, no action needed.


def downgrade() -> None:
    # ==================== Restore dead columns ====================
    op.add_column(
        "sessions",
        sa.Column("summary_message_id", sa.String(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("cost", sa.Float(), nullable=True, server_default="0"),
    )
    op.add_column(
        "sessions",
        sa.Column("completion_tokens", sa.BigInteger(), nullable=True, server_default="0"),
    )
    op.add_column(
        "sessions",
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=True, server_default="0"),
    )

    # ==================== Remove app_kind ====================
    op.drop_index("idx_sessions_app_kind", table_name="sessions")
    op.drop_column("sessions", "app_kind")

    # ==================== Reverse agent table renames ====================
    op.rename_table("agent_event_log", "agent_run_events")
    op.rename_table("agent_summaries", "session_summaries")
    op.rename_table("agent_sandboxes", "sandboxes")
    op.rename_table("agent_events", "events")

    # ==================== Reverse chat table renames ====================
    op.rename_table("chat_provider_vector_stores", "provider_vector_stores")
    op.rename_table("chat_provider_files", "provider_files")
    op.rename_table("chat_provider_containers", "provider_containers")
    op.rename_table("chat_summaries", "conversation_summaries")
