"""Repository layer for Nano Banana design mode - data access only."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from html import escape as html_escape
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.slides.models import SlideContent, SlideVersion
from ii_agent.content.slides.repository import SlideContentRepository
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository

from .schemas import Instruction


class NanoBananaRepository:
    """Data access facade for Nano Banana workflows.

    Composes existing session/slide repositories and adds SlideVersion CRUD.
    """

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        slide_repo: SlideContentRepository,
    ) -> None:
        self._session_repo = session_repo
        self._slide_repo = slide_repo

    async def validate_session_access(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
    ) -> Session:
        """Validate user has access to the session. Raises if not found or denied."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            from ii_agent.projects.design.exceptions import (
                DesignSessionAccessDeniedError,
                DesignSessionNotFoundError,
            )

            # Check if session exists at all
            exists = await self._session_repo.get_by_id(db, session_id)
            if not exists:
                raise DesignSessionNotFoundError(f"Session {session_id} not found")
            raise DesignSessionAccessDeniedError(
                f"User does not have access to session {session_id}"
            )
        return session

    async def get_slide(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
    ) -> Optional[SlideContent]:
        """Get a specific slide by session, presentation, and number."""
        return await self._slide_repo.get_by_session_and_presentation_and_number(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
        )

    async def update_slide_content_image(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
        image_url: str,
    ) -> bool:
        """Update SlideContent with a new image URL.

        Returns True if updated successfully.
        """
        slide = await self._slide_repo.get_by_session_and_presentation_and_number(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
        )

        if not slide:
            return False

        new_html = _create_image_slide_html(
            image_url=image_url,
            title=slide.slide_title or f"Slide {slide_number}",
            slide_number=slide_number,
        )

        slide.slide_content = new_html
        slide.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return True

    # ==================== SlideVersion CRUD ====================

    async def create_version(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
        image_url: str,
        instructions: Optional[List[Instruction]] = None,
        edit_summary: Optional[str] = None,
    ) -> SlideVersion:
        """Create a new version record for a slide."""
        # Find existing versions to determine root and next version number
        stmt = (
            select(SlideVersion)
            .where(
                and_(
                    SlideVersion.session_id == session_id,
                    SlideVersion.presentation_name == presentation_name,
                    SlideVersion.slide_number == slide_number,
                )
            )
            .order_by(SlideVersion.version.desc())
        )
        result = await db.execute(stmt)
        existing_versions = result.scalars().all()

        if existing_versions:
            latest = existing_versions[0]
            next_version = latest.version + 1
            root_id = latest.root_version_id or latest.id
            parent_id = latest.id
        else:
            next_version = 1
            root_id = None
            parent_id = None

        version = SlideVersion(
            id=str(uuid.uuid4()),
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
            version=next_version,
            root_version_id=root_id,
            parent_version_id=parent_id,
            image_url=image_url,
            edit_summary=edit_summary,
            instructions_applied=(
                [inst.model_dump() for inst in instructions] if instructions else None
            ),
        )

        # If this is the first version, set root to self
        if root_id is None:
            version.root_version_id = version.id

        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version

    async def get_versions(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
    ) -> List[SlideVersion]:
        """Get all versions for a slide, ordered by version number descending."""
        stmt = (
            select(SlideVersion)
            .where(
                and_(
                    SlideVersion.session_id == session_id,
                    SlideVersion.presentation_name == presentation_name,
                    SlideVersion.slide_number == slide_number,
                )
            )
            .order_by(SlideVersion.version.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_version_by_id(
        self,
        db: AsyncSession,
        *,
        version_id: str,
    ) -> Optional[SlideVersion]:
        """Get a specific version by ID."""
        stmt = select(SlideVersion).where(SlideVersion.id == version_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# ============ HTML Helpers ============


def _create_image_slide_html(image_url: str, title: str, slide_number: int) -> str:
    """Create HTML wrapper for a regenerated image slide.

    Same format as SlideGenerationTool._create_image_slide_html() for compatibility.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="slide-type" content="image">
    <meta name="slide-number" content="{slide_number}">
    <title>{html_escape(title)}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            width: 1280px;
            height: 720px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000;
        }}
        .slide-image {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
    </style>
</head>
<body data-is-image-slide="true" data-image-url="{html_escape(image_url, quote=True)}">
    <img src="{html_escape(image_url, quote=True)}" alt="{html_escape(title)}" class="slide-image" />
</body>
</html>"""


def extract_image_url_from_slide_html(html: str) -> Optional[str]:
    """Extract the image URL from a nano banana slide's HTML content."""
    import re

    # Try data-image-url attribute first
    match = re.search(r'data-image-url="([^"]+)"', html)
    if match:
        return match.group(1)

    # Fallback: try img src
    match = re.search(r'<img[^>]+src="([^"]+)"', html)
    if match:
        return match.group(1)

    return None
