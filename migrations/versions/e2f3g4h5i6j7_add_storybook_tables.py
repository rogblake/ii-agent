"""Add storybook tables for versioning and editing support

Revision ID: e2f3g4h5i6j7
Revises: c1d2e3f4g5h6
Create Date: 2026-01-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create storybooks and storybook_pages tables."""
    # Create storybooks table
    op.create_table(
        "storybooks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("parent_storybook_id", sa.String(), nullable=True),
        sa.Column("style_json", JSONB(), nullable=True),
        sa.Column("aspect_ratio", sa.String(), nullable=False, server_default="1:1"),
        sa.Column("resolution", sa.String(), nullable=False, server_default="1K"),
        sa.Column("page_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_storybook_id"],
            ["storybooks.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for storybooks
    op.create_index("idx_storybooks_session_id", "storybooks", ["session_id"])
    op.create_index("idx_storybooks_parent_id", "storybooks", ["parent_storybook_id"])
    op.create_index("idx_storybooks_created_at", "storybooks", ["created_at"])

    # Create storybook_pages table
    op.create_table(
        "storybook_pages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("storybook_id", sa.String(), nullable=False),
        sa.Column("page_number", sa.BigInteger(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("text_position", sa.String(), nullable=False, server_default="none"),
        sa.Column("text_percentage", sa.BigInteger(), nullable=False, server_default="30"),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["storybook_id"],
            ["storybooks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for storybook_pages
    op.create_index("idx_storybook_pages_storybook_id", "storybook_pages", ["storybook_id"])
    op.create_index(
        "idx_storybook_pages_storybook_page",
        "storybook_pages",
        ["storybook_id", "page_number"],
        unique=True,
    )


def downgrade() -> None:
    """Drop storybook tables."""
    op.drop_index("idx_storybook_pages_storybook_page", table_name="storybook_pages")
    op.drop_index("idx_storybook_pages_storybook_id", table_name="storybook_pages")
    op.drop_table("storybook_pages")

    op.drop_index("idx_storybooks_created_at", table_name="storybooks")
    op.drop_index("idx_storybooks_parent_id", table_name="storybooks")
    op.drop_index("idx_storybooks_session_id", table_name="storybooks")
    op.drop_table("storybooks")
