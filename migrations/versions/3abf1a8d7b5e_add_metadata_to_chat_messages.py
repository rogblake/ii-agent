"""add metadata to chat_messages

Revision ID: 3abf1a8d7b5e
Revises: 2e8b1c9a7d66
Create Date: 2025-12-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3abf1a8d7b5e"
down_revision: Union[str, None] = "2e8b1c9a7d66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add metadata column for general message metadata (non-provider specific)."""
    op.add_column(
        "chat_messages",
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    """Remove metadata column."""
    op.drop_column("chat_messages", "metadata")
