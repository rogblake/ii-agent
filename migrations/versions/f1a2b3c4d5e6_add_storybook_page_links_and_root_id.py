"""Add storybook page links, root_storybook_id, and cleanup unused columns.

This migration:
1. Creates storybook_page_links table (without created_at - not needed)
2. Removes storybook_id from storybook_pages (replaced by link table)
3. Adds root_storybook_id to storybooks for version family tracking
4. Removes page_count from storybooks (computed from linked pages)
5. Removes unused columns from storybook_pages:
   - image_prompt (only used for unused regenerate feature)
   - text_content (only used as fallback, html_content is primary)
   - text_position (only used during initial HTML generation)
   - text_percentage (only used during initial HTML generation)

Revision ID: f1a2b3c4d5e6
Revises: f3g4h5i6j7k8
Create Date: 2026-01-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "f3g4h5i6j7k8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create storybook_page_links, add root_storybook_id, remove unused columns."""
    # 1. Create storybook_page_links table (no created_at needed)
    op.create_table(
        "storybook_page_links",
        sa.Column("storybook_id", sa.String(), nullable=False),
        sa.Column("page_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["storybook_id"], ["storybooks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], ["storybook_pages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("storybook_id", "page_id"),
    )

    op.create_index(
        "idx_storybook_page_links_storybook_id",
        "storybook_page_links",
        ["storybook_id"],
    )
    op.create_index(
        "idx_storybook_page_links_page_id",
        "storybook_page_links",
        ["page_id"],
    )

    # 2. Remove storybook_id from storybook_pages (replaced by link table)
    op.drop_index("idx_storybook_pages_storybook_page", table_name="storybook_pages")
    op.drop_index("idx_storybook_pages_storybook_id", table_name="storybook_pages")
    op.drop_column("storybook_pages", "storybook_id")

    op.create_index(
        "idx_storybook_pages_page_number",
        "storybook_pages",
        ["page_number"],
    )

    # 3. Add root_storybook_id column
    op.add_column(
        "storybooks",
        sa.Column("root_storybook_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "storybooks_root_storybook_id_fkey",
        "storybooks",
        "storybooks",
        ["root_storybook_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_storybooks_root_id", "storybooks", ["root_storybook_id"])

    # 4. Remove page_count from storybooks (computed from linked pages)
    op.drop_column("storybooks", "page_count")

    # 5. Remove unused columns from storybook_pages
    op.drop_column("storybook_pages", "image_prompt")
    op.drop_column("storybook_pages", "text_content")
    op.drop_column("storybook_pages", "text_position")
    op.drop_column("storybook_pages", "text_percentage")


def downgrade() -> None:
    """Restore all changes."""
    # Restore unused columns to storybook_pages
    op.add_column(
        "storybook_pages",
        sa.Column("image_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "storybook_pages",
        sa.Column("text_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "storybook_pages",
        sa.Column(
            "text_position",
            sa.String(),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "storybook_pages",
        sa.Column(
            "text_percentage",
            sa.BigInteger(),
            nullable=False,
            server_default="30",
        ),
    )

    # Restore page_count to storybooks
    op.add_column(
        "storybooks",
        sa.Column(
            "page_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # Drop root_storybook_id
    op.drop_index("idx_storybooks_root_id", table_name="storybooks")
    op.drop_constraint(
        "storybooks_root_storybook_id_fkey", "storybooks", type_="foreignkey"
    )
    op.drop_column("storybooks", "root_storybook_id")

    # Drop storybook_page_links
    op.drop_index(
        "idx_storybook_page_links_page_id", table_name="storybook_page_links"
    )
    op.drop_index(
        "idx_storybook_page_links_storybook_id", table_name="storybook_page_links"
    )
    op.drop_table("storybook_page_links")

    # Restore storybook_id on pages
    op.drop_index("idx_storybook_pages_page_number", table_name="storybook_pages")
    op.add_column(
        "storybook_pages",
        sa.Column("storybook_id", sa.String(), nullable=False),
    )
    op.create_foreign_key(
        "storybook_pages_storybook_id_fkey",
        "storybook_pages",
        "storybooks",
        ["storybook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_storybook_pages_storybook_id", "storybook_pages", ["storybook_id"]
    )
    op.create_index(
        "idx_storybook_pages_storybook_page",
        "storybook_pages",
        ["storybook_id", "page_number"],
        unique=True,
    )
