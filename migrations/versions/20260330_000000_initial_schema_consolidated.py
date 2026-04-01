"""Initial schema consolidated.

Revision ID: 0001_initial
Revises: None
Create Date: 2026-03-30

All 38 tables from the II-Agent application, ordered by FK dependency.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY

# revision identifiers, used by Alembic.
revision = "20260330_000000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Users & Auth
    # =========================================================================

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("avatar", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("login_provider", sa.String(), nullable=True),
        sa.Column("organization", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("subscription_plan", sa.String(), nullable=True),
        sa.Column("subscription_status", sa.String(), nullable=True),
        sa.Column("subscription_billing_cycle", sa.String(), nullable=True),
        sa.Column("subscription_current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("idx_api_keys_is_active", "api_keys", ["is_active"])

    op.create_table(
        "waitlist",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # =========================================================================
    # 2. Settings (LLM, MCP, Skills)
    # =========================================================================

    op.create_table(
        "model_settings",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("encrypted_api_key", sa.String(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column("pricing", JSONB(), nullable=True),
        sa.Column("config_type", sa.String(), nullable=False, server_default="user"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_model_settings_user_id", "model_settings", ["user_id"])
    op.create_index(
        "uq_model_settings_user",
        "model_settings",
        ["model_id", "provider", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_model_settings_system",
        "model_settings",
        ["model_id", "provider"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    op.create_table(
        "mcp_settings",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mcp_config", JSONB(none_as_null=True), nullable=False),
        sa.Column("metadata", JSONB(none_as_null=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_mcp_settings_user_id", "mcp_settings", ["user_id"])

    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="builtin"),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("skill_md_content", sa.Text(), nullable=False),
        sa.Column("sandbox_path", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=False),
        sa.Column("allowed_tools", JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("license", sa.String(), nullable=True),
        sa.Column("compatibility", sa.String(500), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_skills_user_id", "skills", ["user_id"])
    op.create_index("idx_skills_source", "skills", ["source"])
    op.create_index("idx_skills_enabled", "skills", ["is_enabled"])
    op.create_unique_constraint("uq_skills_user_name", "skills", ["user_id", "name"])
    op.create_index(
        "idx_skills_builtin_name_unique",
        "skills",
        ["name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    # =========================================================================
    # 3. Sessions
    # =========================================================================

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("model_setting_id", UUID(as_uuid=True), sa.ForeignKey("model_settings.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("agent_type", sa.String(), nullable=True),
        sa.Column("app_kind", sa.String(), nullable=False, server_default="agent"),
        sa.Column("public_url", sa.String(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("api_version", sa.String(), nullable=False, server_default="v0"),
        sa.Column("parent_session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("session_metadata", JSONB(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_status", "sessions", ["status"])
    op.create_index("idx_sessions_created_at", "sessions", ["created_at"])
    op.create_index("idx_sessions_model_setting_id", "sessions", ["model_setting_id"])
    op.create_index("idx_sessions_parent_session_id", "sessions", ["parent_session_id"])

    op.create_table(
        "session_pins",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_session_pins_user_session", "session_pins", ["user_id", "session_id"], unique=True)
    op.create_index("idx_session_pins_session_id", "session_pins", ["session_id"])

    op.create_table(
        "session_wishlists",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_session_wishlists_user_session", "session_wishlists", ["user_id", "session_id"], unique=True)
    op.create_index("idx_session_wishlists_session_id", "session_wishlists", ["session_id"])

    # =========================================================================
    # 4. Tasks & Agent Runs
    # =========================================================================

    op.create_table(
        "run_tasks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FK to sessions — high-volume table; use index for lookups, app-level integrity
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("data", JSONB(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_run_tasks_session_id", "run_tasks", ["session_id"])
    op.create_index("ix_run_tasks_status", "run_tasks", ["status"])
    op.create_index("ix_run_tasks_session_status", "run_tasks", ["session_id", "status"])
    op.create_index("ix_run_tasks_created_at", "run_tasks", ["created_at"])
    op.create_index("ix_run_tasks_task_type", "run_tasks", ["task_type"])
    op.create_index(
        "uq_run_tasks_session_type_active",
        "run_tasks",
        ["session_id", "task_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'waiting_for_input')"),
    )
    op.create_table(
        "task_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # No FK to run_tasks — high-volume append-only log; use index for lookups
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("data", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_logs_task_id", "task_logs", ["task_id"])
    op.create_index("ix_task_logs_created_at", "task_logs", ["created_at"])
    op.create_index("ix_task_logs_task_created", "task_logs", ["task_id", "created_at"])

    op.create_table(
        "agent_run_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # No FKs — high-volume table; use indexes for lookups, app-level integrity
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("run_input", JSONB(), nullable=True),
        sa.Column("messages", JSONB(), nullable=True),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("additional_info", JSONB(), nullable=True),
        sa.Column("tools", JSONB(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_run_messages_session_id", "agent_run_messages", ["session_id"])
    op.create_index("ix_agent_run_messages_run_id", "agent_run_messages", ["run_id"])
    op.create_index("ix_agent_run_messages_parent_run_id", "agent_run_messages", ["parent_run_id"])
    op.create_index("ix_agent_run_messages_session_run", "agent_run_messages", ["session_id", "run_id"])
    op.create_index("ix_agent_run_messages_created_at", "agent_run_messages", ["created_at"])
    op.create_index("ix_agent_run_messages_status", "agent_run_messages", ["status"])

    op.create_table(
        "session_summaries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("topics", JSONB, nullable=True),
        sa.Column("metrics", JSONB, nullable=True),
        sa.Column("session_id", sa.String, nullable=False),
        sa.Column("agent_run_id", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_session_summaries_session_id",
        "session_summaries",
        ["session_id"],
        unique=True,
    )
    op.create_index(
        "ix_session_summaries_session_id_agent_run_id",
        "session_summaries",
        ["session_id", "agent_run_id"],
    )

    op.create_table(
        "agent_sandboxes",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FK to sessions — sandbox lifecycle managed by app; use index for lookups
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="e2b"),
        sa.Column("provider_sandbox_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="initializing"),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_data", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_sandboxes_session_id", "agent_sandboxes", ["session_id"])

    # =========================================================================
    # 5. Files (must come before chat_provider_files which references user_assets)
    # =========================================================================

    op.create_table(
        "user_assets",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False, unique=True),
        sa.Column("content_type", sa.String(200), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("asset_type", sa.String(20), nullable=False, server_default="other"),
        sa.Column("source", sa.String(30), nullable=False, server_default="user_upload"),
        sa.Column("upload_status", sa.String(20), nullable=False, server_default="complete"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sandbox_path", sa.String(1000), nullable=True),
        sa.Column("signed_url", sa.String(2000), nullable=True),
        sa.Column("signed_url_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_user_assets_user_id", "user_assets", ["user_id"])
    op.create_index("idx_user_assets_upload_status", "user_assets", ["upload_status"])

    op.create_table(
        "session_assets",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("user_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_session_assets_session_id", "session_assets", ["session_id"])
    op.create_index("idx_session_assets_asset_id", "session_assets", ["asset_id"])
    op.create_unique_constraint("uq_session_asset", "session_assets", ["session_id", "asset_id"])

    # =========================================================================
    # 6. Chat
    # =========================================================================

    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FK to sessions — highest-volume table; use index for lookups, app-level integrity
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("usage", JSONB(), nullable=True),
        sa.Column("tokens", sa.BigInteger(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("tools", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("provider_metadata", JSONB(), nullable=True),
        sa.Column("file_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        # No FK self-ref — app manages tree integrity
        sa.Column("parent_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_finished", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("finish_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_chat_messages_session", "chat_messages", ["session_id"])
    op.create_index("idx_chat_messages_created", "chat_messages", ["created_at"])
    op.create_index("idx_chat_messages_parent", "chat_messages", ["parent_message_id"])
    op.create_index("idx_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])

    op.create_table(
        "chat_summaries",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FK to sessions — chat data managed at app level; use index for lookups
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("end_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_tokens", sa.BigInteger(), nullable=False),
        sa.Column("summary_tokens", sa.BigInteger(), nullable=False),
        sa.Column("compression_ratio", sa.Float(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("parent_summary_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_summaries_session", "chat_summaries", ["session_id"])
    op.create_index("idx_summaries_end_message", "chat_summaries", ["end_message_id"])

    op.create_table(
        "chat_provider_containers",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FK to sessions — provider data managed at app level; use index for lookups
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("container_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_container_object", JSONB(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_chat_provider_containers_session_id", "chat_provider_containers", ["session_id"])
    op.create_index("idx_chat_provider_containers_provider", "chat_provider_containers", ["provider"])
    op.create_index("idx_chat_provider_containers_session_provider", "chat_provider_containers", ["session_id", "provider"])
    op.create_index("idx_chat_provider_containers_expires_at", "chat_provider_containers", ["expires_at"])
    op.create_unique_constraint("uq_chat_provider_containers_container_provider", "chat_provider_containers", ["container_id", "provider"])

    op.create_table(
        "chat_provider_files",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FKs — provider cache table; use indexes for lookups
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_file_id", sa.String(), nullable=False),
        sa.Column("raw_file_object", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_chat_provider_files_file_id", "chat_provider_files", ["file_id"])
    op.create_index("idx_chat_provider_files_provider", "chat_provider_files", ["provider"])
    op.create_index("idx_chat_provider_files_file_provider", "chat_provider_files", ["file_id", "provider"])
    op.create_index("idx_chat_provider_files_expires_at", "chat_provider_files", ["expires_at"])
    op.create_unique_constraint("uq_chat_provider_files_provider_file_provider", "chat_provider_files", ["provider_file_id", "provider"])

    op.create_table(
        "chat_provider_vector_stores",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("vector_store_id", sa.String(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("raw_vector_object", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_chat_provider_vector_stores_user_id", "chat_provider_vector_stores", ["user_id"])
    op.create_index("idx_chat_provider_vector_stores_provider", "chat_provider_vector_stores", ["provider"])
    op.create_index("idx_chat_provider_vector_stores_vector_store_id", "chat_provider_vector_stores", ["vector_store_id"])
    op.create_index("idx_chat_provider_vector_stores_expires_at", "chat_provider_vector_stores", ["expires_at"])
    op.create_unique_constraint(
        "uq_chat_provider_vector_stores_user_provider_vector",
        "chat_provider_vector_stores",
        ["user_id", "provider", "vector_store_id"],
    )

    # =========================================================================
    # 7. Billing & Credits
    # =========================================================================

    op.create_table(
        "billing_transactions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stripe_event_id", sa.String(), nullable=False, unique=True),
        sa.Column("stripe_object_id", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("plan_id", sa.String(), nullable=True),
        sa.Column("billing_cycle", sa.String(), nullable=True),
        sa.Column("credits", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("raw_payload", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_billing_transactions_user_id", "billing_transactions", ["user_id"])
    op.create_index("idx_billing_transactions_subscription", "billing_transactions", ["stripe_subscription_id"])

    op.create_table(
        "credit_balances",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("bonus_credits", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("billing_status", sa.String(), nullable=False, server_default="ok"),
        sa.Column("billing_status_reason", sa.Text(), nullable=True),
        sa.Column("billing_status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # No FKs — ledger table (append-only, high-volume); use indexes for lookups
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("credit_type", sa.String(10), nullable=False, server_default="regular"),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 6), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("billing_transaction_id", UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data", JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_credit_tx_user", "credit_transactions", ["user_id", "created_at"])
    op.create_index(
        "idx_credit_tx_session",
        "credit_transactions",
        ["session_id", "created_at"],
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )
    op.create_index("idx_credit_tx_type", "credit_transactions", ["user_id", "transaction_type", "created_at"])
    op.create_index(
        "idx_credit_tx_billing",
        "credit_transactions",
        ["billing_transaction_id"],
        postgresql_where=sa.text("billing_transaction_id IS NOT NULL"),
    )

    # =========================================================================
    # 8. Projects & Deployments
    # =========================================================================

    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("current_build_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("framework", sa.String(), nullable=True),
        sa.Column("project_path", sa.String(), nullable=True),
        sa.Column("production_url", sa.String(), nullable=True),
        sa.Column("database_json", JSONB(), nullable=True),
        sa.Column("storage_json", JSONB(), nullable=True),
        sa.Column("secrets_json", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_projects_user_id", "projects", ["user_id"])
    op.create_index("idx_projects_session_id", "projects", ["session_id"])
    op.create_index("idx_projects_status", "projects", ["status"])
    op.create_unique_constraint("uq_projects_session_id", "projects", ["session_id"])

    op.create_table(
        "project_deployments",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("deployment_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("deployment_url", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deploy_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deployed_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="cloud_run"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot_id", sa.String(255), nullable=True),
        sa.Column("source_path", sa.String(500), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("error_phase", sa.String(50), nullable=True),
        sa.Column("error_details", JSONB(), nullable=True),
        sa.Column("upload_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("build_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_project_deployments_project_id", "project_deployments", ["project_id"])
    op.create_index("idx_project_deployments_environment", "project_deployments", ["environment"])
    op.create_index("idx_project_deployments_provider", "project_deployments", ["provider"])
    op.create_index("idx_project_deployments_version", "project_deployments", ["project_id", "version"])
    op.create_index(
        "idx_project_deployments_deployed_by",
        "project_deployments",
        ["deployed_by_user_id"],
        postgresql_where=sa.text("deployed_by_user_id IS NOT NULL"),
    )

    op.create_table(
        "project_custom_domains",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("subdomain", sa.String(63), nullable=False, unique=True),
        sa.Column("full_domain", sa.String(255), nullable=False),
        sa.Column("deployment_id", UUID(as_uuid=True), sa.ForeignKey("project_deployments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dns_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("ssl_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("cloudflare_record_id", sa.String(100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_project_custom_domains_project_id", "project_custom_domains", ["project_id"])
    op.create_index("idx_project_custom_domains_subdomain", "project_custom_domains", ["subdomain"])
    op.create_index(
        "idx_project_custom_domains_deployment_id",
        "project_custom_domains",
        ["deployment_id"],
        postgresql_where=sa.text("deployment_id IS NOT NULL"),
    )

    op.create_table(
        "project_databases",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="neondb"),
        sa.Column("connection_string", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=True),
        sa.Column("database_name", sa.String(), nullable=True),
        sa.Column("role_name", sa.String(), nullable=True),
        sa.Column("branch_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_project_databases_session_id", "project_databases", ["session_id"])
    op.create_index("idx_project_databases_source", "project_databases", ["source"])
    op.create_index("idx_project_databases_is_active", "project_databases", ["is_active"])

    # =========================================================================
    # 9. Content (Slides, Media, Storybooks)
    # =========================================================================

    op.create_table(
        "slide_contents",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_name", sa.String(), nullable=False),
        sa.Column("slide_number", sa.BigInteger(), nullable=False),
        sa.Column("slide_title", sa.String(), nullable=True),
        sa.Column("slide_content", sa.String(), nullable=False),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_slide_contents_session_id", "slide_contents", ["session_id"])
    op.create_index("idx_slide_contents_presentation_name", "slide_contents", ["presentation_name"])
    op.create_index(
        "idx_slide_contents_session_presentation_slide",
        "slide_contents",
        ["session_id", "presentation_name", "slide_number"],
        unique=True,
    )

    op.create_table(
        "slide_versions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_name", sa.String(), nullable=False),
        sa.Column("slide_number", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("root_version_id", UUID(as_uuid=True), sa.ForeignKey("slide_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_version_id", UUID(as_uuid=True), sa.ForeignKey("slide_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("edit_summary", sa.String(), nullable=True),
        sa.Column("instructions_applied", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_slide_versions_session_id", "slide_versions", ["session_id"])
    op.create_index("idx_slide_versions_session_slide", "slide_versions", ["session_id", "presentation_name", "slide_number"])
    op.create_index("idx_slide_versions_root", "slide_versions", ["root_version_id"])
    op.create_index("idx_slide_versions_parent", "slide_versions", ["parent_version_id"])

    op.create_table(
        "slide_templates",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("slide_template_name", sa.String(), nullable=False),
        sa.Column("slide_content", sa.String(), nullable=False),
        sa.Column("slide_template_images", ARRAY(sa.String()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("idx_slide_templates_name", "slide_templates", ["slide_template_name"])

    op.create_table(
        "media_templates",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("preview", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )

    op.create_table(
        "storybook_pages",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("page_number", sa.BigInteger(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("audio_link", sa.String(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_storybook_pages_page_number", "storybook_pages", ["page_number"])

    op.create_table(
        "storybooks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("root_storybook_id", UUID(as_uuid=True), sa.ForeignKey("storybooks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_storybook_id", UUID(as_uuid=True), sa.ForeignKey("storybooks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("style_json", JSONB(), nullable=True),
        sa.Column("aspect_ratio", sa.String(), nullable=False, server_default="1:1"),
        sa.Column("resolution", sa.String(), nullable=False, server_default="1K"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_storybooks_session_id", "storybooks", ["session_id"])
    op.create_index("idx_storybooks_root_id", "storybooks", ["root_storybook_id"])
    op.create_index("idx_storybooks_parent_id", "storybooks", ["parent_storybook_id"])
    op.create_index("idx_storybooks_created_at", "storybooks", ["created_at"])

    op.create_table(
        "storybook_page_links",
        sa.Column("storybook_id", UUID(as_uuid=True), sa.ForeignKey("storybooks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("page_id", UUID(as_uuid=True), sa.ForeignKey("storybook_pages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_storybook_page_links_storybook_id", "storybook_page_links", ["storybook_id"])
    op.create_index("idx_storybook_page_links_page_id", "storybook_page_links", ["page_id"])

    # =========================================================================
    # 10. Integrations
    # =========================================================================

    op.create_table(
        "connectors",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_type", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_connectors_user_id", "connectors", ["user_id"])
    op.create_index("idx_connectors_type", "connectors", ["connector_type"])
    op.create_unique_constraint("uq_user_connector_type", "connectors", ["user_id", "connector_type"])

    op.create_table(
        "composio_profiles",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_name", sa.String(), nullable=False),
        sa.Column("toolkit_slug", sa.String(), nullable=False),
        sa.Column("toolkit_name", sa.String(), nullable=False),
        sa.Column("auth_config_id", sa.String(), nullable=False),
        sa.Column("connected_account_id", sa.String(), nullable=False),
        sa.Column("mcp_server_id", sa.String(), nullable=False),
        sa.Column("composio_user_id", sa.String(), nullable=False),
        sa.Column("encrypted_mcp_url", sa.String(), nullable=False),
        sa.Column("redirect_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled_tools", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_composio_profiles_user_id", "composio_profiles", ["user_id"])
    op.create_index("idx_composio_profiles_toolkit_slug", "composio_profiles", ["toolkit_slug"])
    op.create_unique_constraint("uq_composio_profile_name", "composio_profiles", ["user_id", "profile_name"])

    op.create_table(
        "apple_credentials",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("apple_id", sa.String(), nullable=False),
        sa.Column("auth_state", sa.String(), nullable=False, server_default="pending_login"),
        sa.Column("encrypted_session_data", sa.Text(), nullable=True),
        sa.Column("selected_team_id", sa.String(), nullable=True),
        sa.Column("team_name", sa.String(), nullable=True),
        sa.Column("available_teams", JSONB(), nullable=True),
        sa.Column("session_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encrypted_expo_token", sa.Text(), nullable=True),
        sa.Column("encrypted_app_specific_password", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_p12", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_p12_password", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_provisioning_profile", sa.Text(), nullable=True),
        sa.Column("ios_bundle_identifier", sa.String(), nullable=True),
        sa.Column("ios_certificate_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ios_certificate_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_apple_credentials_user_id", "apple_credentials", ["user_id"])
    op.create_unique_constraint("uq_user_apple_account", "apple_credentials", ["user_id", "apple_id"])

    # =========================================================================
    # 11. Events
    # =========================================================================

    op.create_table(
        "application_events",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_group", sa.String(50), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("content", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_app_events_session", "application_events", ["session_id", "created_at"])
    op.create_index("idx_app_events_session_type", "application_events", ["session_id", "event_type"])
    op.create_index(
        "idx_app_events_run",
        "application_events",
        ["run_id", "created_at"],
        postgresql_where=sa.text("run_id IS NOT NULL"),
    )
    op.create_index("idx_app_events_group", "application_events", ["event_group", "created_at"])
    op.create_index("idx_app_events_user", "application_events", ["user_id", "created_at"])
    op.create_index("idx_app_events_created_brin", "application_events", ["created_at"], postgresql_using="brin")


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("storybook_page_links")
    op.drop_table("storybooks")
    op.drop_table("storybook_pages")
    op.drop_table("media_templates")
    op.drop_table("slide_templates")
    op.drop_table("slide_versions")
    op.drop_table("slide_contents")
    op.drop_table("apple_credentials")
    op.drop_table("composio_profiles")
    op.drop_table("connectors")
    op.drop_table("project_databases")
    op.drop_table("project_custom_domains")
    op.drop_table("project_deployments")
    op.drop_table("projects")
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")
    op.drop_table("billing_transactions")
    op.drop_table("session_assets")
    op.drop_table("user_assets")
    op.drop_table("chat_provider_vector_stores")
    op.drop_table("chat_provider_files")
    op.drop_table("chat_provider_containers")
    op.drop_table("chat_summaries")
    op.drop_table("chat_messages")
    op.drop_table("agent_sandboxes")
    op.drop_table("session_summaries")
    op.drop_table("agent_run_messages")
    op.drop_table("task_logs")
    op.drop_table("run_tasks")
    op.drop_table("session_wishlists")
    op.drop_table("session_pins")
    op.drop_table("sessions")
    op.drop_table("skills")
    op.drop_table("mcp_settings")
    op.drop_table("model_settings")
    op.drop_table("waitlist")
    op.drop_table("api_keys")
    op.drop_table("users")
