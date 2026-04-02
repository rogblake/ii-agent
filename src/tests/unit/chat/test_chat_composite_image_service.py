"""Unit tests for chat/media/services/composite_image_service.py.

Tests dimension calculations, HTML generation, and render logic
with the tool server mocked via httpx.
"""

from __future__ import annotations

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ii_agent.chat.media.services.composite_image_service import (
    DEFAULT_PIXELS,
    RESOLUTION_PIXELS,
    _calculate_dimensions,
    _escape_html,
    _generate_html,
    _get_flex_direction,
    _parse_aspect_ratio,
    _render_via_tool_server,
    _round_to_even,
    create_composite,
)


# ---------------------------------------------------------------------------
# _parse_aspect_ratio
# ---------------------------------------------------------------------------


class TestParseAspectRatio:
    def test_standard_16_9(self):
        assert _parse_aspect_ratio("16:9") == (16, 9)

    def test_square_1_1(self):
        assert _parse_aspect_ratio("1:1") == (1, 1)

    def test_portrait_9_16(self):
        assert _parse_aspect_ratio("9:16") == (9, 16)

    def test_4_3(self):
        assert _parse_aspect_ratio("4:3") == (4, 3)

    def test_invalid_string_defaults_to_16_9(self):
        assert _parse_aspect_ratio("badformat") == (16, 9)

    def test_empty_string_defaults_to_16_9(self):
        assert _parse_aspect_ratio("") == (16, 9)

    def test_non_numeric_parts_default_to_16_9(self):
        assert _parse_aspect_ratio("a:b") == (16, 9)


# ---------------------------------------------------------------------------
# _round_to_even
# ---------------------------------------------------------------------------


class TestRoundToEven:
    def test_even_number_unchanged(self):
        assert _round_to_even(1920) == 1920
        assert _round_to_even(1080) == 1080
        assert _round_to_even(100) == 100

    def test_odd_number_rounded_up(self):
        assert _round_to_even(1025) == 1026
        assert _round_to_even(1) == 2
        assert _round_to_even(101) == 102

    def test_zero_stays_zero(self):
        assert _round_to_even(0) == 0


# ---------------------------------------------------------------------------
# _calculate_dimensions
# ---------------------------------------------------------------------------


class TestCalculateDimensions:
    def test_16_9_at_1k(self):
        w, h = _calculate_dimensions("16:9", "1K")
        assert h == 1024
        assert w > h  # landscape
        assert w % 2 == 0
        assert h % 2 == 0

    def test_16_9_at_2k(self):
        w, h = _calculate_dimensions("16:9", "2K")
        assert h == 2048
        assert w == int((2048 * 16) / 9)

    def test_9_16_portrait_at_1k(self):
        w, h = _calculate_dimensions("9:16", "1K")
        assert w == 1024
        assert h > w  # portrait

    def test_4k_resolution(self):
        w, h = _calculate_dimensions("16:9", "4K")
        assert h == RESOLUTION_PIXELS["4K"]

    def test_unknown_resolution_uses_default(self):
        w, h = _calculate_dimensions("16:9", "8K")
        assert h == DEFAULT_PIXELS

    def test_results_always_even(self):
        for ratio in ["16:9", "9:16", "4:3", "3:4", "21:9"]:
            for res in ["1K", "2K", "4K"]:
                w, h = _calculate_dimensions(ratio, res)
                assert w % 2 == 0, f"{ratio} {res}: width {w} not even"
                assert h % 2 == 0, f"{ratio} {res}: height {h} not even"

    def test_square_ratio(self):
        w, h = _calculate_dimensions("1:1", "1K")
        assert w == h

    def test_invalid_ratio_uses_16_9_default(self):
        w, h = _calculate_dimensions("bad:ratio", "1K")
        # Falls back to 16:9
        assert h == 1024


# ---------------------------------------------------------------------------
# _escape_html
# ---------------------------------------------------------------------------


