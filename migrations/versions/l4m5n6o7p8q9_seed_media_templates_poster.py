"""seed_media_templates_poster

Revision ID: l4m5n6o7p8q9
Revises: k4l5m6n7o8p9
Create Date: 2026-02-12 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "l4m5n6o7p8q9"
down_revision: Union[str, None] = "k4l5m6n7o8p9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed poster media templates."""
    op.execute(
        """
        INSERT INTO public.media_templates (id, name, preview, type, prompt, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'Poster 1', 'generate-media/poster/poster-1.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 2', 'generate-media/poster/poster-2.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 3', 'generate-media/poster/poster-3.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 4', 'generate-media/poster/poster-4.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 5', 'generate-media/poster/poster-5.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 6', 'generate-media/poster/poster-6.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 7', 'generate-media/poster/poster-7.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 8', 'generate-media/poster/poster-8.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 9', 'generate-media/poster/poster-9.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 10', 'generate-media/poster/poster-10.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 11', 'generate-media/poster/poster-11.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 12', 'generate-media/poster/poster-12.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 13', 'generate-media/poster/poster-13.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 14', 'generate-media/poster/poster-14.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 15', 'generate-media/poster/poster-15.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 16', 'generate-media/poster/poster-16.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 17', 'generate-media/poster/poster-17.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 18', 'generate-media/poster/poster-18.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 19', 'generate-media/poster/poster-19.png', 'poster', '', now(), null),
            (gen_random_uuid(), 'Poster 20', 'generate-media/poster/poster-20.png', 'poster', '', now(), null);
        """
    )


def downgrade() -> None:
    """Remove poster media templates."""
    op.execute(
        """
        DELETE FROM public.media_templates
        WHERE type = 'poster';
        """
    )
