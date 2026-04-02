"""add_storybook_page_audio_and_text

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-01-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add text_content and audio_link columns to storybook_pages."""
    op.add_column("storybook_pages", sa.Column("text_content", sa.Text(), nullable=True))
    op.add_column("storybook_pages", sa.Column("audio_link", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove text_content and audio_link columns from storybook_pages."""
    op.drop_column("storybook_pages", "audio_link")
    op.drop_column("storybook_pages", "text_content")
