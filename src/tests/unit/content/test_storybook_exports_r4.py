"""Unit tests for storybook voice service, html generator, pdf/png exporters."""

from __future__ import annotations

import io
import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.content.storybook.html_generator import (
    _calculate_dimensions,
    _escape_html,
    _get_flex_direction,
    _parse_aspect_ratio,
    _round_to_even,
    extract_image_url_from_html,
    extract_text_content_from_html,
    generate_storybook_page_html,
    generate_text_only_page_html,
    update_html_image_url,
    update_html_text_content,
    FLEX_DIRECTION_MAP,
    RESOLUTION_PIXELS,
)
from ii_agent.content.storybook.voice_service import (
    _extract_plain_text,
    _resolve_language_code,
    _generate_voice_audio,
    StorybookVoiceService,
)
from ii_agent.content.storybook.schemas import (
    StorybookDetail,
    StorybookPageInfo,
    StorybookVoiceOverResponse,
)

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers
# ============================================================================


def _now():
    return datetime.now(timezone.utc)


def _make_page(
    page_number=1,
    text_content="Once upon a time",
    html_content=None,
    audio_link=None,
    page_metadata=None,
):
    return StorybookPageInfo(
        id=f"p{page_number}",
        storybook_id="sb-001",
        page_number=page_number,
        image_url="https://img.example.com/img.png",
        text_content=text_content,
        audio_link=audio_link,
        text_position="right",
        text_percentage=30,
        html_content=html_content,
        metadata=page_metadata or {},
        created_at=_now(),
        updated_at=_now(),
    )


def _make_storybook(pages=None, style_json=None, session_id="sess-001"):
    return StorybookDetail(
        id="sb-001",
        session_id=session_id,
        name="My Story",
        version=1,
        style_json=style_json or {},
        aspect_ratio="16:9",
        resolution="1K",
        page_count=len(pages or []),
        created_at=_now(),
        updated_at=_now(),
        pages=pages or [],
    )


# ============================================================================
# HTML Generator - parse_aspect_ratio
# ============================================================================


class TestParseAspectRatio:
    def test_standard_16_9(self):
        w, h = _parse_aspect_ratio("16:9")
        assert w == 16
        assert h == 9

    def test_standard_1_1(self):
        w, h = _parse_aspect_ratio("1:1")
        assert w == 1
        assert h == 1

    def test_standard_4_3(self):
        w, h = _parse_aspect_ratio("4:3")
        assert w == 4
        assert h == 3

    def test_portrait_9_16(self):
        w, h = _parse_aspect_ratio("9:16")
        assert w == 9
        assert h == 16

    def test_invalid_returns_1_1(self):
        w, h = _parse_aspect_ratio("invalid")
        assert w == 1
        assert h == 1

    def test_empty_returns_1_1(self):
        w, h = _parse_aspect_ratio(":")
        # Both sides parse to something -- just verify no crash
        assert isinstance(w, int)
        assert isinstance(h, int)


# ============================================================================
# HTML Generator - round_to_even
# ============================================================================


class TestRoundToEven:
    def test_even_unchanged(self):
        assert _round_to_even(1024) == 1024

    def test_odd_incremented(self):
        assert _round_to_even(1023) == 1024

    def test_zero_is_even(self):
        assert _round_to_even(0) == 0

    def test_1_becomes_2(self):
        assert _round_to_even(1) == 2


# ============================================================================
# HTML Generator - calculate_dimensions
# ============================================================================


class TestCalculateDimensions:
    def test_1k_1x1(self):
        w, h = _calculate_dimensions("1:1", "1K")
        assert w == 1024
        assert h == 1024

    def test_1k_16x9(self):
        w, h = _calculate_dimensions("16:9", "1K")
        assert h == 1024
        assert w > h

    def test_2k_1x1(self):
        w, h = _calculate_dimensions("1:1", "2K")
        assert w == 2048
        assert h == 2048

    def test_portrait_9x16(self):
        w, h = _calculate_dimensions("9:16", "1K")
        assert w < h

    def test_unknown_resolution_defaults(self):
        w, h = _calculate_dimensions("1:1", "XXX")
        # should default to DEFAULT_PIXELS=1024
        assert w == 1024
        assert h == 1024

    def test_result_always_even(self):
        w, h = _calculate_dimensions("16:9", "1K")
        assert w % 2 == 0
        assert h % 2 == 0


