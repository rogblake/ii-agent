"""Add project_databases table for database connection management.

Revision ID: c5a87195d092
Revises: 3a32c9ff5c2b
Create Date: 2026-01-26 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoSuchTableError

# revision identifiers, used by Alembic.
revision: str = "c5a87195d092"
down_revision: Union[str, None] = "3a32c9ff5c2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_inspector():
    return sa.inspect(op.get_bind())


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    try:
        indexes = inspector.get_indexes(table_name)
    except NoSuchTableError:
        return False
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    """Create project_databases table and migrate data from database_json."""

    inspector = _get_inspector()

    # Create project_databases table
    if not _table_exists(inspector, "project_databases"):
        op.create_table(
            "project_databases",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default="neondb",
            ),
            sa.Column("connection_string", sa.String(), nullable=False),
            sa.Column("host", sa.String(), nullable=True),
            sa.Column("database_name", sa.String(), nullable=True),
            sa.Column("role_name", sa.String(), nullable=True),
            sa.Column("branch_name", sa.String(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # Create indexes
    inspector = _get_inspector()
    if not _index_exists(inspector, "project_databases", "idx_project_databases_session_id"):
        op.create_index(
            "idx_project_databases_session_id",
            "project_databases",
            ["session_id"],
        )
    if not _index_exists(inspector, "project_databases", "idx_project_databases_source"):
        op.create_index(
            "idx_project_databases_source",
            "project_databases",
            ["source"],
        )
    if not _index_exists(inspector, "project_databases", "idx_project_databases_is_active"):
        op.create_index(
            "idx_project_databases_is_active",
            "project_databases",
            ["is_active"],
        )

    # Migrate existing data from database_json to project_databases
    # This is a data migration that extracts connection info from the JSONB column
    conn = op.get_bind()

    # Query projects with non-null database_json
    result = conn.execute(
        sa.text("""
            SELECT
                p.id as project_id,
                p.session_id,
                p.database_json
            FROM projects p
            WHERE p.database_json IS NOT NULL
              AND p.session_id IS NOT NULL
              AND p.deleted_at IS NULL
        """)
    )

    import json
    import uuid
    from datetime import datetime, timezone

    for row in result:
        db_json = row.database_json
        if not isinstance(db_json, dict):
            continue

        # Extract connection_string from various possible keys
        connection_string = None
        for key in ("connection_string", "connection_url", "connection_uri", "uri", "url", "dsn"):
            value = db_json.get(key)
            if isinstance(value, str) and value:
                connection_string = value
                break

        if not connection_string:
            continue

        # Check if a database record already exists for this session
        existing = conn.execute(
            sa.text("""
                SELECT id FROM project_databases
                WHERE session_id = :session_id AND is_active = true
            """),
            {"session_id": row.session_id},
        ).fetchone()

        if existing:
            continue

        # Insert new record
        conn.execute(
            sa.text("""
                INSERT INTO project_databases (
                    id, session_id, source, connection_string, host,
                    database_name, role_name, branch_name, is_active, metadata,
                    created_at, updated_at
                ) VALUES (
                    :id, :session_id, :source, :connection_string, :host,
                    :database_name, :role_name, :branch_name, :is_active, :metadata,
                    :created_at, :updated_at
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "session_id": row.session_id,
                "source": "neondb",
                "connection_string": connection_string,
                "host": db_json.get("host"),
                "database_name": db_json.get("database_name"),
                "role_name": db_json.get("role_name"),
                "branch_name": db_json.get("branch_name"),
                "is_active": True,
                "metadata": json.dumps({
                    "project_id": db_json.get("project_id"),
                    "project_name": db_json.get("project_name"),
                    "is_new_project": db_json.get("is_new_project"),
                    "current_project_count": db_json.get("current_project_count"),
                    "databases_in_project": db_json.get("databases_in_project"),
                    "capacity_remaining": db_json.get("capacity_remaining"),
                    "original_database_name": db_json.get("original_database_name"),
                    "time_taken_ms": db_json.get("time_taken_ms"),
                    "migrated_from": "database_json",
                    "migrated_project_id": row.project_id,
                }),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )


def downgrade() -> None:
    """Drop project_databases table."""

    op.drop_index("idx_project_databases_is_active", table_name="project_databases")
    op.drop_index("idx_project_databases_source", table_name="project_databases")
    op.drop_index("idx_project_databases_session_id", table_name="project_databases")
    op.drop_table("project_databases")
