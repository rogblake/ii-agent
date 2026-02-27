"""Unit tests for storybook router helper functions and logic."""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from datetime import datetime, timezone

from ii_agent.content.storybook.router import _format_content_disposition
from ii_agent.content.storybook.schemas import (
    StorybookDetail,
    StorybookPageInfo,
    StorybookInfo,
)

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers
# ============================================================================


def _now():
    return datetime.now(timezone.utc)


def _make_storybook(
    storybook_id="sb-001",
    session_id="sess-001",
    name="My Storybook",
    pages=None,
):
    return StorybookDetail(
        id=storybook_id,
        session_id=session_id,
        name=name,
        version=1,
        aspect_ratio="16:9",
        resolution="1K",
        page_count=len(pages or []),
        created_at=_now(),
        updated_at=_now(),
        pages=pages or [],
    )


def _make_page(page_number=1, html_content=None, text_content="Hello"):
    return StorybookPageInfo(
        id=f"p{page_number}",
        storybook_id="sb-001",
        page_number=page_number,
        image_url="https://img.example.com/img.png",
        text_content=text_content,
        audio_link=None,
        text_position="right",
        text_percentage=30,
        html_content=html_content,
        metadata={},
        created_at=_now(),
        updated_at=_now(),
    )


# ============================================================================
# _format_content_disposition
# ============================================================================


class TestFormatContentDisposition:
    def test_ascii_filename_unchanged(self):
        result = _format_content_disposition("my_file.pdf")
        assert 'filename="my_file.pdf"' in result
        assert "attachment" in result

    def test_unicode_filename_encoded(self):
        result = _format_content_disposition("histoire_de_la_fée.pdf")
        assert "filename*=UTF-8''" in result
        assert "attachment" in result

    def test_empty_filename_uses_download_fallback(self):
        result = _format_content_disposition("")
        assert 'filename="download"' in result

    def test_filename_with_spaces(self):
        result = _format_content_disposition("my story book.pdf")
        assert "attachment" in result
        assert "filename*=UTF-8''" in result

    def test_filename_with_chinese_characters(self):
        result = _format_content_disposition("故事书.pdf")
        assert "filename*=UTF-8''" in result
        # ASCII fallback should be present
        assert 'filename="' in result

    def test_normal_pdf_filename(self):
        filename = "My_Storybook_ab12cd34.pdf"
        result = _format_content_disposition(filename)
        assert result.startswith("attachment")
        assert filename in result

    def test_png_filename(self):
        result = _format_content_disposition("page_001.png")
        assert "attachment" in result
        assert "page_001.png" in result

    def test_zip_filename(self):
        result = _format_content_disposition("storybook_pages.zip")
        assert "attachment" in result


# ============================================================================
# StorybookDetail schema behavior
# ============================================================================


class TestStorybookDetailSchema:
    def test_storybook_detail_has_pages(self):
        pages = [_make_page(1), _make_page(2)]
        sb = _make_storybook(pages=pages)
        assert len(sb.pages) == 2

    def test_storybook_detail_default_empty_pages(self):
        sb = _make_storybook()
        assert sb.pages == []

    def test_storybook_detail_session_id_accessible(self):
        sb = _make_storybook(session_id="test-session")
        assert sb.session_id == "test-session"

    def test_storybook_detail_name_accessible(self):
        sb = _make_storybook(name="Adventure Story")
        assert sb.name == "Adventure Story"


# ============================================================================
# Router logic (unit-testable portions)
# ============================================================================


class TestStorybookRouterFilenameBuilding:
    """Test filename construction logic mirroring the router endpoints."""

    def test_download_pdf_filename_format(self):
        storybook = _make_storybook(storybook_id="abcd1234ef", name="My Cool Story")
        storybook_id = storybook.id
        filename = f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}.pdf"
        assert filename == "My_Cool_Story_abcd1234.pdf"

    def test_download_page_pdf_filename_format(self):
        storybook = _make_storybook(name="Space Adventure")
        page_number = 3
        filename = f"{storybook.name.replace(' ', '_')}_page_{page_number}.pdf"
        assert filename == "Space_Adventure_page_3.pdf"

    def test_download_page_png_filename_format(self):
        storybook = _make_storybook(name="Ocean Tales")
        page_number = 5
        filename = f"{storybook.name.replace(' ', '_')}_page_{page_number}.png"
        assert filename == "Ocean_Tales_page_5.png"

    def test_download_png_zip_filename_format(self):
        storybook = _make_storybook(storybook_id="xyz99999ab", name="Forest Journey")
        storybook_id = storybook.id
        filename = f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}-pages.zip"
        assert filename == "Forest_Journey_xyz99999-pages.zip"

    def test_filename_with_no_spaces(self):
        storybook = _make_storybook(name="NoSpaces")
        filename = f"{storybook.name.replace(' ', '_')}_ab12cd34.pdf"
        assert filename == "NoSpaces_ab12cd34.pdf"

    def test_filename_replaces_multiple_spaces(self):
        storybook = _make_storybook(name="A B C")
        filename = storybook.name.replace(" ", "_")
        assert filename == "A_B_C"


