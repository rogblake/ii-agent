"""Schema integrity: Numeric precision, FK constraints, chat_run columns.

- session_metrics.credits: Float → Numeric(18,6)
- billing_transactions.amount/credits: Float → Numeric(18,6)
- Add NOT VALID FK constraints on chat_messages, chat_provider_*, agent_*
- Validate all FK constraints
- Add telemetry columns to chat_runs

Revision ID: b001a1a1a1a1
Revises: l5m6n7o8p9q0
Create Date: 2026-03-16 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b001a1a1a1a1"
down_revision: Union[str, None] = "l5m6n7o8p9q0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Numeric precision ────────────────────────────────────────────
    op.alter_column(
        "session_metrics",
        "credits",
        existing_type=sa.Float(),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.alter_column(
        "billing_transactions",
        "amount",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=18, scale=6),
        existing_nullable=True,
    )
    op.alter_column(
        "billing_transactions",
        "credits",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=18, scale=6),
        existing_nullable=True,
    )

    # ── FK constraints (NOT VALID for zero-downtime) ─────────────────
    _fk_statements = [
        """ALTER TABLE chat_messages
           ADD CONSTRAINT fk_chat_messages_session
           FOREIGN KEY (session_id) REFERENCES sessions (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE chat_messages
           ADD CONSTRAINT fk_chat_messages_parent
           FOREIGN KEY (parent_message_id) REFERENCES chat_messages (id)
           ON DELETE SET NULL NOT VALID""",
        """ALTER TABLE chat_provider_containers
           ADD CONSTRAINT fk_chat_provider_containers_session
           FOREIGN KEY (session_id) REFERENCES sessions (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE chat_provider_files
           ADD CONSTRAINT fk_chat_provider_files_session
           FOREIGN KEY (session_id) REFERENCES sessions (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE chat_provider_files
           ADD CONSTRAINT fk_chat_provider_files_file
           FOREIGN KEY (file_id) REFERENCES file_uploads (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE chat_provider_vector_stores
           ADD CONSTRAINT fk_chat_provider_vector_stores_user
           FOREIGN KEY (user_id) REFERENCES users (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE agent_sandboxes
           ADD CONSTRAINT fk_agent_sandboxes_session
           FOREIGN KEY (session_id) REFERENCES sessions (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE agent_events
           ADD CONSTRAINT fk_agent_events_run
           FOREIGN KEY (run_id) REFERENCES agent_run_tasks (id)
           ON DELETE CASCADE NOT VALID""",
        """ALTER TABLE agent_summaries
           ADD CONSTRAINT fk_agent_summaries_session
           FOREIGN KEY (session_id) REFERENCES sessions (id)
           ON DELETE CASCADE NOT VALID""",
    ]
    for stmt in _fk_statements:
        op.execute(stmt)

    # ── Validate FK constraints ──────────────────────────────────────
    _validate_statements = [
        "ALTER TABLE chat_messages VALIDATE CONSTRAINT fk_chat_messages_session",
        "ALTER TABLE chat_messages VALIDATE CONSTRAINT fk_chat_messages_parent",
        "ALTER TABLE chat_provider_containers VALIDATE CONSTRAINT fk_chat_provider_containers_session",
        "ALTER TABLE chat_provider_files VALIDATE CONSTRAINT fk_chat_provider_files_session",
        "ALTER TABLE chat_provider_files VALIDATE CONSTRAINT fk_chat_provider_files_file",
        "ALTER TABLE chat_provider_vector_stores VALIDATE CONSTRAINT fk_chat_provider_vector_stores_user",
        "ALTER TABLE agent_sandboxes VALIDATE CONSTRAINT fk_agent_sandboxes_session",
        "ALTER TABLE agent_events VALIDATE CONSTRAINT fk_agent_events_run",
        "ALTER TABLE agent_summaries VALIDATE CONSTRAINT fk_agent_summaries_session",
    ]
    for stmt in _validate_statements:
        op.execute(stmt)

    # ── chat_runs telemetry columns ──────────────────────────────────
    op.add_column("chat_runs", sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("chat_runs", sa.Column("model_id", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("finish_reason", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("chat_runs", sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    # chat_runs columns
    op.drop_column("chat_runs", "completed_at")
    op.drop_column("chat_runs", "started_at")
    op.drop_column("chat_runs", "error_code")
    op.drop_column("chat_runs", "finish_reason")
    op.drop_column("chat_runs", "provider")
    op.drop_column("chat_runs", "model_id")
    op.drop_column("chat_runs", "assistant_message_id")

    # FK constraints
    op.drop_constraint("fk_agent_summaries_session", "agent_summaries", type_="foreignkey")
    op.drop_constraint("fk_agent_events_run", "agent_events", type_="foreignkey")
    op.drop_constraint("fk_agent_sandboxes_session", "agent_sandboxes", type_="foreignkey")
    op.drop_constraint("fk_chat_provider_vector_stores_user", "chat_provider_vector_stores", type_="foreignkey")
    op.drop_constraint("fk_chat_provider_files_file", "chat_provider_files", type_="foreignkey")
    op.drop_constraint("fk_chat_provider_files_session", "chat_provider_files", type_="foreignkey")
    op.drop_constraint("fk_chat_provider_containers_session", "chat_provider_containers", type_="foreignkey")
    op.drop_constraint("fk_chat_messages_parent", "chat_messages", type_="foreignkey")
    op.drop_constraint("fk_chat_messages_session", "chat_messages", type_="foreignkey")

    # Numeric → Float
    op.alter_column(
        "billing_transactions", "credits",
        existing_type=sa.Numeric(precision=18, scale=6),
        type_=sa.Float(), existing_nullable=True,
    )
    op.alter_column(
        "billing_transactions", "amount",
        existing_type=sa.Numeric(precision=18, scale=6),
        type_=sa.Float(), existing_nullable=True,
    )
    op.alter_column(
        "session_metrics", "credits",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Float(), existing_nullable=False,
    )
