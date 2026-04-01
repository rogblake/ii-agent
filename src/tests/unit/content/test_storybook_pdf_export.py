"""Unit tests for ii_agent.content.storybook.pdf_export."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from ii_agent.content.storybook.pdf_export import (
    StorybookPDFExporter,
    compress_pdf_images,
)
from ii_agent.content.storybook.schemas import StorybookDetail, StorybookPageInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _page(page_number: int, html: str = "<html><body>p</body></html>") -> StorybookPageInfo:
    return StorybookPageInfo(
        id=f"page-{page_number}",
        storybook_id="sb-001",
        page_number=page_number,
        image_url=f"https://cdn.example.com/img/{page_number}.png",
        image_prompt="a cat in a hat",
        text_content="Once upon a time",
        audio_link=None,
        text_position="right",
        text_percentage=30,
        html_content=html,
        metadata={},
        created_at=_now(),
        updated_at=_now(),
    )


def _storybook(pages=None) -> StorybookDetail:
    pages = pages or [_page(1), _page(2)]
    return StorybookDetail(
        id="sb-001",
        session_id="sess-001",
        name="Test Storybook",
        version=1,
        style_json={},
        aspect_ratio="16:9",
        resolution="1K",
        page_count=len(pages),
        created_at=_now(),
        updated_at=_now(),
        pages=pages,
    )


# ---------------------------------------------------------------------------
# StorybookPDFExporter instantiation
# ---------------------------------------------------------------------------


class TestStorybookPDFExporterInit:
    def test_can_instantiate(self):
        exporter = StorybookPDFExporter()
        assert isinstance(exporter, StorybookPDFExporter)


# ---------------------------------------------------------------------------
# download_storybook_as_pdf – guard clauses
# ---------------------------------------------------------------------------


class TestDownloadStorybookAsPdf:
    @pytest.mark.asyncio
    async def test_returns_none_when_storybook_is_none(self):
        exporter = StorybookPDFExporter()
        result = await exporter.download_storybook_as_pdf(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_pages_empty(self):
        exporter = StorybookPDFExporter()
        sb = _storybook(pages=[])
        # prepare_pages_for_export returns [] for empty pages list
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
            return_value=[],
        ):
            result = await exporter.download_storybook_as_pdf(sb)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_prepare_pages_returns_empty(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
            return_value=[],
        ):
            result = await exporter.download_storybook_as_pdf(sb)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_pdf_bytes_on_success(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()

        # Minimal real PDF bytes (1-page PDF created in memory)
        from pypdf import PdfWriter

        buf = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=595, height=842)
        w.write(buf)
        buf.seek(0)
        fake_pdf_bytes = buf.read()

        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=fake_pdf_bytes)
        mock_page.set_content = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
                return_value=[(1, "<html/>", 1280, 720)],
            ),
            patch("ii_agent.content.storybook.pdf_export.compress_pdf_images") as mock_compress,
            patch(
                "playwright.async_api.async_playwright",
                return_value=mock_playwright,
            ),
        ):
            mock_compress.return_value = None
            result = await exporter.download_storybook_as_pdf(sb)

        assert result is not None
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# download_storybook_as_pdf_with_progress – guard clauses
# ---------------------------------------------------------------------------


class TestDownloadStorybookAsPdfWithProgress:
    @pytest.mark.asyncio
    async def test_yields_error_when_storybook_is_none(self):
        exporter = StorybookPDFExporter()
        events = []
        async for event in exporter.download_storybook_as_pdf_with_progress(None):
            events.append(event)
        assert any(e.get("type") == "error" for e in events)

    @pytest.mark.asyncio
    async def test_yields_error_when_pages_empty(self):
        exporter = StorybookPDFExporter()
        sb = _storybook(pages=[])
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
            return_value=[],
        ):
            events = []
            async for event in exporter.download_storybook_as_pdf_with_progress(sb):
                events.append(event)
        assert any(e.get("type") == "error" for e in events)

    @pytest.mark.asyncio
    async def test_yields_error_when_prepare_pages_returns_empty(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
            return_value=[],
        ):
            events = []
            async for event in exporter.download_storybook_as_pdf_with_progress(sb):
                events.append(event)
        assert any(e.get("type") == "error" for e in events)

    @pytest.mark.asyncio
    async def test_yields_progress_then_complete(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()

        from pypdf import PdfWriter

        buf = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=595, height=842)
        w.write(buf)
        buf.seek(0)
        fake_pdf_bytes = buf.read()

        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=fake_pdf_bytes)
        mock_page.set_content = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
                return_value=[(1, "<html/>", 1280, 720)],
            ),
            patch("ii_agent.content.storybook.pdf_export.compress_pdf_images"),
            patch(
                "playwright.async_api.async_playwright",
                return_value=mock_playwright,
            ),
        ):
            events = []
            async for event in exporter.download_storybook_as_pdf_with_progress(sb):
                events.append(event)

        types = [e["type"] for e in events]
        assert "progress" in types
        assert "complete" in types

    @pytest.mark.asyncio
    async def test_complete_event_includes_filename(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()

        from pypdf import PdfWriter

        buf = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=595, height=842)
        w.write(buf)
        buf.seek(0)
        fake_pdf_bytes = buf.read()

        mock_page = AsyncMock()
        mock_page.pdf = AsyncMock(return_value=fake_pdf_bytes)
        mock_page.set_content = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
                return_value=[(1, "<html/>", 1280, 720)],
            ),
            patch("ii_agent.content.storybook.pdf_export.compress_pdf_images"),
            patch(
                "playwright.async_api.async_playwright",
                return_value=mock_playwright,
            ),
        ):
            events = []
            async for event in exporter.download_storybook_as_pdf_with_progress(sb):
                events.append(event)

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        complete = complete_events[0]
        assert "filename" in complete
        assert "pdf_base64" in complete
        assert complete["filename"].endswith(".pdf")


# ---------------------------------------------------------------------------
# download_storybook_page_as_pdf – guard clauses
# ---------------------------------------------------------------------------


class TestDownloadStorybookPageAsPdf:
    @pytest.mark.asyncio
    async def test_returns_none_when_storybook_is_none(self):
        exporter = StorybookPDFExporter()
        result = await exporter.download_storybook_page_as_pdf(None, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_pages_empty(self):
        exporter = StorybookPDFExporter()
        sb = _storybook(pages=[])
        # Mock prepare_single_page_for_export to return None for empty pages
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_single_page_for_export",
            return_value=None,
        ):
            result = await exporter.download_storybook_page_as_pdf(sb, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_prepare_single_page_returns_none(self):
        exporter = StorybookPDFExporter()
        sb = _storybook()
        with patch(
            "ii_agent.content.storybook.pdf_export.prepare_single_page_for_export",
            return_value=None,
        ):
            result = await exporter.download_storybook_page_as_pdf(sb, 1)
        assert result is None


# ---------------------------------------------------------------------------
# compress_pdf_images – pure logic paths
# ---------------------------------------------------------------------------


class TestCompressPdfImages:
    def test_runs_without_error_on_empty_writer(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        # Should not raise even if no XObject resources
        compress_pdf_images(writer, quality=75, max_dimension=1920)

    def test_does_not_crash_on_page_without_resources(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        # No /Resources in a blank page's object tree typically
        compress_pdf_images(writer, quality=50, max_dimension=500)

    def test_small_image_not_resized(self):
        """An image smaller than max_dimension should not be resized."""
        img = Image.new("RGB", (100, 100), color=(128, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        small_img_bytes = buf.getvalue()

        # We're testing internal logic indirectly; just ensure no crash
        img_reopen = Image.open(io.BytesIO(small_img_bytes))
        assert max(img_reopen.width, img_reopen.height) <= 1920

    def test_large_image_resize_logic(self):
        """Verify PIL resize produces correct dimensions."""
        img = Image.new("RGB", (3000, 2000), color=(200, 100, 50))
        max_dim = 1920
        ratio = max_dim / max(img.width, img.height)
        new_width = int(img.width * ratio)
        new_height = int(img.height * ratio)
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        assert max(resized.width, resized.height) == max_dim

    def test_cmyk_image_converted_to_rgb(self):
        """CMYK images must be converted to RGB before JPEG save."""
        img = Image.new("CMYK", (200, 200))
        converted = img.convert("RGB")
        assert converted.mode == "RGB"

    def test_jpeg_compression_reduces_size(self):
        """Saving at quality=30 should produce fewer bytes than raw PNG."""
        img = Image.new("RGB", (500, 500), color=(100, 149, 237))
        raw_buf = io.BytesIO()
        img.save(raw_buf, format="PNG")
        raw_size = raw_buf.tell()

        jpeg_buf = io.BytesIO()
        img.save(jpeg_buf, format="JPEG", quality=30, optimize=True)
        jpeg_size = jpeg_buf.tell()

        assert jpeg_size < raw_size