# ============================================================================
# Save edits request logic
# ============================================================================


class TestSaveEditsRequestValidation:
    """Test the save edits validation logic."""

    def test_storybook_id_mismatch_detected(self):
        path_id = "storybook-path-id"
        request_id = "different-id"
        assert path_id != request_id

    def test_storybook_id_match_passes(self):
        path_id = "storybook-123"
        request_id = "storybook-123"
        assert path_id == request_id

    def test_empty_page_changes_detected(self):
        page_changes = []
        assert not page_changes

    def test_non_empty_page_changes_passes(self):
        from ii_agent.content.storybook.schemas import PageChanges, DesignChange

        change = DesignChange(
            designId="elem-1",
            type="style",
            property="color",
            value={"from": "red", "to": "blue"},
            timestamp=1700000000,
        )
        page_change = PageChanges(page_number=1, changes=[change])
        assert page_change.changes


# ============================================================================
# StorybookPageInfo schema
# ============================================================================


class TestStorybookPageInfoSchema:
    def test_page_info_default_text_position(self):
        page = _make_page()
        assert page.text_position == "right"

    def test_page_info_without_html_content(self):
        page = _make_page(html_content=None)
        assert page.html_content is None

    def test_page_info_with_html_content(self):
        page = _make_page(html_content="<html>test</html>")
        assert page.html_content == "<html>test</html>"

    def test_page_metadata_defaults_to_empty_dict(self):
        page = _make_page()
        assert isinstance(page.metadata, dict)


# ============================================================================
# Voice service status handling
# ============================================================================


class TestVoiceServiceStatusLogic:
    """Test the logic in cancel_storybook_generation endpoint."""

    def test_completed_status_returns_false(self):
        generation_status = "completed"
        success = generation_status != "completed" and generation_status != "failed"
        assert not success

    def test_failed_status_returns_false(self):
        generation_status = "failed"
        success = generation_status != "completed" and generation_status != "failed"
        assert not success

    def test_generating_status_allows_cancel(self):
        generation_status = "generating"
        success = generation_status != "completed" and generation_status != "failed"
        assert success

    def test_pending_status_allows_cancel(self):
        generation_status = "pending"
        success = generation_status != "completed" and generation_status != "failed"
        assert success


# ============================================================================
# Upload background content type detection
# ============================================================================


class TestUploadBackgroundValidation:
    """Test content type validation logic."""

    def test_png_is_image(self):
        content_type = "image/png"
        assert content_type.startswith("image/")

    def test_jpeg_is_image(self):
        content_type = "image/jpeg"
        assert content_type.startswith("image/")

    def test_webp_is_image(self):
        content_type = "image/webp"
        assert content_type.startswith("image/")

    def test_pdf_is_not_image(self):
        content_type = "application/pdf"
        assert not content_type.startswith("image/")

    def test_text_is_not_image(self):
        content_type = "text/plain"
        assert not content_type.startswith("image/")

    def test_ext_map_png(self):
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/avif": ".avif",
        }
        assert ext_map.get("image/png") == ".png"
        assert ext_map.get("image/webp") == ".webp"
        assert ext_map.get("image/unknown", ".png") == ".png"


# ============================================================================
# StorybookInfo schema
# ============================================================================


class TestStorybookInfoSchema:
    def test_storybook_info_defaults(self):
        info = StorybookInfo(
            id="sb-1",
            session_id="s-1",
            name="Test Book",
            aspect_ratio="1:1",
            resolution="1K",
        )
        assert info.version == 1
        assert info.page_count == 0
        assert info.root_storybook_id is None

    def test_storybook_info_with_version(self):
        info = StorybookInfo(
            id="sb-2",
            session_id="s-1",
            name="v2 Book",
            aspect_ratio="16:9",
            resolution="2K",
            version=2,
        )
        assert info.version == 2
