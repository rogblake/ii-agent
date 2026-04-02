"""make snapshot_id nullable in project_deployments

Revision ID: m5n6o7p8q9r0
Revises: l4m5n6o7p8q9
Create Date: 2026-02-20 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m5n6o7p8q9r0"
down_revision: Union[str, None] = "l4m5n6o7p8q9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "project_deployments",
        "snapshot_id",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "project_deployments",
        "snapshot_id",
        existing_type=sa.String(),
        nullable=False,
    )
