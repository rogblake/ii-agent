"""Remove billing usage facts outbox table.

Revision ID: c9f4e1a2b3c4
Revises: b002b2b2b2b2
Create Date: 2026-03-22 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9f4e1a2b3c4"
down_revision: Union[str, None] = "b002b2b2b2b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_billing_usage_facts_run_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_user_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_session_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_dispatchable", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_status_created", table_name="billing_usage_facts")
    op.drop_table("billing_usage_facts")


def downgrade() -> None:
    op.create_table(
        "billing_usage_facts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("reservation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("billing_kind", sa.String(), nullable=False),
        sa.Column("event_kind", sa.String(), nullable=False),
        sa.Column("app_kind", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("request_kind", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("charged_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'captured'")),
        sa.Column("attempt_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "captured_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processing_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["reservation_id"], ["credit_reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("reservation_id", name="uq_billing_usage_facts_reservation"),
    )
    op.create_index(
        "idx_billing_usage_facts_status_created", "billing_usage_facts", ["status", "created_at"]
    )
    op.create_index(
        "idx_billing_usage_facts_dispatchable",
        "billing_usage_facts",
        ["status", "processing_started_at", "created_at"],
    )
    op.create_index(
        "idx_billing_usage_facts_session_created",
        "billing_usage_facts",
        ["session_id", "created_at"],
    )
    op.create_index(
        "idx_billing_usage_facts_user_created", "billing_usage_facts", ["user_id", "created_at"]
    )
    op.create_index(
        "idx_billing_usage_facts_run_created", "billing_usage_facts", ["run_id", "created_at"]
    )
