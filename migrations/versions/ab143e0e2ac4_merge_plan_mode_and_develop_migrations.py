"""merge plan mode and develop migrations

Revision ID: ab143e0e2ac4
Revises: 3f4e6d8c0b1b, a2b3c4d5e6f7
Create Date: 2025-12-25 10:40:17.661740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab143e0e2ac4'
down_revision: Union[str, None] = ('3f4e6d8c0b1b', 'a2b3c4d5e6f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
