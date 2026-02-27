"""Unit tests for ii_agent.content.slides.design.service – SlideDesignService."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.slides.design.service import SlideDesignService
from ii_agent.content.slides.design.schemas import (
    SlideDeckSyncBatchRequest,
    SlideDeckSyncBatchResponse,
    SlideDeckSyncChange,
    SlideSyncBatchRequest,
    SlideSyncBatchResponse,
    SlideSyncChange,
)
from ii_agent.projects.design.exceptions import (
    DesignSessionAccessDeniedError,
    DesignSessionNotFoundError,
    DesignValidationError,
)
from ii_agent.projects.design.models import DesignSyncCounters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(
    repo=None,
    sandbox_service=None,
    event_service=None,
    config=None,
) -> SlideDesignService:
    repo = repo or MagicMock()
    sandbox_service = sandbox_service or MagicMock()
    event_service = event_service or MagicMock()
    config = config or MagicMock(workspace_path="/workspace")
    return SlideDesignService(
        repo=repo,
        sandbox_service=sandbox_service,
        event_service=event_service,
        config=config,
    )


def _mock_slide(number: int, content: str = "<div>slide</div>"):
    slide = MagicMock()
    slide.slide_number = number
    slide.slide_content = content
    slide.slide_title = f"Slide {number}"
    return slide


def _style_change(
    design_id: str,
    change_type: str,
    prop: str = "color",
    value: Any = "red",
    slide_number: int = 0,
    timestamp: int = 1000,
) -> dict:
    return {
        "designId": design_id,
        "type": change_type,
        "property": prop,
        "value": {"to": value},
        "timestamp": timestamp,
        "slideNumber": slide_number,
    }


# ---------------------------------------------------------------------------
# SlideDesignService instantiation
# ---------------------------------------------------------------------------

class TestSlideDesignServiceInit:
    def test_can_instantiate(self):
        service = _make_service()
        assert isinstance(service, SlideDesignService)

    def test_stores_config(self):
        config = MagicMock(workspace_path="/ws")
        service = _make_service(config=config)
        assert service._config is config


# ---------------------------------------------------------------------------
# _get_session_for_request
# ---------------------------------------------------------------------------

class TestGetSessionForRequest:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        db = MagicMock()
        with pytest.raises(DesignSessionNotFoundError):
            await service._get_session_for_request(
                db, session_id="s1", user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_raises_when_user_id_mismatch(self):
        session = MagicMock()
        session.user_id = "u99"
        repo = MagicMock()
        repo.get_session = AsyncMock(return_value=session)
        service = _make_service(repo=repo)
        db = MagicMock()
        with pytest.raises(DesignSessionAccessDeniedError):
            await service._get_session_for_request(
                db, session_id="s1", user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_returns_session_when_valid(self):
        session = MagicMock()
        session.user_id = "u1"
        repo = MagicMock()
        repo.get_session = AsyncMock(return_value=session)
        service = _make_service(repo=repo)
        db = MagicMock()
        result = await service._get_session_for_request(
            db, session_id="s1", user_id="u1"
        )
        assert result is session


# ---------------------------------------------------------------------------
# get_slide_proxy_html
# ---------------------------------------------------------------------------

class TestGetSlideProxyHtml:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        with pytest.raises(DesignSessionNotFoundError):
            await service.get_slide_proxy_html(
                MagicMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="deck",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_raises_when_slide_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_slide = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        from ii_agent.content.slides.design.exceptions import DesignSlideNotFoundError
        with pytest.raises(DesignSlideNotFoundError):
            await service.get_slide_proxy_html(
                MagicMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="deck",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_raises_when_slide_has_no_content(self):
        slide = MagicMock()
        slide.slide_content = ""
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_slide = AsyncMock(return_value=slide)
        service = _make_service(repo=repo)
        from ii_agent.content.slides.design.exceptions import DesignSlideNotFoundError
        with pytest.raises(DesignSlideNotFoundError):
            await service.get_slide_proxy_html(
                MagicMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="deck",
                slide_number=1,
            )

    @pytest.mark.asyncio
    async def test_returns_html_on_success(self):
        slide = MagicMock()
        slide.slide_content = "<html><body>slide</body></html>"
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_slide = AsyncMock(return_value=slide)
        service = _make_service(repo=repo)
        with patch(
            "ii_agent.content.slides.design.service.sanitize_legacy_editable_artifacts",
            side_effect=lambda h: h,
        ), patch(
            "ii_agent.content.slides.design.service.inject_runtime_script_only",
            side_effect=lambda h: f"INJECTED:{h}",
        ):
            result = await service.get_slide_proxy_html(
                MagicMock(),
                session_id="s1",
                user_id="u1",
                presentation_name="deck",
                slide_number=1,
            )
        assert result.startswith("INJECTED:")


# ---------------------------------------------------------------------------
# apply_slide_sync_batch – counters and no-op on no changes
# ---------------------------------------------------------------------------

class TestApplySlideSyncBatch:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            changes=[],
        )
        with pytest.raises(DesignSessionNotFoundError):
            await service.apply_slide_sync_batch(MagicMock(), request=request, user_id="u1")

    @pytest.mark.asyncio
    async def test_returns_success_when_no_changes_applied(self):
        slide = _mock_slide(1, "<div>content</div>")
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_slide = AsyncMock(return_value=slide)
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            changes=[],
        )
        response = await service.apply_slide_sync_batch(MagicMock(), request=request, user_id="u1")
        assert isinstance(response, SlideSyncBatchResponse)
        assert response.success is True
        assert response.processed == 0

    @pytest.mark.asyncio
    async def test_increments_failed_counter_for_unknown_type(self):
        slide = _mock_slide(1, "<div>content</div>")
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_slide = AsyncMock(return_value=slide)
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)
        change = SlideSyncChange(
            design_id="d1",
            type="unknown_type",
            property="x",
            value={"to": "y"},
        )
        request = SlideSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            changes=[change],
        )
        response = await service.apply_slide_sync_batch(MagicMock(), request=request, user_id="u1")
        assert response.failed >= 1
        assert response.success is False


# ---------------------------------------------------------------------------
# apply_slide_deck_sync_batch – empty changes short-circuit
# ---------------------------------------------------------------------------

class TestApplySlideDeckSyncBatch:
    @pytest.mark.asyncio
    async def test_returns_success_immediately_for_empty_changes(self):
        service = _make_service()
        request = SlideDeckSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            changes=[],
        )
        result = await service.apply_slide_deck_sync_batch(
            MagicMock(), request=request, user_id="u1"
        )
        assert isinstance(result, SlideDeckSyncBatchResponse)
        assert result.success is True
        assert result.processed == 0

    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        change = SlideDeckSyncChange(
            slide_number=1,
            design_id="d1",
            type="style",
            property="color",
            value={"to": "red"},
        )
        request = SlideDeckSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            changes=[change],
        )
        with pytest.raises(DesignSessionNotFoundError):
            await service.apply_slide_deck_sync_batch(
                MagicMock(), request=request, user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_fails_changes_with_invalid_slide_number(self):
        slide = _mock_slide(1)
        repo = MagicMock()
        repo.get_session_for_user = AsyncMock(return_value=MagicMock())
        repo.get_presentation_slides = AsyncMock(return_value=[slide])
        repo.update_slide_html = AsyncMock()
        service = _make_service(repo=repo)
        change = SlideDeckSyncChange(
            slide_number=0,  # invalid
            design_id="d1",
            type="style",
            property="color",
            value={"to": "red"},
        )
        request = SlideDeckSyncBatchRequest(
            session_id="s1",
            presentation_name="deck",
            changes=[change],
        )
        result = await service.apply_slide_deck_sync_batch(
            MagicMock(), request=request, user_id="u1"
        )
        assert result.failed >= 1


# ---------------------------------------------------------------------------
# _apply_single_change – static method
# ---------------------------------------------------------------------------

class TestApplySingleChange:
    def test_returns_false_for_unknown_change_type(self):
        html = "<div>content</div>"
        updated, ok, reason = SlideDesignService._apply_single_change(
            html,
            design_id="d1",
            change_type="unknown",
            property_name="x",
            new_value="y",
        )
        assert ok is False
        assert "Unsupported" in (reason or "")

    def test_handles_exception_gracefully(self):
        html = "<div>content</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_style_change_with_status",
            side_effect=RuntimeError("boom"),
        ):
            updated, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="d1",
                change_type="style",
                property_name="color",
                new_value="red",
            )
        assert ok is False
        assert reason is not None

    def test_dispatches_style_change(self):
        html = "<div data-design-id='d1'>content</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_style_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            updated, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="d1",
                change_type="style",
                property_name="color",
                new_value="blue",
            )
        assert mock_fn.called
        assert ok is True

    def test_dispatches_text_change(self):
        html = "<p data-design-id='t1'>old</p>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_text_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            updated, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="t1",
                change_type="text",
                property_name="",
                new_value="new text",
            )
        assert mock_fn.called

    def test_dispatches_delete_change(self):
        html = "<div data-design-id='del1'>bye</div>"
        with patch(
            "ii_agent.content.slides.design.service.apply_slide_delete_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            updated, ok, reason = SlideDesignService._apply_single_change(
                html,
                design_id="del1",
                change_type="delete",
                property_name="",
                new_value="",
            )
        assert mock_fn.called


# ---------------------------------------------------------------------------
# _extract_slide_number – static method
# ---------------------------------------------------------------------------

class TestExtractSlideNumberStatic:
    def test_returns_slide_number_from_change(self):
        from ii_agent.projects.design.schemas import StyleChange
        change = StyleChange.model_validate(_style_change("d1", "style", slide_number=3))
        assert SlideDesignService._extract_slide_number(change) == 3

    def test_returns_zero_when_no_slide_number(self):
        from ii_agent.projects.design.schemas import StyleChange
        data = {
            "designId": "d1",
            "type": "style",
            "property": "color",
            "value": {"to": "red"},
            "timestamp": 1000,
            "slideNumber": None,
        }
        change = StyleChange.model_validate(data)
        assert SlideDesignService._extract_slide_number(change) == 0


# ---------------------------------------------------------------------------
# _parse_persisted_design_changes – static method
# ---------------------------------------------------------------------------

class TestParsePersistedDesignChanges:
    def test_returns_empty_for_non_list(self):
        result = SlideDesignService._parse_persisted_design_changes("not a list")
        assert result == []

    def test_returns_empty_for_none(self):
        result = SlideDesignService._parse_persisted_design_changes(None)
        assert result == []

    def test_skips_non_dict_items(self):
        result = SlideDesignService._parse_persisted_design_changes(["str", 42, None])
        assert result == []

    def test_parses_valid_change_dicts(self):
        raw = [_style_change("d1", "style", slide_number=2, timestamp=5000)]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert len(result) == 1
        assert result[0].designId == "d1"

    def test_sorts_by_timestamp(self):
        raw = [
            _style_change("d2", "style", timestamp=2000, slide_number=1),
            _style_change("d1", "style", timestamp=1000, slide_number=1),
        ]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert result[0].timestamp == 1000
        assert result[1].timestamp == 2000

    def test_skips_invalid_change_dicts(self):
        raw = [{"invalid": "data", "no_required_fields": True}]
        result = SlideDesignService._parse_persisted_design_changes(raw)
        assert result == []


# ---------------------------------------------------------------------------
# _build_persisted_sync_result – summary generation
# ---------------------------------------------------------------------------

class TestBuildPersistedSyncResult:
    def test_success_summary_when_all_applied(self):
        service = _make_service()
        result = service._build_persisted_sync_result(
            total=3, applied=3, remaining_changes=[], errors=[], sandbox_error=None
        )
        assert result.success is True
        assert "3" in result.summary

    def test_partial_summary_when_some_applied(self):
        service = _make_service()
        from ii_agent.projects.design.schemas import StyleChange
        remaining = [StyleChange.model_validate(_style_change("d1", "style"))]
        result = service._build_persisted_sync_result(
            total=3, applied=2, remaining_changes=remaining, errors=["err"], sandbox_error=None
        )
        assert result.success is False
        assert "2" in result.summary

    def test_sandbox_error_summary_when_zero_applied(self):
        service = _make_service()
        result = service._build_persisted_sync_result(
            total=2,
            applied=0,
            remaining_changes=[],
            errors=["sandbox down"],
            sandbox_error="sandbox down",
        )
        assert result.success is False
        assert "sandbox" in result.summary.lower()

    def test_generic_failure_summary_when_no_sandbox_error(self):
        service = _make_service()
        result = service._build_persisted_sync_result(
            total=2, applied=0, remaining_changes=[], errors=["nope"], sandbox_error=None
        )
        assert result.success is False

    def test_singular_form_for_one_change(self):
        service = _make_service()
        result = service._build_persisted_sync_result(
            total=1, applied=1, remaining_changes=[], errors=[], sandbox_error=None
        )
        assert "change" in result.summary
