"""Storybook export service for PDF and PNG downloads."""

from __future__ import annotations

from typing import Optional, Dict, Any, AsyncGenerator, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.storybook.pdf_export import StorybookPDFExporter
from ii_agent.content.storybook.png_export import StorybookPNGExporter

if TYPE_CHECKING:
    from ii_agent.content.storybook.service import StorybookService


class StorybookExportService:
    """Service for exporting storybooks as PDF or PNG."""

    def __init__(self, *, storybook_service: StorybookService) -> None:
        self._storybook_service = storybook_service
        self._pdf_exporter = StorybookPDFExporter()
        self._png_exporter = StorybookPNGExporter()

    async def download_storybook_as_pdf(
        self, db: AsyncSession, storybook_id: str
    ) -> Optional[bytes]:
        """Download a storybook as PDF."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            return None
        return await self._pdf_exporter.download_storybook_as_pdf(storybook)

    async def download_storybook_as_pdf_with_progress(
        self, db: AsyncSession, storybook_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download a storybook as PDF with progress updates."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            yield {"type": "error", "message": "Storybook not found or has no pages"}
            return
        async for event in self._pdf_exporter.download_storybook_as_pdf_with_progress(storybook):
            yield event

    async def download_storybook_page_as_pdf(
        self, db: AsyncSession, storybook_id: str, page_number: int
    ) -> Optional[bytes]:
        """Download a single storybook page as PDF."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            return None
        return await self._pdf_exporter.download_storybook_page_as_pdf(storybook, page_number)

    async def download_storybook_page_as_png(
        self, db: AsyncSession, storybook_id: str, page_number: int
    ) -> Optional[bytes]:
        """Download a single storybook page as PNG."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            return None
        return await self._png_exporter.download_storybook_page_as_png(storybook, page_number)

    async def download_storybook_as_png_zip(
        self, db: AsyncSession, storybook_id: str
    ) -> Optional[bytes]:
        """Download all storybook pages as a ZIP of PNGs."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            return None
        return await self._png_exporter.download_storybook_as_png_zip(storybook)

    async def download_storybook_as_png_with_progress(
        self, db: AsyncSession, storybook_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download all storybook pages as a ZIP of PNGs with progress updates."""
        storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not storybook or not storybook.pages:
            yield {"type": "error", "message": "Storybook not found or has no pages"}
            return
        async for event in self._png_exporter.download_storybook_as_png_with_progress(storybook):
            yield event
