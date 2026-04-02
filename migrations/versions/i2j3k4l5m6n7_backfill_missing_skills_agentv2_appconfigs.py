"""Backfill missing skills, agent_v2, and application_configs tables

This migration backfills schema changes that were skipped in production:
- b3c4d5e6f7g8: Add skills table
- c3d4e5f6g7h8: Add agent_v2 tables (agent_run_messages, agent_run_events, sandboxes)
- d4e5f6g7h8i9: Add application_configs table

This migration is idempotent - safe to run even if tables/columns already exist.

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-02-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "i2j3k4l5m6n7"
down_revision: Union[str, None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    """Backfill missing tables and columns from skipped migrations."""

    # =========================================================================
    # From b3c4d5e6f7g8: Add skills table
    # =========================================================================
    if not table_exists("skills"):
        op.create_table(
            "skills",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="builtin"),
            sa.Column("source_url", sa.String(), nullable=True),
            sa.Column("skill_md_content", sa.Text(), nullable=False),
            sa.Column("sandbox_path", sa.String(), nullable=False),
            sa.Column("storage_uri", sa.String(), nullable=False),
            sa.Column("allowed_tools", JSONB(), nullable=True, server_default="[]"),
            sa.Column("license", sa.String(), nullable=True),
            sa.Column("compatibility", sa.String(500), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_skills_user_name"),
        )
        op.create_index("idx_skills_user_id", "skills", ["user_id"])
        op.create_index("idx_skills_source", "skills", ["source"])
        op.create_index("idx_skills_enabled", "skills", ["is_enabled"])
        op.create_index(
            "idx_skills_builtin_name_unique",
            "skills",
            ["name"],
            unique=True,
            postgresql_where=sa.text("user_id IS NULL"),
        )

    # =========================================================================
    # From c3d4e5f6g7h8: Add agent_v2 tables
    # =========================================================================

    # Add api_version column to sessions table
    if table_exists("sessions") and not column_exists("sessions", "api_version"):
        op.add_column(
            "sessions",
            sa.Column("api_version", sa.String(10), nullable=False, server_default="v0"),
        )

    # Add error_message column to agent_run_tasks table
    if table_exists("agent_run_tasks") and not column_exists("agent_run_tasks", "error_message"):
        op.add_column(
            "agent_run_tasks",
            sa.Column("error_message", sa.Text(), nullable=True),
        )

    # Create agent_run_messages table
    if not table_exists("agent_run_messages"):
        op.create_table(
            "agent_run_messages",
            sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("run_id", UUID(as_uuid=True), nullable=False),
            sa.Column("model_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("run_input", JSONB(), nullable=True),
            sa.Column("messages", JSONB(), nullable=True),
            sa.Column("metrics", JSONB(), nullable=True),
            sa.Column("additional_info", JSONB(), nullable=True),
            sa.Column("tools", JSONB(), nullable=True),
            sa.Column("parent_run_id", UUID(as_uuid=True), nullable=True),
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
        )
        op.create_index("ix_agent_run_messages_session_id", "agent_run_messages", ["session_id"])
        op.create_index("ix_agent_run_messages_run_id", "agent_run_messages", ["run_id"])
        op.create_index("ix_agent_run_messages_session_run", "agent_run_messages", ["session_id", "run_id"])
        op.create_index("ix_agent_run_messages_created_at", "agent_run_messages", ["created_at"])
        op.create_index("ix_agent_run_messages_status", "agent_run_messages", ["status"])
        op.create_index("ix_agent_run_messages_parent_run_id", "agent_run_messages", ["parent_run_id"])

    # Create agent_run_events table
    if not table_exists("agent_run_events"):
        op.create_table(
            "agent_run_events",
            sa.Column("id", UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("run_id", UUID(as_uuid=True), nullable=False),
            sa.Column("group", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("payload", JSONB(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_agent_run_events"),
        )
        op.create_index("ix_agent_run_events_session_id", "agent_run_events", ["session_id"])
        op.create_index("ix_agent_run_events_run_id", "agent_run_events", ["run_id"])
        op.create_index("ix_agent_run_events_session_run", "agent_run_events", ["session_id", "run_id"])
        op.create_index("ix_agent_run_events_name", "agent_run_events", ["name"])
        op.create_index("ix_agent_run_events_created_at", "agent_run_events", ["created_at"])

    # Create sandboxes table
    if not table_exists("sandboxes"):
        op.create_table(
            "sandboxes",
            sa.Column("id", UUID(as_uuid=True), nullable=False),
            sa.Column("provider", sa.String(), nullable=False, server_default="e2b"),
            sa.Column("provider_sandbox_id", sa.String(), nullable=True),
            sa.Column("provider_data", JSONB(), nullable=True),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="not_initialized"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_sandboxes"),
            sa.UniqueConstraint("session_id", name="uq_sandboxes_session_id"),
        )
        op.create_index("idx_sandboxes_status", "sandboxes", ["status"])
        op.create_index("idx_sandboxes_provider_sandbox_id", "sandboxes", ["provider_sandbox_id"])
        op.create_index("idx_sandboxes_session_id", "sandboxes", ["session_id"])

    # =========================================================================
    # From d4e5f6g7h8i9: Add application_configs table
    # =========================================================================
    if not table_exists("application_configs"):
        op.create_table(
            "application_configs",
            sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", JSONB(), nullable=True),
            sa.Column("is_secret", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name="pk_application_configs"),
            sa.UniqueConstraint("key", name="uq_application_configs_key"),
        )
        op.create_index("idx_application_configs_is_secret", "application_configs", ["is_secret"])

    # Seed initial agent v1 settings (only if not exists)
    if table_exists("application_configs"):
        op.execute(
            """
            INSERT INTO application_configs (key, value, is_secret, version, created_at, updated_at)
            SELECT 'agent_v1_version_toggle', 'false'::jsonb, false, 0, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM application_configs WHERE key = 'agent_v1_version_toggle'
            )
            """
        )


def downgrade() -> None:
    """Remove backfilled tables and columns.

    Note: This downgrade is intentionally a no-op because these tables/columns
    may have been created by the original migrations (b3c4d5e6f7g8, c3d4e5f6g7h8,
    d4e5f6g7h8i9) in environments where they ran. Dropping them here would break
    those environments.

    If you need to fully reverse this migration, manually drop the tables/columns
    after verifying they were created by this backfill migration and not the originals.
    """
    pass
