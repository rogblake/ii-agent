"""Unit tests for SlideDesignService."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.content.slides.design.service import SlideDesignService
from ii_agent.content.slides.design.schemas import (
    SlideSyncBatchRequest,
    SlideSyncChange,
    SlideDeckSyncBatchRequest,
    SlideDeckSyncChange,
)
from ii_agent.projects.design.exceptions import (
    DesignSessionNotFoundError,
    DesignSessionAccessDeniedError,
)
from ii_agent.content.slides.design.exceptions import DesignSlideNotFoundError
from ii_agent.projects.design.schemas import StyleChange

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers
# ============================================================================


def _make_slide(slide_number, content="<div>slide content</div>", title=None):
    return SimpleNamespace(
        slide_number=slide_number,
        slide_content=content,
        slide_title=title or f"Slide {slide_number}",
    )


def _make_service(
    *,
    repo=None,
    sandbox_service=None,
    event_service=None,
    config=None,
):
    return SlideDesignService(
        repo=repo or MagicMock(),
        sandbox_service=sandbox_service or MagicMock(),
        config=config or SimpleNamespace(workspace_path="/workspace"),
    )


# ============================================================================
# _get_session_for_request
# ============================================================================


class TestGetSessionForRequest:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        with pytest.raises(DesignSessionNotFoundError):
            await service._get_session_for_request(AsyncMock(), session_id="s1", user_id="u1")

    @pytest.mark.asyncio
    async def test_raises_when_user_id_mismatch(self):
        repo = MagicMock()
        session = SimpleNamespace(user_id="other-user")
        repo.get_session = AsyncMock(return_value=session)
        service = _make_service(repo=repo)

        with pytest.raises(DesignSessionAccessDeniedError):
            await service._get_session_for_request(AsyncMock(), session_id="s1", user_id="u1")

    @pytest.mark.asyncio
    async def test_returns_session_when_user_matches(self):
        repo = MagicMock()
        session = SimpleNamespace(user_id="u1")
        repo.get_session = AsyncMock(return_value=session)
        service = _make_service(repo=repo)

        result = await service._get_session_for_request(AsyncMock(), session_id="s1", user_id="u1")
        assert result is session


# ============================================================================
# get_slide_proxy_html
# ============================================================================


class TestGetSlideProxyHtml:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        with pytest.raises(DesignSessionNotFoundError):
            await service.get_slide_proxy_html(
                AsyncMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="pres",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_raises_when_slide_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        with pytest.raises(DesignSlideNotFoundError):
            await service.get_slide_proxy_html(
                AsyncMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="pres",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_raises_when_slide_has_no_content(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(return_value=_make_slide(1, content=""))
        service = _make_service(repo=repo)

        with pytest.raises(DesignSlideNotFoundError):
            await service.get_slide_proxy_html(
                AsyncMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="pres",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_returns_html_for_valid_slide(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(
            return_value=_make_slide(1, content="<html><body>content</body></html>")
        )
        service = _make_service(repo=repo)

        with (
            patch(
                "ii_agent.content.slides.design.service.inject_runtime_script_only",
                side_effect=lambda html: html + "<!-- injected -->",
            ),
            patch(
                "ii_agent.content.slides.design.service.sanitize_legacy_editable_artifacts",
                side_effect=lambda html: html,
            ),
        ):
            result = await service.get_slide_proxy_html(
                AsyncMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="pres",
                slide_number=1,
            )
        assert "content" in result


# ============================================================================
# apply_slide_sync_batch
# ============================================================================


class TestApplySlideSyncBatch:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="pres",
            slide_number=1,
            changes=[],
        )
        with pytest.raises(DesignSessionNotFoundError):
            await service.apply_slide_sync_batch(AsyncMock(), request=request, user_id="u1")

    @pytest.mark.asyncio
    async def test_raises_when_slide_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="pres",
            slide_number=1,
            changes=[],
        )
        with pytest.raises(DesignSlideNotFoundError):
            await service.apply_slide_sync_batch(AsyncMock(), request=request, user_id="u1")

    @pytest.mark.asyncio
    async def test_processes_style_change(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        slide = _make_slide(1, content='<div data-design-id="el1">text</div>')
        repo.get_slide = AsyncMock(return_value=slide)
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)

        change = SlideSyncChange(
            design_id="el1",
            type="style",
            property="color",
            value={"from": "red", "to": "blue"},
        )
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="pres",
            slide_number=1,
            changes=[change],
        )
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_style_change",
            return_value="<div modified>",
        ):
            result = await service.apply_slide_sync_batch(
                AsyncMock(), request=request, user_id="u1"
            )
        assert result.processed == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_unknown_change_type_fails(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(return_value=_make_slide(1, content="<div>content</div>"))
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)

        change = SlideSyncChange(
            design_id="el1",
            type="unknown_type",
            property="color",
            value={"from": "red", "to": "blue"},
        )
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="pres",
            slide_number=1,
            changes=[change],
        )
        result = await service.apply_slide_sync_batch(AsyncMock(), request=request, user_id="u1")
        assert result.failed == 1
        assert result.success is False

    @pytest.mark.asyncio
    async def test_text_change_processed(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_slide = AsyncMock(return_value=_make_slide(1, content="<div>content</div>"))
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)

        change = SlideSyncChange(
            design_id="el1",
            type="text",
            property="textContent",
            value={"to": "New text"},
        )
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="pres",
            slide_number=1,
            changes=[change],
        )
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_text_change",
            return_value="<div>New text</div>",
        ):
            result = await service.apply_slide_sync_batch(
                AsyncMock(), request=request, user_id="u1"
            )
        assert result.processed == 1
        assert result.failed == 0


# ============================================================================
# apply_slide_deck_sync_batch
# ============================================================================


class TestApplySlideDeckSyncBatch:
    @pytest.mark.asyncio
    async def test_returns_success_for_empty_changes(self):
        service = _make_service()
        request = SlideDeckSyncBatchRequest(session_id="s1", presentation_name="pres", changes=[])
        result = await service.apply_slide_deck_sync_batch(
            AsyncMock(), request=request, user_id="u1"
        )
        assert result.success is True
        assert result.processed == 0

    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)

        change = SlideDeckSyncChange(
            slide_number=1,
            design_id="el1",
            type="style",
            property="color",
            value={"to": "blue"},
        )
        request = SlideDeckSyncBatchRequest(
            session_id="s1", presentation_name="pres", changes=[change]
        )
        with pytest.raises(DesignSessionNotFoundError):
            await service.apply_slide_deck_sync_batch(AsyncMock(), request=request, user_id="u1")

    @pytest.mark.asyncio
    async def test_invalid_slide_number_increments_failed(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_presentation_slides = AsyncMock(return_value=[_make_slide(1)])
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)

        change = SlideDeckSyncChange(
            slide_number=0,  # invalid
            design_id="el1",
            type="style",
            property="color",
            value={"to": "blue"},
        )
        request = SlideDeckSyncBatchRequest(
            session_id="s1", presentation_name="pres", changes=[change]
        )
        result = await service.apply_slide_deck_sync_batch(
            AsyncMock(), request=request, user_id="u1"
        )
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_slide_not_found_increments_failed(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=SimpleNamespace())
        repo.get_presentation_slides = AsyncMock(return_value=[_make_slide(1)])
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)

        change = SlideDeckSyncChange(
            slide_number=99,  # doesn't exist
            design_id="el1",
            type="style",
            property="color",
            value={"to": "blue"},
        )
        request = SlideDeckSyncBatchRequest(
            session_id="s1", presentation_name="pres", changes=[change]
        )
        result = await service.apply_slide_deck_sync_batch(
            AsyncMock(), request=request, user_id="u1"
        )
        assert result.failed > 0


# ============================================================================
# _apply_single_change (static method)
# ============================================================================


class TestApplySingleChange:
    def test_unsupported_change_type_returns_false(self):
        html = "<div>content</div>"
        result_html, ok, reason = SlideDesignService._apply_single_change(
            html,
            design_id="el1",
            change_type="unsupported",
            property_name="color",
            new_value="blue",
        )
        assert ok is False
        assert "Unsupported" in reason
        assert result_html == html

    def test_style_change_calls_handler(self):
        html = "<div>content</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_style_change_with_status",
            return_value=("<div modified>", True),
        ):
            result_html, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="el1",
                change_type="style",
                property_name="color",
                new_value="blue",
            )
        assert ok is True

    def test_text_change_calls_handler(self):
        html = "<div>old text</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_text_change_with_status",
            return_value=("<div>new text</div>", True),
        ):
            result_html, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="el1",
                change_type="text",
                property_name="textContent",
                new_value="new text",
            )
        assert ok is True

    def test_icon_change_calls_handler(self):
        html = "<div>icon</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_icon_change_with_status",
            return_value=("<div>new icon</div>", True),
        ):
            result_html, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="el1",
                change_type="attribute",
                property_name="icon",
                new_value="star",
            )
        assert ok is True

    def test_delete_change_calls_handler(self):
        html = "<div>content</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_delete_change_with_status",
            return_value=("<div></div>", True),
        ):
            result_html, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="el1",
                change_type="delete",
                property_name="",
                new_value="",
                slide_number=1,
            )
        assert ok is True

    def test_exception_in_handler_returns_false(self):
        html = "<div>content</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_style_change_with_status",
            side_effect=Exception("parse error"),
        ):
            result_html, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="el1",
                change_type="style",
                property_name="color",
                new_value="blue",
            )
        assert ok is False
        assert "parse error" in reason


# ============================================================================
# _extract_slide_number
# ============================================================================


class TestExtractSlideNumber:
    def test_returns_slide_number_from_change(self):
        change = StyleChange(
            designId="el1",
            slideNumber=3,
            type="style",
            property="color",
            value={"to": "blue"},
            timestamp=1700000000,
        )
        result = SlideDesignService._extract_slide_number(change)
        assert result == 3

    def test_returns_zero_when_no_slide_number(self):
        change = StyleChange(
            designId="el1",
            type="style",
            property="color",
            value={"to": "blue"},
            timestamp=1700000000,
        )
        result = SlideDesignService._extract_slide_number(change)
        assert result == 0

    def test_returns_slide_number_from_element_context(self):
        from ii_agent.projects.design.schemas import ElementContext

        ctx = ElementContext(designId="el1", slideNumber=5, tagName="div")
        change = StyleChange(
            designId="el1",
            type="style",
            property="color",
            value={"to": "blue"},
            timestamp=1700000000,
            elementContext=ctx,
        )
        result = SlideDesignService._extract_slide_number(change)
        assert result == 5


# ============================================================================
# _parse_persisted_design_changes
# ============================================================================


class TestParsePersistedDesignChanges:
    def test_returns_empty_for_non_list(self):
        result = SlideDesignService._parse_persisted_design_changes("not a list")
        assert result == []

    def test_returns_empty_for_none(self):
        result = SlideDesignService._parse_persisted_design_changes(None)
        assert result == []

    def test_parses_valid_changes(self):
        raw = [
            {
                "designId": "el1",
                "type": "style",
                "property": "color",
                "value": {"to": "blue"},
                "timestamp": 1700000001,
            },
            {
                "designId": "el2",
                "type": "text",
                "property": "textContent",
                "value": {"to": "hello"},
                "timestamp": 1700000000,
            },
        ]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert len(result) == 2

    def test_skips_invalid_items(self):
        raw = [
            {"invalid": "data"},
            {
                "designId": "el1",
                "type": "style",
                "property": "color",
                "value": {"to": "blue"},
                "timestamp": 1700000000,
            },
        ]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert len(result) == 1

    def test_sorts_by_timestamp(self):
        raw = [
            {
                "designId": "el2",
                "type": "text",
                "property": "textContent",
                "value": {"to": "later"},
                "timestamp": 1700000002,
            },
            {
                "designId": "el1",
                "type": "style",
                "property": "color",
                "value": {"to": "blue"},
                "timestamp": 1700000000,
            },
        ]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert result[0].designId == "el1"
        assert result[1].designId == "el2"

    def test_skips_non_dict_items(self):
        raw = [
            "string",
            42,
            None,
            {"designId": "el1", "type": "style", "property": "c", "value": {}, "timestamp": 100},
        ]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert len(result) == 1


# ============================================================================
# _build_persisted_sync_result
# ============================================================================


class TestBuildPersistedSyncResult:
    def _service(self):
        return _make_service()

    def test_success_when_all_applied(self):
        service = self._service()
        result = service._build_persisted_sync_result(
            total=3,
            applied=3,
            remaining_changes=[],
            errors=[],
            sandbox_error=None,
        )
        assert result.success is True
        assert "3 slide design change" in result.summary

    def test_partial_success_message(self):
        from ii_agent.projects.design.schemas import StyleChange

        change = StyleChange(
            designId="el1",
            type="style",
            property="color",
            value={"to": "blue"},
            timestamp=1700000000,
        )
        service = self._service()
        result = service._build_persisted_sync_result(
            total=3,
            applied=2,
            remaining_changes=[change],
            errors=["some error"],
            sandbox_error=None,
        )
        assert result.success is False
        assert "2/3" in result.summary

    def test_sandbox_error_message(self):
        service = self._service()
        result = service._build_persisted_sync_result(
            total=3,
            applied=0,
            remaining_changes=[],
            errors=["sandbox unavailable"],
            sandbox_error="sandbox not found",
        )
        assert result.success is False
        assert "sandbox" in result.summary.lower()

    def test_full_failure_message(self):
        service = self._service()
        result = service._build_persisted_sync_result(
            total=3,
            applied=0,
            remaining_changes=[],
            errors=["failed to apply"],
            sandbox_error=None,
        )
        assert result.success is False
        assert "could not apply" in result.summary.lower()

    def test_singular_change_message(self):
        service = self._service()
        result = service._build_persisted_sync_result(
            total=1,
            applied=1,
            remaining_changes=[],
            errors=[],
            sandbox_error=None,
        )
        assert result.success is True
        assert "1 slide design change" in result.summary
        # No 's' suffix for singular
        assert "changes" not in result.summary