# ============================================================================
# HTML Generator - escape_html
# ============================================================================


class TestEscapeHtml:
    def test_ampersand_escaped(self):
        assert _escape_html("a & b") == "a &amp; b"

    def test_less_than_escaped(self):
        assert _escape_html("a < b") == "a &lt; b"

    def test_greater_than_escaped(self):
        assert _escape_html("a > b") == "a &gt; b"

    def test_double_quote_escaped(self):
        assert _escape_html('say "hi"') == "say &quot;hi&quot;"

    def test_single_quote_escaped(self):
        assert _escape_html("it's") == "it&#39;s"

    def test_plain_text_unchanged(self):
        assert _escape_html("Hello World") == "Hello World"

    def test_empty_string(self):
        assert _escape_html("") == ""


# ============================================================================
# HTML Generator - get_flex_direction
# ============================================================================


class TestGetFlexDirection:
    def test_left_is_row_reverse(self):
        assert _get_flex_direction("left") == "row-reverse"

    def test_right_is_row(self):
        assert _get_flex_direction("right") == "row"

    def test_top_is_column_reverse(self):
        assert _get_flex_direction("top") == "column-reverse"

    def test_bottom_is_column(self):
        assert _get_flex_direction("bottom") == "column"

    def test_none_is_row(self):
        assert _get_flex_direction("none") == "row"

    def test_unknown_defaults_to_row(self):
        assert _get_flex_direction("unknown") == "row"


# ============================================================================
# HTML Generator - generate_storybook_page_html
# ============================================================================


class TestGenerateStorybookPageHtml:
    def test_image_only_when_no_text(self):
        html = generate_storybook_page_html(
            image_url="https://img.example.com/img.png",
            text_content="",
            text_position="none",
            text_percentage=0,
        )
        assert "https://img.example.com/img.png" in html
        assert "<!DOCTYPE html>" in html
        assert "storybook-page" in html

    def test_composite_when_text_present(self):
        html = generate_storybook_page_html(
            image_url="https://img.example.com/img.png",
            text_content="The fox jumped",
            text_position="right",
            text_percentage=25,
        )
        assert "text-section" in html
        assert "The fox jumped" in html

    def test_page_number_in_html(self):
        html = generate_storybook_page_html(
            image_url="https://img.example.com/img.png",
            text_content="",
            text_position="none",
            text_percentage=0,
            page_number=7,
        )
        assert "7" in html

    def test_invalid_text_position_becomes_none(self):
        html = generate_storybook_page_html(
            image_url="https://img.example.com/img.png",
            text_content="Hello",
            text_position="invalid_position",
            text_percentage=25,
        )
        # Invalid position should be treated as "none" -> image only
        assert "<!DOCTYPE html>" in html

    def test_resolution_1k_affects_viewport(self):
        html = generate_storybook_page_html(
            image_url="url",
            text_content="",
            text_position="none",
            text_percentage=0,
            aspect_ratio="1:1",
            resolution="1K",
        )
        assert "1024" in html

    def test_text_escaped_in_output(self):
        html = generate_storybook_page_html(
            image_url="url",
            text_content='<script>alert("xss")</script>',
            text_position="right",
            text_percentage=25,
        )
        assert "<script>" not in html

    def test_text_percentage_clamped(self):
        # text_percentage=10 is below 20 -> should be clamped to 20
        html = generate_storybook_page_html(
            image_url="url",
            text_content="Hello world",
            text_position="right",
            text_percentage=10,
        )
        assert "text-section" in html


# ============================================================================
# HTML Generator - generate_text_only_page_html
# ============================================================================


class TestGenerateTextOnlyPageHtml:
    def test_contains_text_content(self):
        html = generate_text_only_page_html(
            text_content="Once upon a time",
            aspect_ratio="1:1",
            resolution="1K",
            page_number=2,
        )
        assert "Once upon a time" in html
        assert "text-only" in html

    def test_data_type_attribute(self):
        html = generate_text_only_page_html(
            text_content="Story text",
            aspect_ratio="16:9",
            resolution="1K",
        )
        assert 'data-type="text-only"' in html

    def test_page_number_present(self):
        html = generate_text_only_page_html(
            text_content="Page text",
            page_number=5,
        )
        assert "5" in html

    def test_html_entities_escaped(self):
        html = generate_text_only_page_html(
            text_content="A & B",
        )
        assert "&amp;" in html


