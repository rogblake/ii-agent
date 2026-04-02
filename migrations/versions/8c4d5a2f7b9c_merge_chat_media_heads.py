"""Merge heads for chat/media branches

Revision ID: 8c4d5a2f7b9c
Revises: 3abf1a8d7b5e, 3f4e6d8c0b1b
Create Date: 2025-01-05 00:00:00

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "8c4d5a2f7b9c"
down_revision: Union[str, Sequence[str], None] = ("3abf1a8d7b5e", "3f4e6d8c0b1b")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge upgrade."""
    pass


def downgrade() -> None:
    """No-op merge downgrade."""
    pass
