from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.content.storybook.export_service import StorybookExportService


class FakePDFExporter:
    def __init__(self):
        self.calls = []

    async def download_storybook_as_pdf(self, storybook):
        self.calls.append(("download_storybook_as_pdf", storybook))
        return b"pdf-bytes"

    async def download_storybook_page_as_pdf(self, storybook, page_number):
        self.calls.append(("download_storybook_page_as_pdf", storybook, page_number))
        return b"page-pdf-bytes"

    async def download_storybook_as_pdf_with_progress(self, storybook):
        self.calls.append(("download_storybook_as_pdf_with_progress", storybook))
        for event in [{"type": "progress", "value": 50}, {"type": "done"}]:
            yield event


class FakePNGExporter:
    def __init__(self):
        self.calls = []

    async def download_storybook_page_as_png(self, storybook, page_number):
        self.calls.append(("download_storybook_page_as_png", storybook, page_number))
        return b"page-png-bytes"

    async def download_storybook_as_png_zip(self, storybook):
        self.calls.append(("download_storybook_as_png_zip", storybook))
        return b"zip-bytes"

    async def download_storybook_as_png_with_progress(self, storybook):
        self.calls.append(("download_storybook_as_png_with_progress", storybook))
        for event in [{"type": "progress", "value": 25}, {"type": "done"}]:
            yield event


def _service_with_exporters(storybook):
    storybook_service = SimpleNamespace(
        get_storybook_detail=AsyncMock(return_value=storybook)
    )
    service = StorybookExportService(storybook_service=storybook_service)
    service._pdf_exporter = FakePDFExporter()
    service._png_exporter = FakePNGExporter()
    return service, storybook_service


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_returns_none_when_missing_storybook():
    service, _ = _service_with_exporters(storybook=None)

    result = await service.download_storybook_as_pdf(db=None, storybook_id="sb-1")

    assert result is None


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_delegates_to_exporter():
    storybook = SimpleNamespace(pages=[{"page_number": 1}])
    service, storybook_service = _service_with_exporters(storybook=storybook)

    result = await service.download_storybook_as_pdf(db=None, storybook_id="sb-1")

    assert result == b"pdf-bytes"
    storybook_service.get_storybook_detail.assert_awaited_once()
    assert service._pdf_exporter.calls == [("download_storybook_as_pdf", storybook)]


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_with_progress_yields_error_when_empty():
    storybook = SimpleNamespace(pages=[])
    service, _ = _service_with_exporters(storybook=storybook)

    events = [
        event
        async for event in service.download_storybook_as_pdf_with_progress(
            db=None, storybook_id="sb-1"
        )
    ]

    assert events == [{"type": "error", "message": "Storybook not found or has no pages"}]


@pytest.mark.asyncio
async def test_download_storybook_as_pdf_with_progress_passes_through_exporter_events():
    storybook = SimpleNamespace(pages=[{"page_number": 1}])
    service, _ = _service_with_exporters(storybook=storybook)

    events = [
        event
        async for event in service.download_storybook_as_pdf_with_progress(
            db=None, storybook_id="sb-1"
        )
    ]

    assert events == [{"type": "progress", "value": 50}, {"type": "done"}]


@pytest.mark.asyncio
async def test_png_download_methods_delegate_to_png_exporter():
    storybook = SimpleNamespace(pages=[{"page_number": 1}])
    service, _ = _service_with_exporters(storybook=storybook)

    page_png = await service.download_storybook_page_as_png(
        db=None, storybook_id="sb-1", page_number=1
    )
    zip_bytes = await service.download_storybook_as_png_zip(db=None, storybook_id="sb-1")
    events = [
        event
        async for event in service.download_storybook_as_png_with_progress(
            db=None, storybook_id="sb-1"
        )
    ]

    assert page_png == b"page-png-bytes"
    assert zip_bytes == b"zip-bytes"
    assert events == [{"type": "progress", "value": 25}, {"type": "done"}]
    assert service._png_exporter.calls[0][0] == "download_storybook_page_as_png"
    assert service._png_exporter.calls[1][0] == "download_storybook_as_png_zip"
    assert service._png_exporter.calls[2][0] == "download_storybook_as_png_with_progress"


@pytest.mark.asyncio
async def test_download_storybook_page_as_pdf_returns_none_when_no_pages():
    storybook = SimpleNamespace(pages=[])
    service, _ = _service_with_exporters(storybook=storybook)

    result = await service.download_storybook_page_as_pdf(
        db=None, storybook_id="sb-1", page_number=1
    )

    assert result is None