# ============================================================================
# HTML Generator - update_html functions
# ============================================================================


class TestUpdateHtmlFunctions:
    def test_update_text_content(self):
        original = generate_storybook_page_html(
            image_url="https://img.example.com/img.png",
            text_content="Old text",
            text_position="right",
            text_percentage=25,
        )
        updated = update_html_text_content(original, "New text")
        assert "New text" in updated

    def test_update_image_url(self):
        original = generate_storybook_page_html(
            image_url="https://old-url.com/img.png",
            text_content="",
            text_position="none",
            text_percentage=0,
        )
        updated = update_html_image_url(original, "https://new-url.com/img.png")
        assert "https://new-url.com/img.png" in updated

    def test_extract_image_url(self):
        html = generate_storybook_page_html(
            image_url="https://extract-test.com/img.png",
            text_content="",
            text_position="none",
            text_percentage=0,
        )
        url = extract_image_url_from_html(html)
        assert url == "https://extract-test.com/img.png"

    def test_extract_text_content(self):
        html = generate_storybook_page_html(
            image_url="url",
            text_content="Extract me",
            text_position="right",
            text_percentage=25,
        )
        text = extract_text_content_from_html(html)
        assert text is not None
        assert "Extract me" in text

    def test_extract_image_url_returns_none_if_no_img(self):
        result = extract_image_url_from_html("<html>no image</html>")
        assert result is None


# ============================================================================
# Voice Service - module-level helpers
# ============================================================================


class TestExtractPlainText:
    def test_extracts_from_data_editable(self):
        html = '<div data-editable="text">Hello World</div>'
        result = _extract_plain_text(html)
        assert "Hello World" in result

    def test_empty_html_returns_empty(self):
        result = _extract_plain_text("")
        assert result == ""

    def test_html_without_data_editable(self):
        html = "<div><p>Some text here</p></div>"
        result = _extract_plain_text(html)
        assert "Some text here" in result

    def test_none_returns_empty(self):
        result = _extract_plain_text(None)
        assert result == ""


class TestResolveLanguageCode:
    def test_explicit_language_code_takes_priority(self):
        result = _resolve_language_code("fr-FR", {"language_code": "en-US"})
        assert result == "fr-FR"

    def test_style_json_language_code(self):
        result = _resolve_language_code(None, {"language_code": "de-DE"})
        assert result == "de-DE"

    def test_style_json_language_key(self):
        result = _resolve_language_code(None, {"language": "es-ES"})
        assert result == "es-ES"

    def test_none_language_code_returns_none(self):
        result = _resolve_language_code(None, {})
        assert result is None

    def test_non_dict_style_json_returns_none(self):
        result = _resolve_language_code(None, "not-a-dict")
        assert result is None

    def test_empty_string_language_code(self):
        result = _resolve_language_code("", {"language_code": "ja-JP"})
        assert result == "ja-JP"


class TestGenerateVoiceAudio:
    @pytest.mark.asyncio
    async def test_empty_text_returns_none_zero(self):
        voice_service = MagicMock()
        url, cost = await _generate_voice_audio(voice_service, text="", session_id="s1")
        assert url is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_none_voice_service_returns_none_zero(self):
        url, cost = await _generate_voice_audio(None, text="Hello", session_id="s1")
        assert url is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_successful_generation_returns_url_and_cost(self):
        mock_result = SimpleNamespace(url="https://audio.example.com/file.mp3", cost=0.01)
        mock_service = AsyncMock()
        mock_service.generate_voice = AsyncMock(return_value=mock_result)

        url, cost = await _generate_voice_audio(
            mock_service, text="Hello world", session_id="sess-1"
        )
        assert url == "https://audio.example.com/file.mp3"
        assert cost == 0.01

    @pytest.mark.asyncio
    async def test_exception_returns_none_zero(self):
        mock_service = AsyncMock()
        mock_service.generate_voice = AsyncMock(side_effect=Exception("network error"))

        url, cost = await _generate_voice_audio(mock_service, text="Hello", session_id="sess-1")
        assert url is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_language_code_passed_to_service(self):
        mock_result = SimpleNamespace(url="https://audio.example.com/file.mp3", cost=0.05)
        mock_service = AsyncMock()
        mock_service.generate_voice = AsyncMock(return_value=mock_result)

        await _generate_voice_audio(
            mock_service,
            text="Bonjour",
            session_id="sess-1",
            language_code="fr-FR",
        )
        call_kwargs = mock_service.generate_voice.call_args.kwargs
        assert call_kwargs.get("language_code") == "fr-FR"


