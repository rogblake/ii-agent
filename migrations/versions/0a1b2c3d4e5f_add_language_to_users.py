"""Add language column to users table

Revision ID: 0a1b2c3d4e5f
Revises: d4e5f6g7h8i9
Create Date: 2026-01-09 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add language column to users table."""
    op.add_column(
        "users",
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    """Remove language column from users table."""
    op.drop_column("users", "language")