class TestEscapeHtml:
    def test_ampersand(self):
        assert _escape_html("a & b") == "a &amp; b"

    def test_less_than(self):
        assert _escape_html("<div>") == "&lt;div&gt;"

    def test_greater_than(self):
        assert _escape_html("x > y") == "x &gt; y"

    def test_double_quote(self):
        assert _escape_html('"hello"') == "&quot;hello&quot;"

    def test_single_quote(self):
        assert _escape_html("it's") == "it&#39;s"

    def test_no_special_chars(self):
        assert _escape_html("hello world") == "hello world"

    def test_empty_string(self):
        assert _escape_html("") == ""

    def test_multiple_special_chars(self):
        result = _escape_html("<script>alert('xss & more')</script>")
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&#39;" in result


# ---------------------------------------------------------------------------
# _get_flex_direction
# ---------------------------------------------------------------------------


class TestGetFlexDirection:
    def test_left_returns_row_reverse(self):
        assert _get_flex_direction("left") == "row-reverse"

    def test_right_returns_row(self):
        assert _get_flex_direction("right") == "row"

    def test_top_returns_column_reverse(self):
        assert _get_flex_direction("top") == "column-reverse"

    def test_bottom_returns_column(self):
        assert _get_flex_direction("bottom") == "column"

    def test_none_returns_row(self):
        assert _get_flex_direction("none") == "row"

    def test_unknown_defaults_to_row(self):
        assert _get_flex_direction("unknown") == "row"


# ---------------------------------------------------------------------------
# _generate_html
# ---------------------------------------------------------------------------


class TestGenerateHtml:
    def test_image_only_when_no_text(self):
        html = _generate_html(
            image_url="https://img.example.com/photo.jpg",
            text_content="",
            text_position="none",
            text_percentage=0,
        )
        assert "image-only" in html
        assert "container" not in html
        assert "photo.jpg" in html

    def test_image_and_text_when_text_present(self):
        html = _generate_html(
            image_url="https://img.example.com/photo.jpg",
            text_content="Hello World",
            text_position="right",
            text_percentage=25,
        )
        assert "container" in html
        assert "image-section" in html
        assert "text-section" in html
        assert "Hello World" in html

    def test_text_escaped_in_html(self):
        html = _generate_html(
            image_url="https://img.example.com/photo.jpg",
            text_content="<b>Bold & 'italic'</b>",
            text_position="bottom",
            text_percentage=25,
        )
        assert "&lt;b&gt;" in html
        assert "&amp;" in html
        assert "&#39;" in html

    def test_image_url_in_html(self):
        url = "https://example.com/image.png"
        html = _generate_html(
            image_url=url,
            text_content="",
            text_position="none",
            text_percentage=0,
        )
        assert url in html

    def test_dimensions_embedded_in_html(self):
        html = _generate_html(
            image_url="https://example.com/img.png",
            text_content="",
            text_position="none",
            text_percentage=0,
            width=1920,
            height=1080,
        )
        assert "1920" in html
        assert "1080" in html

    def test_flex_direction_for_left_position(self):
        html = _generate_html(
            image_url="https://example.com/img.png",
            text_content="Text here",
            text_position="left",
            text_percentage=25,
        )
        assert "row-reverse" in html

    def test_text_percentage_in_css(self):
        html = _generate_html(
            image_url="https://example.com/img.png",
            text_content="Some text",
            text_position="right",
            text_percentage=30,
        )
        assert "30%" in html
        assert "70%" in html  # 100 - 30 = image percentage


# ---------------------------------------------------------------------------
# _render_via_tool_server
# ---------------------------------------------------------------------------