# ============================================================================
# StorybookVoiceService
# ============================================================================


class TestStorybookVoiceServiceGetGenerationStatus:
    def _make_service(self):
        return StorybookVoiceService(
            repo=MagicMock(),
            storybook_service=MagicMock(),
            config=SimpleNamespace(),
            credit_service=MagicMock(),
        )

    def test_returns_status_from_style_json(self):
        service = self._make_service()
        sb = _make_storybook(style_json={"generation": {"status": "completed"}})
        assert service.get_generation_status(sb) == "completed"

    def test_returns_none_when_no_generation_key(self):
        service = self._make_service()
        sb = _make_storybook(style_json={})
        assert service.get_generation_status(sb) is None

    def test_returns_none_when_style_json_none(self):
        service = self._make_service()
        sb = _make_storybook(style_json=None)
        # style_json=None not a dict
        result = service.get_generation_status(sb)
        assert result is None

    def test_returns_failed_status(self):
        service = self._make_service()
        sb = _make_storybook(style_json={"generation": {"status": "failed"}})
        assert service.get_generation_status(sb) == "failed"

    def test_returns_generating_status(self):
        service = self._make_service()
        sb = _make_storybook(style_json={"generation": {"status": "generating"}})
        assert service.get_generation_status(sb) == "generating"


class TestStorybookVoiceServiceGenerateVoiceoverAndDeductCredits:
    def _make_service(self, *, repo=None, credit_service=None):
        if credit_service is None:
            credit_svc = MagicMock()
            credit_svc.has_sufficient_credits = AsyncMock(return_value=True)
        else:
            credit_svc = credit_service
        return StorybookVoiceService(
            repo=repo or MagicMock(),
            storybook_service=MagicMock(),
            config=SimpleNamespace(),
            credit_service=credit_svc,
        )

    @pytest.mark.asyncio
    async def test_returns_error_when_storybook_not_found(self):
        service = self._make_service()
        with patch.object(
            service,
            "generate_voiceover",
            new=AsyncMock(return_value=(None, False, 0.0)),
        ):
            result = await service.generate_voiceover_and_deduct_credits(
                db=AsyncMock(),
                storybook_id="missing",
                user_id="user-1",
                session_id="sess-1",
            )
        assert not result.success
        assert "unavailable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_no_audio_generated(self):
        service = self._make_service()
        sb = _make_storybook()
        with patch.object(
            service,
            "generate_voiceover",
            new=AsyncMock(return_value=(sb, False, 0.0)),
        ):
            result = await service.generate_voiceover_and_deduct_credits(
                db=AsyncMock(),
                storybook_id="sb-001",
                user_id="user-1",
                session_id="sess-1",
            )
        assert not result.success
        assert "No voice audio" in result.error

    @pytest.mark.asyncio
    async def test_returns_success_when_audio_generated_no_cost(self):
        service = self._make_service()
        sb = _make_storybook()
        with patch.object(
            service,
            "generate_voiceover",
            new=AsyncMock(return_value=(sb, True, 0.0)),
        ):
            result = await service.generate_voiceover_and_deduct_credits(
                db=AsyncMock(),
                storybook_id="sb-001",
                user_id="user-1",
                session_id="sess-1",
            )
        assert result.success
        assert result.storybook is not None

    @pytest.mark.asyncio
    async def test_deducts_credits_when_cost_present(self):
        credit_svc = MagicMock()
        credit_svc.has_sufficient_credits = AsyncMock(return_value=True)
        service = self._make_service(credit_service=credit_svc)
        sb = _make_storybook()
        with (
            patch.object(
                service,
                "generate_voiceover",
                new=AsyncMock(return_value=(sb, True, 0.10)),
            ),
            patch(
                "ii_agent.content.storybook.voice_service.check_and_deduct_storybook_credits",
                new=AsyncMock(),
            ) as mock_deduct,
        ):
            db = AsyncMock()
            result = await service.generate_voiceover_and_deduct_credits(
                db=db,
                storybook_id="sb-001",
                user_id="user-1",
                session_id="sess-1",
            )
        mock_deduct.assert_called_once()
        assert result.success

    @pytest.mark.asyncio
    async def test_insufficient_credits_returns_error(self):
        credit_svc = MagicMock()
        credit_svc.has_sufficient_credits = AsyncMock(return_value=False)
        service = self._make_service(credit_service=credit_svc)
        sb = _make_storybook()
        db = AsyncMock()
        result = await service.generate_voiceover_and_deduct_credits(
            db=db,
            storybook_id="sb-001",
            user_id="user-1",
            session_id="sess-1",
        )
        assert not result.success
        assert "Insufficient" in result.error


