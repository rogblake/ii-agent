"""Targeted coverage tests for storybook router glue logic."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ii_agent.core.exceptions import PaymentRequiredError, ValidationError
from ii_agent.content.storybook.exceptions import (
    StorybookAccessDeniedError,
    StorybookNotFoundError,
    StorybookPageNotFoundError,
)
from ii_agent.content.storybook.router import (
    _format_content_disposition,
    ai_generate_storybook_background,
    ai_rewrite_storybook_content,
    ai_regenerate_storybook_image,
    cancel_storybook_generation,
    download_storybook,
    generate_storybook_voiceover,
    get_session_storybooks,
    get_storybook,
    get_storybook_progress,
    get_storybook_versions,
    proxy_storybook_edit_page,
    regenerate_page_image,
    save_storybook_edits,
    update_page_text,
    upload_storybook_background,
)
from ii_agent.sessions.exceptions import SessionNotFoundError


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1")


def _session(
    storybook_id: str = "sb-1", session_id: str = "session-1"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=storybook_id,
        session_id=session_id,
        name="My Storybook",
        version=1,
        root_storybook_id=None,
        parent_storybook_id=None,
        aspect_ratio="16:9",
        resolution="1K",
        style_json=None,
        page_count=0,
        created_at=None,
        updated_at=None,
        pages=[],
    )


@pytest.mark.asyncio
async def test_get_session_storybooks_success():
    service = AsyncMock()
    service.get_session_storybooks.return_value = SimpleNamespace(items=[])
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}

    result = await get_session_storybooks(
        "session-1",
        _user(),
        service,
        session_service,
        None,
        include_pages=True,
    )

    assert result.items == []


@pytest.mark.asyncio
async def test_get_session_storybooks_access_denied():
    service = AsyncMock()
    session_service = AsyncMock()
    session_service.get_session_details.return_value = None

    with pytest.raises(SessionNotFoundError):
        await get_session_storybooks("session-1", _user(), service, session_service, None)


@pytest.mark.asyncio
async def test_get_storybook_success_and_access_denied():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}

    result = await get_storybook("sb-1", _user(), service, session_service, None)
    assert result.id == "sb-1"

    session_service.get_session_details.return_value = None
    with pytest.raises(StorybookAccessDeniedError):
        await get_storybook("sb-1", _user(), service, session_service, None)


@pytest.mark.asyncio
async def test_get_storybook_not_found():
    service = AsyncMock()
    service.get_storybook_detail.return_value = None
    session_service = AsyncMock()

    with pytest.raises(StorybookNotFoundError):
        await get_storybook("sb-1", _user(), service, session_service, None)


@pytest.mark.asyncio
async def test_generate_storybook_voiceover_success():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    voice_service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    voice_service.generate_voiceover_and_deduct_credits.return_value = (
        SimpleNamespace(audio_url="ok")
    )

    result = await generate_storybook_voiceover(
        "sb-1",
        _user(),
        service,
        voice_service,
        session_service,
        None,
    )
    assert result.audio_url == "ok"


@pytest.mark.asyncio
async def test_generate_storybook_voiceover_not_found():
    service = AsyncMock()
    service.get_storybook_detail.return_value = None
    voice_service = AsyncMock()
    session_service = AsyncMock()

    with pytest.raises(StorybookNotFoundError):
        await generate_storybook_voiceover(
            "sb-1",
            _user(),
            service,
            voice_service,
            session_service,
            None,
        )


@pytest.mark.asyncio
async def test_get_storybook_progress_builds_generation_payload():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    session_service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    service.build_generation_response = Mock(return_value=SimpleNamespace(status="done"))
    session_service.get_session_details.return_value = {"id": "session-1"}

    result = await get_storybook_progress("sb-1", _user(), service, session_service, None)
    assert result.status == "done"


@pytest.mark.asyncio
async def test_cancel_storybook_generation_completed_and_running():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    voice_service = AsyncMock()

    voice_service.get_generation_status = Mock(return_value="completed")
    result = await cancel_storybook_generation(
        "sb-1", _user(), service, voice_service, session_service, None
    )
    assert result["success"] is False
    assert "already completed" in result["message"]

    voice_service.get_generation_status = Mock(return_value="running")
    voice_service.reset_mock()
    result = await cancel_storybook_generation(
        "sb-1", _user(), service, voice_service, session_service, None
    )
    assert result["success"] is True
    voice_service.cancel_generation.assert_awaited_once_with(None, "sb-1")


@pytest.mark.asyncio
async def test_update_and_regenerate_page_image_flow():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    version_service = AsyncMock()
    version_service.update_page_text.return_value = _session("sb-2", "session-1")
    updated = await update_page_text(
        "sb-1",
        1,
        SimpleNamespace(text_content="hi"),
        _user(),
        service,
        version_service,
        session_service,
        None,
    )
    assert updated.success

    user_service = AsyncMock()
    user_service.get_active_api_key.return_value = None
    version_service.reset_mock()

    with pytest.raises(ValidationError):
        await regenerate_page_image(
            "sb-1",
            1,
            SimpleNamespace(image_prompt="x"),
            _user(),
            service,
            version_service,
            session_service,
            user_service,
            None,
        )


@pytest.mark.asyncio
async def test_proxy_storybook_edit_page_returns_html_response_or_raises():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    edit_service = AsyncMock()
    edit_service.get_page_html_with_runtime.return_value = "<html/>"
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}

    result = await proxy_storybook_edit_page(
        "sb-1",
        _user(),
        service,
        edit_service,
        session_service,
        None,
        page_number=1,
    )
    assert result.status_code == 200

    edit_service.get_page_html_with_runtime.return_value = None
    with pytest.raises(StorybookPageNotFoundError):
        await proxy_storybook_edit_page(
            "sb-1",
            _user(),
            service,
            edit_service,
            session_service,
            None,
            page_number=1,
        )


@pytest.mark.asyncio
async def test_save_storybook_edits_validation_and_cost_handling():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    edit_service = AsyncMock()
    usage_service = AsyncMock()
    db = AsyncMock()
    db.rollback = AsyncMock()

    edit_request = SimpleNamespace(storybook_id="sb-1", page_changes=[])
    mismatch = SimpleNamespace(storybook_id="other", page_changes=[SimpleNamespace()])
    result = await save_storybook_edits(
        "sb-1",
        mismatch,
        _user(),
        service,
        edit_service,
        usage_service,
        session_service,
        db,
    )
    assert result.success is False
    assert result.error == "Path storybook_id does not match request.storybook_id"

    edit_request.page_changes = []
    result = await save_storybook_edits(
        "sb-1",
        edit_request,
        _user(),
        service,
        edit_service,
        usage_service,
        session_service,
        db,
    )
    assert result.success is False
    assert result.error == "No changes to save"

    edit_service.save_all_page_edits.return_value = (
        _session("sb-2", "session-1"),
        0.0,
    )
    edit_request.page_changes = [SimpleNamespace(changes=None, image_url=None, page_number=1)]
    result = await save_storybook_edits(
        "sb-1",
        edit_request,
        _user(),
        service,
        edit_service,
        usage_service,
        session_service,
        db,
    )
    assert result.success is False
    assert result.error == "No changes to save"

    edit_request.page_changes = [SimpleNamespace(changes=[SimpleNamespace()], image_url=None, page_number=1)]
    result = await save_storybook_edits(
        "sb-1",
        edit_request,
        _user(),
        service,
        edit_service,
        usage_service,
        session_service,
        db,
    )
    assert result.success is True

    edit_service.save_all_page_edits.return_value = (
        _session("sb-3", "session-1"),
        1.0,
    )
    usage_service.deduct_and_track_session_usage.return_value = False
    with pytest.raises(PaymentRequiredError):
        await save_storybook_edits(
            "sb-1",
            edit_request,
            _user(),
            service,
            edit_service,
            usage_service,
            session_service,
            db,
        )


@pytest.mark.asyncio
async def test_storybook_versions_and_download_and_upload_background():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    edit_service = AsyncMock()
    edit_service.get_version_history.return_value = [
        {"id": "v1", "version": 1, "is_current": True, "created_at": None},
        {"id": "v2", "version": 2, "is_current": False, "created_at": None},
    ]
    result = await get_storybook_versions(
        "sb-1",
        _user(),
        service,
        edit_service,
        session_service,
        None,
    )
    assert len(result.versions) == 2

    media_storage = SimpleNamespace(
        upload_and_get_permanent_url=Mock(return_value="https://cdn/cover.png"),
    )
    upload_request = SimpleNamespace(
        filename="cover.png",
        content_type="image/png",
        file=SimpleNamespace(),
    )
    response = await upload_storybook_background(
        "sb-1",
        _user(),
        service,
        session_service,
        media_storage,
        None,
        file=upload_request,
    )
    assert response.url == "https://cdn/cover.png"

    upload_request.content_type = "text/plain"
    with pytest.raises(ValidationError):
        await upload_storybook_background(
            "sb-1",
            _user(),
            service,
            session_service,
            media_storage,
            None,
            file=upload_request,
        )

    export_service = AsyncMock()
    export_service.download_storybook_as_pdf.return_value = b"pdf-bytes"
    response = await download_storybook(
        "sb-1",
        _user(),
        service,
        export_service,
        session_service,
        None,
    )
    assert response.media_type == "application/pdf"
    assert response.body == b"pdf-bytes"


@pytest.mark.asyncio
async def test_ai_storybook_edit_endpoints():
    storybook = _session("sb-1", "session-1")
    service = AsyncMock()
    service.get_storybook_detail.return_value = storybook
    session_service = AsyncMock()
    session_service.get_session_details.return_value = {"id": "session-1"}
    ai_service = AsyncMock()

    mismatch = SimpleNamespace(storybook_id="other")
    assert (
        (
            await ai_rewrite_storybook_content(
                "sb-1",
                mismatch,
                _user(),
                service,
                session_service,
                ai_service,
                None,
            )
        ).success
        is False
    )

    ai_service.rewrite_content.return_value = "rewritten"
    rewrite = SimpleNamespace(storybook_id="sb-1", content="text", page_image_url="x")
    result = await ai_rewrite_storybook_content(
        "sb-1",
        rewrite,
        _user(),
        service,
        session_service,
        ai_service,
        None,
    )
    assert result.success is True
    assert result.rewritten_content == "rewritten"

    ai_service.generate_background.return_value = "img://ok"
    background = SimpleNamespace(
        storybook_id="sb-1",
        prompt="pretty",
        page_image_url="x",
        text_position="center",
    )
    result = await ai_generate_storybook_background(
        "sb-1",
        background,
        _user(),
        service,
        session_service,
        ai_service,
        None,
    )
    assert result.success is True
    assert result.image_url == "img://ok"

    ai_service.regenerate_image.return_value = "img://repl"
    regenerate = SimpleNamespace(
        storybook_id="sb-1",
        page_number=1,
        prompt="a",
        reference_image_url="x",
        scene_text="y",
        text_position="center",
        text_percentage=0.5,
    )
    result = await ai_regenerate_storybook_image(
        "sb-1",
        regenerate,
        _user(),
        service,
        session_service,
        ai_service,
        None,
    )
    assert result.success is True
    assert result.image_url == "img://repl"


def test_format_content_disposition_handles_filename():
    assert 'filename="story.pdf"' in _format_content_disposition("story.pdf")