class TestRenderViaToolServer:
    async def test_raises_when_tool_server_url_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            if "TOOL_SERVER_URL" in os.environ:
                del os.environ["TOOL_SERVER_URL"]
            with pytest.raises(RuntimeError, match="TOOL_SERVER_URL is not configured"):
                await _render_via_tool_server(
                    html_content="<html/>",
                    session_id="sess",
                    user_api_key="key",
                )

    async def test_raises_when_user_api_key_missing(self):
        with patch.dict(os.environ, {"TOOL_SERVER_URL": "http://tool-server"}):
            with pytest.raises(RuntimeError, match="user_api_key is required"):
                await _render_via_tool_server(
                    html_content="<html/>",
                    session_id="sess",
                    user_api_key=None,
                )

    async def test_successful_render_returns_png_bytes(self):
        fake_png = b"\x89PNG fake data"
        encoded = base64.b64encode(fake_png).decode()

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "image_base64": encoded}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TOOL_SERVER_URL": "http://tool-server"}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _render_via_tool_server(
                html_content="<html/>",
                session_id="sess-1",
                user_api_key="api-key",
                width=1920,
                height=1080,
            )

        assert result == fake_png

    async def test_raises_when_success_false(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error": "Rendering failed",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TOOL_SERVER_URL": "http://tool-server"}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(RuntimeError, match="Rendering failed"):
                await _render_via_tool_server(
                    html_content="<html/>",
                    session_id="sess-1",
                    user_api_key="api-key",
                )

    async def test_raises_when_no_image_data(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "image_base64": None}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TOOL_SERVER_URL": "http://tool-server"}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(RuntimeError, match="No image data"):
                await _render_via_tool_server(
                    html_content="<html/>",
                    session_id="sess-1",
                    user_api_key="api-key",
                )

    async def test_http_error_wrapped_in_runtime_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TOOL_SERVER_URL": "http://tool-server"}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(RuntimeError, match="Failed to call tool server"):
                await _render_via_tool_server(
                    html_content="<html/>",
                    session_id="sess-1",
                    user_api_key="api-key",
                )


# ---------------------------------------------------------------------------
# create_composite
# ---------------------------------------------------------------------------


class TestCreateComposite:
    async def test_text_percentage_clamped_below_20(self):
        """text_percentage < 20 should be clamped to 20."""
        generated_htmls = []

        async def fake_render(html, session_id, user_api_key, width, height):
            generated_htmls.append(html)
            return b"PNG"

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="Hello",
                text_position="right",
                text_percentage=5,  # below min 20
                session_id="sess",
                user_api_key="key",
            )

        # 20% text -> 80% image
        assert "20%" in generated_htmls[0]
        assert "80%" in generated_htmls[0]

    async def test_text_percentage_clamped_above_30(self):
        """text_percentage > 30 should be clamped to 30."""
        generated_htmls = []

        async def fake_render(html, session_id, user_api_key, width, height):
            generated_htmls.append(html)
            return b"PNG"

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="Hello",
                text_position="right",
                text_percentage=50,  # above max 30
                session_id="sess",
                user_api_key="key",
            )

        assert "30%" in generated_htmls[0]
        assert "70%" in generated_htmls[0]

    async def test_no_text_position_generates_image_only(self):
        generated_htmls = []

        async def fake_render(html, session_id, user_api_key, width, height):
            generated_htmls.append(html)
            return b"PNG"

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            result = await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="Some text",
                text_position="none",
                text_percentage=25,
                session_id="sess",
                user_api_key="key",
            )

        assert result == b"PNG"
        assert "image-only" in generated_htmls[0]

    async def test_empty_text_content_generates_image_only(self):
        generated_htmls = []

        async def fake_render(html, session_id, user_api_key, width, height):
            generated_htmls.append(html)
            return b"PNG"

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            result = await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="   ",  # whitespace only
                text_position="right",
                text_percentage=25,
                session_id="sess",
                user_api_key="key",
            )

        assert "image-only" in generated_htmls[0]

    async def test_valid_text_percentage_unchanged(self):
        generated_htmls = []

        async def fake_render(html, session_id, user_api_key, width, height):
            generated_htmls.append(html)
            return b"PNG"

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="Hello",
                text_position="right",
                text_percentage=25,  # within range 20-30
                session_id="sess",
                user_api_key="key",
            )

        assert "25%" in generated_htmls[0]

    async def test_returns_bytes_from_render(self):
        fake_png = b"\x89PNG actual data"

        async def fake_render(html, session_id, user_api_key, width, height):
            return fake_png

        with patch(
            "ii_agent.chat.media.services.composite_image_service._render_via_tool_server",
            side_effect=fake_render,
        ):
            result = await create_composite(
                image_url="https://img.example.com/img.png",
                text_content="",
                text_position="none",
                text_percentage=25,
                session_id="sess",
                user_api_key="key",
            )

        assert result == fake_png