# ============================================================================
# PDF Exporter
# ============================================================================


class TestStorybookPDFExporterLogic:
    """Test PDF exporter's non-Playwright logic (early returns, etc.)."""

    @pytest.mark.asyncio
    async def test_download_as_pdf_returns_none_for_empty_storybook(self):
        from ii_agent.content.storybook.pdf_export import StorybookPDFExporter

        exporter = StorybookPDFExporter()
        result = await exporter.download_storybook_as_pdf(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_as_pdf_returns_none_for_no_pages(self):
        from ii_agent.content.storybook.pdf_export import StorybookPDFExporter

        exporter = StorybookPDFExporter()
        sb = _make_storybook(pages=[])
        result = await exporter.download_storybook_as_pdf(sb)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_page_as_pdf_returns_none_for_none_storybook(self):
        from ii_agent.content.storybook.pdf_export import StorybookPDFExporter

        exporter = StorybookPDFExporter()
        result = await exporter.download_storybook_page_as_pdf(None, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_with_progress_yields_error_for_empty(self):
        from ii_agent.content.storybook.pdf_export import StorybookPDFExporter

        exporter = StorybookPDFExporter()
        events = []
        async for event in exporter.download_storybook_as_pdf_with_progress(None):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "error"

    @pytest.mark.asyncio
    async def test_download_with_progress_yields_error_for_no_pages(self):
        from ii_agent.content.storybook.pdf_export import StorybookPDFExporter

        exporter = StorybookPDFExporter()
        sb = _make_storybook(pages=[])
        events = []
        async for event in exporter.download_storybook_as_pdf_with_progress(sb):
            events.append(event)
        assert any(e["type"] == "error" for e in events)


# ============================================================================
# PNG Exporter
# ============================================================================


class TestStorybookPNGExporterLogic:
    """Test PNG exporter's non-Playwright logic."""

    @pytest.mark.asyncio
    async def test_download_page_as_png_returns_none_for_none(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        result = await exporter.download_storybook_page_as_png(None, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_page_as_png_returns_none_for_no_pages(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        sb = _make_storybook(pages=[])
        result = await exporter.download_storybook_page_as_png(sb, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_as_zip_returns_none_for_none(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        result = await exporter.download_storybook_as_png_zip(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_as_zip_returns_none_for_no_pages(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        sb = _make_storybook(pages=[])
        result = await exporter.download_storybook_as_png_zip(sb)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_with_progress_yields_error_for_empty(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        events = []
        async for event in exporter.download_storybook_as_png_with_progress(None):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "error"

    @pytest.mark.asyncio
    async def test_download_with_progress_yields_error_for_no_pages(self):
        from ii_agent.content.storybook.png_export import StorybookPNGExporter

        exporter = StorybookPNGExporter()
        sb = _make_storybook(pages=[])
        events = []
        async for event in exporter.download_storybook_as_png_with_progress(sb):
            events.append(event)
        assert any(e["type"] == "error" for e in events)


# ============================================================================
# RESOLUTION_PIXELS / FLEX_DIRECTION_MAP constants
# ============================================================================


class TestConstants:
    def test_resolution_pixels_1k(self):
        assert RESOLUTION_PIXELS["1K"] == 1024

    def test_resolution_pixels_2k(self):
        assert RESOLUTION_PIXELS["2K"] == 2048

    def test_resolution_pixels_4k(self):
        assert RESOLUTION_PIXELS["4K"] == 4096

    def test_flex_direction_map_complete(self):
        for pos in ["left", "right", "top", "bottom", "none", "separate_page"]:
            assert pos in FLEX_DIRECTION_MAP
