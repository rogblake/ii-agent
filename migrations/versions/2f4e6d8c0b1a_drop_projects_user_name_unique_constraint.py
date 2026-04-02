"""Drop projects user/name unique constraint.

Revision ID: 2f4e6d8c0b1a
Revises: f668081cdee0
Create Date: 2025-09-22 16:10:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f4e6d8c0b1b"
down_revision: Union[str, Sequence[str], None] = "c7f1b8e43d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Drop projects user/name unique constraint."""
    op.drop_constraint("uq_projects_user_id_name", "projects", type_="unique")


def downgrade() -> None:
    """Restore projects user/name unique constraint."""
    op.create_unique_constraint(
        "uq_projects_user_id_name",
        "projects",
        ["user_id", "name"]
    )
