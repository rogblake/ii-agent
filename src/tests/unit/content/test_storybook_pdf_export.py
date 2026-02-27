from __future__ import annotations

import io
import sys
import types
from datetime import datetime, timezone

import pytest

from ii_agent.content.storybook.pdf_export import StorybookPDFExporter
from ii_agent.content.storybook.schemas import StorybookDetail, StorybookPageInfo


def _storybook_with_pages(page_html: str = "<html><body>p</body></html>") -> StorybookDetail:
    page = StorybookPageInfo(
        id="p1",
        storybook_id="sb1",
        page_number=1,
        html_content=page_html,
        image_url="https://example.com/1.png",
        image_prompt="prompt",
        text_content="text",
        text_position="none",
        text_percentage=30,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return StorybookDetail(
        id="sb1",
        session_id="session-1",
        name="My Storybook",
        aspect_ratio="1:1",
        resolution="1K",
        version=1,
        pages=[page],
        page_count=1,
    )


def _install_fake_export_runtime(monkeypatch, *, pdf_bytes: bytes = b"%PDF-fake"):
    class _FakePage:
        async def wait_for_load_state(self, *_args, **_kwargs):
            return None

        async def set_content(self, *_args, **_kwargs):
            return None

        async def evaluate(self, *_args, **_kwargs):
            return None

        async def pdf(self, **_kwargs):
            return b"raw-page-pdf"

        async def close(self):
            return None

    class _FakeContext:
        async def new_page(self):
            return _FakePage()

        async def close(self):
            return None

    class _FakeBrowser:
        async def new_context(self, **_kwargs):
            return _FakeContext()

        async def close(self):
            return None

    class _FakeChromium:
        async def launch(self, headless=True):
            return _FakeBrowser()

    class _FakePlaywright:
        chromium = _FakeChromium()

    class _PlaywrightCM:
        async def __aenter__(self):
            return _FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakePdfPage:
        def compress_content_streams(self):
            return None

    class _FakePdfReader:
        def __init__(self, _buffer):
            self.pages = [_FakePdfPage()]

    class _FakePdfWriter:
        def __init__(self):
            self.pages = []

        def add_page(self, page):
            self.pages.append(page)

        def compress_identical_objects(self, **_kwargs):
            return None

        def write(self, output):
            output.write(pdf_bytes)

    playwright_module = types.ModuleType("playwright.async_api")
    playwright_module.async_playwright = lambda: _PlaywrightCM()
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_module)

    pypdf_module = types.ModuleType("pypdf")
    pypdf_module.PdfWriter = _FakePdfWriter
    pypdf_module.PdfReader = _FakePdfReader
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_returns_none_when_missing_pages():
    exporter = StorybookPDFExporter()
    empty = StorybookDetail(
        id="sb1",
        session_id="s1",
        name="Empty",
        aspect_ratio="1:1",
        resolution="1K",
        version=1,
        pages=[],
        page_count=0,
    )

    assert await exporter.download_storybook_as_pdf(empty) is None


@pytest.mark.asyncio
async def test_download_storybook_page_as_pdf_returns_none_for_missing_export_data(monkeypatch):
    exporter = StorybookPDFExporter()
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.prepare_single_page_for_export",
        lambda *args, **kwargs: None,
    )

    result = await exporter.download_storybook_page_as_pdf(_storybook_with_pages(), 1)
    assert result is None


@pytest.mark.asyncio
async def test_download_storybook_page_as_pdf_success(monkeypatch):
    exporter = StorybookPDFExporter()
    _install_fake_export_runtime(monkeypatch, pdf_bytes=b"%PDF-page")
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.prepare_single_page_for_export",
        lambda pages, page_number, aspect_ratio, resolution: (
            "<html><body>page</body></html>",
            800,
            600,
        ),
    )
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.compress_pdf_images",
        lambda *args, **kwargs: None,
    )

    payload = await exporter.download_storybook_page_as_pdf(_storybook_with_pages(), 1)
    assert isinstance(payload, bytes)
    assert payload.startswith(b"%PDF-page")


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_success(monkeypatch):
    exporter = StorybookPDFExporter()
    _install_fake_export_runtime(monkeypatch, pdf_bytes=b"%PDF-merged")
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
        lambda pages, aspect_ratio, resolution: [(1, "<html><body>ok</body></html>", 800, 600)],
    )
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.compress_pdf_images",
        lambda *args, **kwargs: None,
    )

    data = await exporter.download_storybook_as_pdf(_storybook_with_pages())

    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF-merged")


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_with_progress_reports_error_for_empty():
    exporter = StorybookPDFExporter()
    empty = StorybookDetail(
        id="sb1",
        session_id="s1",
        name="Empty",
        aspect_ratio="1:1",
        resolution="1K",
        version=1,
        pages=[],
        page_count=0,
    )

    events = [event async for event in exporter.download_storybook_as_pdf_with_progress(empty)]
    assert events == [{"type": "error", "message": "Storybook not found or has no pages"}]


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_with_progress_success(monkeypatch):
    exporter = StorybookPDFExporter()
    _install_fake_export_runtime(monkeypatch, pdf_bytes=b"%PDF-progress")
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.prepare_pages_for_export",
        lambda pages, aspect_ratio, resolution: [(1, "<html><body>ok</body></html>", 800, 600)],
    )
    monkeypatch.setattr(
        "ii_agent.content.storybook.pdf_export.compress_pdf_images",
        lambda *args, **kwargs: None,
    )

    events = [
        event
        async for event in exporter.download_storybook_as_pdf_with_progress(
            _storybook_with_pages()
        )
    ]

    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "complete"
    assert events[-1]["filename"].endswith(".pdf")
