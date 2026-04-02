"""merge develop and feature heads

Revision ID: a4662ddf3ec4
Revises: 8c4d5a2f7b9c, ab143e0e2ac4
Create Date: 2025-12-29 22:17:14.945078

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4662ddf3ec4'
down_revision: Union[str, None] = ('8c4d5a2f7b9c', 'ab143e0e2ac4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
