"""Credit ledger billing system.

Creates all tables for the reserve/settle/release billing pattern:
- billing_customers: Links users to Stripe
- credit_ledger: Append-only audit trail
- credit_balances: Materialized balance with billing status
- usage_records: Per-operation usage tracking
- llm_invocations: LLM call telemetry
- tool_invocations: Tool call telemetry (with cost columns)
- credit_reservations: Reserve/settle/release state machine
- billing_usage_facts: Durable outbox for settlement recovery

Backfills billing_customers and credit_balances from users table.

Revision ID: b002b2b2b2b2
Revises: b001a1a1a1a1
Create Date: 2026-03-16 00:01:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b002b2b2b2b2"
down_revision: Union[str, None] = "b001a1a1a1a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── billing_customers ────────────────────────────────────────────
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="stripe"),
        sa.Column("external_customer_id", sa.String(), nullable=False),
        sa.Column("subscription_plan", sa.String(), nullable=True),
        sa.Column("subscription_status", sa.String(), nullable=True),
        sa.Column("subscription_billing_cycle", sa.String(), nullable=True),
        sa.Column("subscription_current_period_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("customer_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_billing_customers_user_provider"),
        sa.UniqueConstraint("provider", "external_customer_id", name="uq_billing_customers_provider_external"),
    )
    op.create_index("idx_billing_customers_user", "billing_customers", ["user_id"])

    # ── credit_ledger ────────────────────────────────────────────────
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("source_domain", sa.String(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("delta_credits", sa.Numeric(18, 6), nullable=False),
        sa.Column("delta_bonus_credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("balance_after_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("balance_after_bonus_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("entry_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_credit_ledger_user_created", "credit_ledger", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_credit_ledger_source", "credit_ledger", ["source_domain", "source_id"])
    op.create_index("idx_credit_ledger_entry_type", "credit_ledger", ["entry_type", sa.text("created_at DESC")])
    op.create_index(
        "uq_credit_ledger_idempotency_key", "credit_ledger", ["idempotency_key"],
        unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ── credit_balances (includes billing_status from the start) ─────
    op.create_table(
        "credit_balances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("bonus_credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("billing_status", sa.String(), nullable=False, server_default="ok"),
        sa.Column("billing_status_reason", sa.Text(), nullable=True),
        sa.Column("billing_status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_credit_balances_user_id"),
        sa.CheckConstraint("credits >= 0", name="ck_credit_balances_credits_floor"),
        sa.CheckConstraint("bonus_credits >= 0", name="ck_credit_balances_bonus_credits_floor"),
    )
    # Remove the server_default for billing_status after table creation
    op.alter_column("credit_balances", "billing_status", server_default=None)

    # ── usage_records ────────────────────────────────────────────────
    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ledger_entry_id", sa.BigInteger(), sa.ForeignKey("credit_ledger.id"), nullable=True),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("billing_kind", sa.String(), nullable=False),
        sa.Column("app_kind", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("credits_charged", sa.Numeric(18, 6), nullable=False),
        sa.Column("usage_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_usage_records_user_created", "usage_records", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_session", "usage_records", ["session_id", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_source", "usage_records", ["source_domain", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_billing_kind", "usage_records", ["billing_kind", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_model", "usage_records", ["model_id", sa.text("created_at DESC")])
    op.create_index(
        "uq_usage_records_ledger_entry_id", "usage_records", ["ledger_entry_id"],
        unique=True, postgresql_where=sa.text("ledger_entry_id IS NOT NULL"),
    )

    # ── llm_invocations ──────────────────────────────────────────────
    op.create_table(
        "llm_invocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("request_kind", sa.String(), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("credits_charged", sa.Numeric(18, 6), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("finish_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_llm_invocations_run", "llm_invocations", ["run_id", "created_at"])
    op.create_index("idx_llm_invocations_session", "llm_invocations", ["session_id", sa.text("created_at DESC")])
    op.create_index("idx_llm_invocations_model", "llm_invocations", ["model", sa.text("created_at DESC")])
    op.create_index("idx_llm_invocations_user", "llm_invocations", ["user_id", sa.text("created_at DESC")])

    # ── tool_invocations (with cost columns from the start) ──────────
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_tool_call_id", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("tool_namespace", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("input_summary", sa.String(), nullable=True),
        sa.Column("output_summary", sa.String(), nullable=True),
        sa.Column("is_error", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("credits_charged", sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tool_invocations_run", "tool_invocations", ["run_id", "created_at"])
    op.create_index("idx_tool_invocations_session", "tool_invocations", ["session_id", sa.text("created_at DESC")])
    op.create_index("idx_tool_invocations_tool", "tool_invocations", ["tool_name", sa.text("created_at DESC")])

    # ── credit_reservations ──────────────────────────────────────────
    op.create_table(
        "credit_reservations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("billing_kind", sa.String(), nullable=False),
        sa.Column("quote_strategy", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("reserve_ledger_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("release_ledger_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("shortfall_ledger_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("usage_record_id", sa.BigInteger(), nullable=True),
        sa.Column("reserved_credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("reserved_bonus_credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("actual_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("actual_bonus_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("released_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("released_bonus_credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("quoted_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("max_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("actual_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("reservation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["release_ledger_entry_id"], ["credit_ledger.id"]),
        sa.ForeignKeyConstraint(["reserve_ledger_entry_id"], ["credit_ledger.id"]),
        sa.ForeignKeyConstraint(["shortfall_ledger_entry_id"], ["credit_ledger.id"]),
        sa.ForeignKeyConstraint(["usage_record_id"], ["usage_records.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_credit_reservations_user_created", "credit_reservations", ["user_id", "created_at"])
    op.create_index("idx_credit_reservations_source", "credit_reservations", ["source_domain", "source_id"])
    op.create_index("idx_credit_reservations_status_expires", "credit_reservations", ["status", "expires_at"])
    op.create_index(
        "uq_credit_reservations_idempotency_key", "credit_reservations", ["idempotency_key"],
        unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ── billing_usage_facts ──────────────────────────────────────────
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
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processing_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["reservation_id"], ["credit_reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("reservation_id", name="uq_billing_usage_facts_reservation"),
    )
    op.create_index("idx_billing_usage_facts_status_created", "billing_usage_facts", ["status", "created_at"])
    op.create_index("idx_billing_usage_facts_dispatchable", "billing_usage_facts", ["status", "processing_started_at", "created_at"])
    op.create_index("idx_billing_usage_facts_session_created", "billing_usage_facts", ["session_id", "created_at"])
    op.create_index("idx_billing_usage_facts_user_created", "billing_usage_facts", ["user_id", "created_at"])
    op.create_index("idx_billing_usage_facts_run_created", "billing_usage_facts", ["run_id", "created_at"])

    # ── Backfill billing_customers from users ────────────────────────
    op.execute(
        sa.text("""
            INSERT INTO billing_customers (id, user_id, provider, external_customer_id,
                subscription_plan, subscription_status, subscription_billing_cycle,
                subscription_current_period_end, created_at, updated_at)
            SELECT
                gen_random_uuid()::text, id, 'stripe', stripe_customer_id,
                subscription_plan, subscription_status, subscription_billing_cycle,
                subscription_current_period_end, now(), now()
            FROM users
            WHERE NULLIF(stripe_customer_id, '') IS NOT NULL
            ON CONFLICT (user_id, provider) DO UPDATE
            SET external_customer_id = EXCLUDED.external_customer_id,
                subscription_plan = EXCLUDED.subscription_plan,
                subscription_status = EXCLUDED.subscription_status,
                subscription_billing_cycle = EXCLUDED.subscription_billing_cycle,
                subscription_current_period_end = EXCLUDED.subscription_current_period_end,
                updated_at = now()
        """)
    )

    # ── Backfill credit_balances from users ──────────────────────────
    op.execute(
        sa.text("""
            INSERT INTO credit_balances (id, user_id, credits, bonus_credits, billing_status, created_at, updated_at)
            SELECT gen_random_uuid()::text, id, COALESCE(credits, 0), COALESCE(bonus_credits, 0), 'ok', now(), now()
            FROM users
        """)
    )

    # ── Backfill initial_balance ledger entries ──────────────────────
    op.execute(
        sa.text("""
            INSERT INTO credit_ledger
                (user_id, entry_type, source_domain, delta_credits, delta_bonus_credits, created_at)
            SELECT id, 'initial_balance', 'migration_backfill',
                   COALESCE(credits, 0), COALESCE(bonus_credits, 0), now()
            FROM users
            WHERE COALESCE(credits, 0) != 0 OR COALESCE(bonus_credits, 0) != 0
        """)
    )


def downgrade() -> None:
    # Drop in reverse order of creation
    op.drop_index("idx_billing_usage_facts_run_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_user_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_session_created", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_dispatchable", table_name="billing_usage_facts")
    op.drop_index("idx_billing_usage_facts_status_created", table_name="billing_usage_facts")
    op.drop_table("billing_usage_facts")

    op.drop_index("uq_credit_reservations_idempotency_key", table_name="credit_reservations")
    op.drop_index("idx_credit_reservations_status_expires", table_name="credit_reservations")
    op.drop_index("idx_credit_reservations_source", table_name="credit_reservations")
    op.drop_index("idx_credit_reservations_user_created", table_name="credit_reservations")
    op.drop_table("credit_reservations")

    op.drop_index("idx_tool_invocations_tool", table_name="tool_invocations")
    op.drop_index("idx_tool_invocations_session", table_name="tool_invocations")
    op.drop_index("idx_tool_invocations_run", table_name="tool_invocations")
    op.drop_table("tool_invocations")

    op.drop_index("idx_llm_invocations_user", table_name="llm_invocations")
    op.drop_index("idx_llm_invocations_model", table_name="llm_invocations")
    op.drop_index("idx_llm_invocations_session", table_name="llm_invocations")
    op.drop_index("idx_llm_invocations_run", table_name="llm_invocations")
    op.drop_table("llm_invocations")

    op.drop_index("uq_usage_records_ledger_entry_id", table_name="usage_records")
    op.drop_index("idx_usage_records_model", table_name="usage_records")
    op.drop_index("idx_usage_records_billing_kind", table_name="usage_records")
    op.drop_index("idx_usage_records_source", table_name="usage_records")
    op.drop_index("idx_usage_records_session", table_name="usage_records")
    op.drop_index("idx_usage_records_user_created", table_name="usage_records")
    op.drop_table("usage_records")

    op.execute(sa.text("""
        DELETE FROM credit_ledger
        WHERE entry_type = 'initial_balance' AND source_domain = 'migration_backfill'
    """))

    op.drop_table("credit_balances")

    op.drop_index("uq_credit_ledger_idempotency_key", table_name="credit_ledger")
    op.drop_index("idx_credit_ledger_entry_type", table_name="credit_ledger")
    op.drop_index("idx_credit_ledger_source", table_name="credit_ledger")
    op.drop_index("idx_credit_ledger_user_created", table_name="credit_ledger")
    op.drop_table("credit_ledger")

    op.drop_index("idx_billing_customers_user", table_name="billing_customers")
    op.drop_table("billing_customers")
