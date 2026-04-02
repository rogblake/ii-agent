"""add_conversation_summaries_table

Revision ID: 11e415a01c38
Revises: f7g8h9i0j1k2
Create Date: 2025-12-04 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "11e415a01c38"
down_revision: Union[str, None] = "f7g8h9i0j1k2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("end_message_id", sa.String(), nullable=False),
        sa.Column("parent_summary_id", sa.String(), nullable=True),
        sa.Column("original_tokens", sa.Integer(), nullable=False),
        sa.Column("summary_tokens", sa.Integer(), nullable=False),
        sa.Column("compression_ratio", sa.Float(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_summary_id"],
            ["conversation_summaries.id"],
            ondelete="SET NULL",
        ),
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_conversation_summaries_session",
        "conversation_summaries",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_summaries_session_created",
        "conversation_summaries",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_summaries_end_message",
        "conversation_summaries",
        ["end_message_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_conversation_summaries_end_message",
        table_name="conversation_summaries",
    )
    op.drop_index(
        "idx_conversation_summaries_session_created",
        table_name="conversation_summaries",
    )
    op.drop_index(
        "idx_conversation_summaries_session",
        table_name="conversation_summaries",
    )
    op.drop_table("conversation_summaries")
