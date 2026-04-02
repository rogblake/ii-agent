"""Add production_url and enforce single project per session.

Revision ID: c7f1b8e43d9e
Revises: a1b2c3d4e5f7
Create Date: 2025-01-15 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7f1b8e43d9e"
down_revision: Union[str, Sequence[str], None] = "11e415a01c38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add production_url and make session_id unique."""
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("production_url", sa.String(), nullable=True))
        batch_op.drop_index("idx_projects_session_id")
        batch_op.create_unique_constraint("uq_projects_session_id", ["session_id"])


def downgrade() -> None:
    """Drop unique constraint and production_url."""
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint("uq_projects_session_id", type_="unique")
        batch_op.create_index("idx_projects_session_id", ["session_id"])
        batch_op.drop_column("production_url")
