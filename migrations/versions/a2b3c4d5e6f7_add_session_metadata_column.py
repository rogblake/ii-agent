"""add_session_metadata_column

Revision ID: a2b3c4d5e6f7
Revises: 11e415a01c38
Create Date: 2025-12-10 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "11e415a01c38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_metadata column to sessions table."""
    op.add_column(
        "sessions",
        sa.Column(
            "session_metadata",
            postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove session_metadata column from sessions table."""
    op.drop_column("sessions", "session_metadata")
