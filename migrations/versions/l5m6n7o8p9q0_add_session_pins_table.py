"""Add session_pins table

Revision ID: l5m6n7o8p9q0
Revises: n6o7p8q9r0s1
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "l5m6n7o8p9q0"
down_revision: Union[str, None] = "n6o7p8q9r0s1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table already exists in the database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name: str, table_name: str) -> bool:
    """Check if an index already exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Create session_pins table."""
    if not table_exists("session_pins"):
        op.create_table(
            "session_pins",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["session_id"], ["sessions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if not index_exists("idx_session_pins_user_session", "session_pins"):
        op.create_index(
            "idx_session_pins_user_session",
            "session_pins",
            ["user_id", "session_id"],
            unique=True,
        )


def downgrade() -> None:
    """Drop session_pins table."""
    op.drop_index("idx_session_pins_user_session", table_name="session_pins")
    op.drop_table("session_pins")
