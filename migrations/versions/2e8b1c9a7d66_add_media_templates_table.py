"""add media_templates table

Revision ID: 2e8b1c9a7d66
Revises: 11e415a01c38
Create Date: 2025-12-15 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2e8b1c9a7d66"
down_revision: Union[str, None] = "11e415a01c38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "media_templates",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("preview", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "idx_media_templates_name",
        "media_templates",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_media_templates_name", table_name="media_templates")
    op.drop_table("media_templates")
