"""Combine billing subject scope and billing_context schema changes.

Revision ID: r3s4t5u6v7w8
Revises: c9f4e1a2b3c4
Create Date: 2026-03-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "r3s4t5u6v7w8"
down_revision: Union[str, None] = "c9f4e1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== credit_reservations ====================
    op.add_column(
        "credit_reservations",
        sa.Column("billing_context", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "credit_reservations",
        sa.Column("subject_kind", sa.String(), nullable=False, server_default="session"),
    )
    op.alter_column(
        "credit_reservations",
        "session_id",
        existing_type=sa.String(),
        existing_nullable=True,
        new_column_name="subject_id",
    )
    op.create_index(
        "idx_credit_reservations_subject_created",
        "credit_reservations",
        ["subject_kind", "subject_id", "created_at"],
    )
    op.create_index(
        "idx_credit_reservations_billing_context_created",
        "credit_reservations",
        ["billing_context", "created_at"],
    )
    op.alter_column("credit_reservations", "subject_kind", server_default=None)
    op.alter_column("credit_reservations", "billing_context", server_default=None)

    # ==================== usage_records ====================
    op.add_column(
        "usage_records",
        sa.Column("billing_context", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "usage_records",
        sa.Column("subject_kind", sa.String(), nullable=False, server_default="session"),
    )
    op.drop_index("idx_usage_records_session", table_name="usage_records")
    op.alter_column(
        "usage_records",
        "session_id",
        existing_type=sa.String(),
        existing_nullable=True,
        new_column_name="subject_id",
    )
    op.create_index(
        "idx_usage_records_subject",
        "usage_records",
        ["subject_kind", "subject_id", "created_at"],
    )
    op.create_index(
        "idx_usage_records_billing_context",
        "usage_records",
        ["billing_context", "created_at"],
    )
    op.alter_column("usage_records", "subject_kind", server_default=None)
    op.alter_column("usage_records", "billing_context", server_default=None)

    # ==================== llm_invocations ====================
    op.add_column(
        "llm_invocations",
        sa.Column("billing_context", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "llm_invocations",
        sa.Column("subject_kind", sa.String(), nullable=False, server_default="session"),
    )
    op.drop_index("idx_llm_invocations_session", table_name="llm_invocations")
    op.alter_column(
        "llm_invocations",
        "session_id",
        existing_type=sa.String(),
        existing_nullable=False,
        nullable=True,
        new_column_name="subject_id",
    )
    op.create_index(
        "idx_llm_invocations_subject",
        "llm_invocations",
        ["subject_kind", "subject_id", "created_at"],
    )
    op.create_index(
        "idx_llm_invocations_billing_context",
        "llm_invocations",
        ["billing_context", "created_at"],
    )
    op.alter_column("llm_invocations", "subject_kind", server_default=None)
    op.alter_column("llm_invocations", "billing_context", server_default=None)

    # ==================== tool_invocations ====================
    op.add_column(
        "tool_invocations",
        sa.Column("billing_context", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "tool_invocations",
        sa.Column("subject_kind", sa.String(), nullable=False, server_default="session"),
    )
    op.drop_index("idx_tool_invocations_session", table_name="tool_invocations")
    op.alter_column(
        "tool_invocations",
        "session_id",
        existing_type=sa.String(),
        existing_nullable=False,
        nullable=True,
        new_column_name="subject_id",
    )
    op.create_index(
        "idx_tool_invocations_subject",
        "tool_invocations",
        ["subject_kind", "subject_id", "created_at"],
    )
    op.create_index(
        "idx_tool_invocations_billing_context",
        "tool_invocations",
        ["billing_context", "created_at"],
    )
    op.alter_column("tool_invocations", "subject_kind", server_default=None)
    op.alter_column("tool_invocations", "billing_context", server_default=None)


def downgrade() -> None:
    # ==================== tool_invocations ====================
    op.drop_index("idx_tool_invocations_billing_context", table_name="tool_invocations")
    op.drop_index("idx_tool_invocations_subject", table_name="tool_invocations")
    op.alter_column(
        "tool_invocations",
        "subject_id",
        existing_type=sa.String(),
        existing_nullable=True,
        nullable=False,
        new_column_name="session_id",
    )
    op.create_index(
        "idx_tool_invocations_session",
        "tool_invocations",
        ["session_id", sa.text("created_at DESC")],
    )
    op.drop_column("tool_invocations", "subject_kind")
    op.drop_column("tool_invocations", "billing_context")

    # ==================== llm_invocations ====================
    op.drop_index("idx_llm_invocations_billing_context", table_name="llm_invocations")
    op.drop_index("idx_llm_invocations_subject", table_name="llm_invocations")
    op.alter_column(
        "llm_invocations",
        "subject_id",
        existing_type=sa.String(),
        existing_nullable=True,
        nullable=False,
        new_column_name="session_id",
    )
    op.create_index(
        "idx_llm_invocations_session",
        "llm_invocations",
        ["session_id", sa.text("created_at DESC")],
    )
    op.drop_column("llm_invocations", "subject_kind")
    op.drop_column("llm_invocations", "billing_context")

    # ==================== usage_records ====================
    op.drop_index("idx_usage_records_billing_context", table_name="usage_records")
    op.drop_index("idx_usage_records_subject", table_name="usage_records")
    op.alter_column(
        "usage_records",
        "subject_id",
        existing_type=sa.String(),
        existing_nullable=True,
        new_column_name="session_id",
    )
    op.create_index(
        "idx_usage_records_session",
        "usage_records",
        ["session_id", sa.text("created_at DESC")],
    )
    op.drop_column("usage_records", "subject_kind")
    op.drop_column("usage_records", "billing_context")

    # ==================== credit_reservations ====================
    op.drop_index(
        "idx_credit_reservations_billing_context_created",
        table_name="credit_reservations",
    )
    op.drop_index("idx_credit_reservations_subject_created", table_name="credit_reservations")
    op.alter_column(
        "credit_reservations",
        "subject_id",
        existing_type=sa.String(),
        existing_nullable=True,
        new_column_name="session_id",
    )
    op.drop_column("credit_reservations", "subject_kind")
    op.drop_column("credit_reservations", "billing_context")
