"""add_parent_run_id_to_agent_run_messages

Revision ID: g4h5i6j7k8l9
Revises: c5a87195d092
Create Date: 2025-01-27 10:00:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, None] = "c5a87195d092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: parent_run_id is now included in the create_table in c3d4e5f6g7h8."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
