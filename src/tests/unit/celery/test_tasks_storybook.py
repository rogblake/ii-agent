from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.workers.celery import tasks


@pytest.mark.asyncio
async def test_generate_storybook_page_async_invalid_payload():
    missing_storybook = await tasks._generate_storybook_page_async(
        payload={"scene_index": 0},
        task_id="task-1",
    )
    assert missing_storybook["status"] == "invalid_payload"

    invalid_scene = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": "abc"},
        task_id="task-1",
    )
    assert invalid_scene["status"] == "invalid_payload"

    negative_scene = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": -1},
        task_id="task-1",
    )
    assert negative_scene["status"] == "invalid_payload"


@pytest.mark.asyncio
async def test_generate_storybook_page_async_storybook_not_found(monkeypatch):
    class _Repo:
        async def get_by_id(self, db_session, storybook_id):
            return None

    @asynccontextmanager
    async def _db_cm():
        yield object()

    monkeypatch.setattr(
        "ii_agent.content.storybook.repository.StorybookRepository",
        lambda: _Repo(),
    )
    monkeypatch.setattr(
        "ii_agent.core.db.manager.get_db_session_local",
        _db_cm,
    )

    result = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": 0},
        task_id="task-1",
    )
    assert result["status"] == "storybook_not_found"


@pytest.mark.asyncio
async def test_handle_storybook_page_failure_no_storybook_id():
    assert await tasks._handle_storybook_page_failure({}, "boom") is None


def test_storybook_generate_page_task_success(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "_run_async",
        lambda coro: (coro.close(), {"status": "queued", "next_scene_index": 1})[1],
    )

    result = tasks.storybook_generate_page(
        {"storybook_id": "sb-1", "scene_index": 0},
    )

    assert result == {"status": "queued", "next_scene_index": 1}


def test_storybook_generate_page_task_exception_path(monkeypatch):
    calls = {"count": 0}

    def _run_async(coro):
        calls["count"] += 1
        coro.close()
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return None

    monkeypatch.setattr(tasks, "_run_async", _run_async)

    result = tasks.storybook_generate_page(
        {"storybook_id": "sb-1", "scene_index": 0},
    )

    assert result["status"] == "failed"
    assert "boom" in result["error"]
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_generate_storybook_page_async_early_status_branches(monkeypatch):
    @asynccontextmanager
    async def _db_cm():
        yield object()

    monkeypatch.setattr("ii_agent.core.db.manager.get_db_session_local", _db_cm)

    class _Repo:
        def __init__(self, storybook):
            self._storybook = storybook

        async def get_by_id(self, db_session, storybook_id):
            return self._storybook

    async def _run_with_storybook(storybook, payload, *, cancelled=False):
        monkeypatch.setattr(
            "ii_agent.content.storybook.repository.StorybookRepository",
            lambda: _Repo(storybook),
        )
        monkeypatch.setattr(tasks.cancel, "is_cancelled", AsyncMock(return_value=cancelled))
        monkeypatch.setattr(tasks, "_fail_storybook", AsyncMock())
        return await tasks._generate_storybook_page_async(payload, "task-1")

    failed_storybook = type(
        "Storybook",
        (),
        {"style_json": {"generation": {"status": "failed"}}, "session_id": "s1"},
    )()
    failed = await _run_with_storybook(
        failed_storybook,
        {"storybook_id": "sb-1", "scene_index": 0},
    )
    assert failed["status"] == "failed"

    cancelled_storybook = type(
        "Storybook",
        (),
        {"style_json": {"generation": {"status": "generating", "scenes": [{}]}}, "session_id": "s1"},
    )()
    cancelled = await _run_with_storybook(
        cancelled_storybook,
        {"storybook_id": "sb-1", "scene_index": 0},
        cancelled=True,
    )
    assert cancelled["status"] == "cancelled"

    missing_scenes_storybook = type(
        "Storybook",
        (),
        {"style_json": {"generation": {"status": "generating"}}, "session_id": "s1"},
    )()
    missing_scenes = await _run_with_storybook(
        missing_scenes_storybook,
        {"storybook_id": "sb-1", "scene_index": 0},
    )
    assert missing_scenes["status"] == "failed"
    assert missing_scenes["error"] == "scenes_missing"

    out_of_range_storybook = type(
        "Storybook",
        (),
        {
            "style_json": {
                "generation": {"status": "generating", "scenes": [{}], "completed_pages": 0}
            },
            "session_id": "s1",
        },
    )()
    out_of_range = await _run_with_storybook(
        out_of_range_storybook,
        {"storybook_id": "sb-1", "scene_index": 2},
    )
    assert out_of_range["status"] == "out_of_range"

    no_session_storybook = type(
        "Storybook",
        (),
        {"style_json": {"generation": {"status": "generating", "scenes": [{}]}}, "session_id": ""},
    )()
    no_session = await _run_with_storybook(
        no_session_storybook,
        {"storybook_id": "sb-1", "scene_index": 0},
    )
    assert no_session["status"] == "failed"
    assert no_session["error"] == "session_not_found"


def test_storybook_page_helpers():
    assert tasks._scene_base_page_number(0, separate_page=False) == 1
    assert tasks._scene_base_page_number(2, separate_page=True) == 4
    assert tasks._db_page_to_display_page(1, separate_page_mode=True) == 1
    assert tasks._db_page_to_display_page(4, separate_page_mode=True) == 3
    assert tasks._db_page_to_display_page(3, separate_page_mode=False) == 3

    assert tasks._resolve_storybook_language({"language_code": "ko"}) == "ko"
    assert tasks._resolve_storybook_language({"languageCode": "ja"}) == "ja"
    assert tasks._resolve_storybook_language({"language": "en"}) == "en"
    assert tasks._resolve_storybook_language({"storybook_language": "fr"}) == "fr"
    assert tasks._resolve_storybook_language({}) is None

    assert tasks._get_voice_cost_usd({"voice_cost_usd": 0.3}) == 0.3
    assert tasks._get_voice_cost_usd({"audio_cost": 0.2}) == 0.2
    assert tasks._get_voice_cost_usd({"audio_cost": 0}) == 0.0


@pytest.mark.asyncio
async def test_generate_storybook_page_async_completed_with_existing_image(monkeypatch):
    session_id = "00000000-0000-0000-0000-000000000001"
    storybook = SimpleNamespace(
        id="sb-1",
        session_id=session_id,
        name="My Book",
        aspect_ratio="16:9",
        resolution="1024x768",
        style_json={
            "generation": {
                "status": "generating",
                "scenes": [{"text": "scene-1"}],
                "credits_checked": True,
                "tool_call_id": "tool-1",
                "model_id": "model-1",
            },
        },
    )

    class _Repo:
        async def get_by_id(self, db_session, storybook_id):
            return storybook

        async def get_page_by_number(self, db_session, storybook_id, page_number):
            return SimpleNamespace(
                page_number=1,
                image_url="https://example.com/1.png",
                text_content="hello",
                audio_link=None,
                metadata={},
            )

    @asynccontextmanager
    async def _db_cm():
        yield object()

    update_status = AsyncMock()
    container = SimpleNamespace(
        session_service=SimpleNamespace(
            get_session_by_id=AsyncMock(return_value=SimpleNamespace(user_id="user-1"))
        ),
        user_service=SimpleNamespace(get_active_api_key=AsyncMock(return_value="api-key")),
        storybook_service=SimpleNamespace(update_generation_status=update_status),
    )

    class _Tool:
        user_text_position = "none"

        def _build_style_context(self, style_json):
            return {}

        async def _process_single_scene(self, **kwargs):  # pragma: no cover - not used in this branch
            return [], "", 0.0

    monkeypatch.setattr("ii_agent.core.db.manager.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.content.storybook.repository.StorybookRepository", lambda: _Repo())
    monkeypatch.setattr(tasks, "get_celery_container", lambda: container)
    monkeypatch.setattr(tasks.cancel, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(tasks, "_setup_storybook_tool", lambda payload, session_id: _Tool())
    monkeypatch.setattr(tasks, "_mark_scene_completed", AsyncMock(return_value=True))
    monkeypatch.setattr(tasks, "_deduct_storybook_credits", AsyncMock(return_value=True))
    create_result = AsyncMock()
    monkeypatch.setattr(tasks, "_create_storybook_tool_result", create_result)

    result = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": 0},
        task_id="task-1",
    )

    assert result == {"status": "completed", "completed_pages": 1}
    create_result.assert_awaited_once()
    assert update_status.await_count >= 2


@pytest.mark.asyncio
async def test_generate_storybook_page_async_queued_after_scene_generation(monkeypatch):
    session_id = "00000000-0000-0000-0000-000000000002"
    storybook = SimpleNamespace(
        id="sb-1",
        session_id=session_id,
        name="My Book",
        aspect_ratio="16:9",
        resolution="1024x768",
        style_json={
            "generation": {
                "status": "generating",
                "scenes": [{"text": "scene-1"}, {"text": "scene-2"}],
                "credits_checked": True,
            },
        },
    )

    class _Repo:
        async def get_by_id(self, db_session, storybook_id):
            return storybook

        async def get_page_by_number(self, db_session, storybook_id, page_number):
            return None

    @asynccontextmanager
    async def _db_cm():
        yield object()

    update_status = AsyncMock()
    container = SimpleNamespace(
        session_service=SimpleNamespace(
            get_session_by_id=AsyncMock(return_value=SimpleNamespace(user_id="user-1"))
        ),
        user_service=SimpleNamespace(get_active_api_key=AsyncMock(return_value="api-key")),
        storybook_service=SimpleNamespace(update_generation_status=update_status),
    )

    class _Tool:
        user_text_position = "none"

        def _build_style_context(self, style_json):
            return {"ctx": True}

        async def _process_single_scene(self, **kwargs):
            return [SimpleNamespace()], "https://example.com/new.png", 0.0

    monkeypatch.setattr("ii_agent.core.db.manager.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.content.storybook.repository.StorybookRepository", lambda: _Repo())
    monkeypatch.setattr(tasks, "get_celery_container", lambda: container)
    monkeypatch.setattr(tasks.cancel, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(tasks, "_setup_storybook_tool", lambda payload, session_id: _Tool())
    monkeypatch.setattr(tasks, "_mark_scene_completed", AsyncMock(return_value=False))
    queue_mock = AsyncMock(return_value="next-task")
    monkeypatch.setattr(tasks, "queue_task", queue_mock)

    result = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": 0},
        task_id="task-1",
    )

    assert result == {"status": "queued", "next_scene_index": 1}
    assert queue_mock.call_count == 1


@pytest.mark.asyncio
async def test_generate_storybook_page_async_api_key_missing_path(monkeypatch):
    session_id = "00000000-0000-0000-0000-000000000003"
    storybook = SimpleNamespace(
        id="sb-1",
        session_id=session_id,
        style_json={"generation": {"status": "generating", "scenes": [{"text": "scene"}]}},
    )

    class _Repo:
        async def get_by_id(self, db_session, storybook_id):
            return storybook

    @asynccontextmanager
    async def _db_cm():
        yield object()

    container = SimpleNamespace(
        session_service=SimpleNamespace(
            get_session_by_id=AsyncMock(return_value=SimpleNamespace(user_id="user-1"))
        ),
        user_service=SimpleNamespace(get_active_api_key=AsyncMock(return_value=None)),
        storybook_service=SimpleNamespace(update_generation_status=AsyncMock()),
    )
    fail_storybook = AsyncMock()
    monkeypatch.setattr(tasks, "_fail_storybook", fail_storybook)
    monkeypatch.setattr(tasks.cancel, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(tasks, "get_celery_container", lambda: container)
    monkeypatch.setattr("ii_agent.core.db.manager.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.content.storybook.repository.StorybookRepository", lambda: _Repo())

    result = await tasks._generate_storybook_page_async(
        payload={"storybook_id": "sb-1", "scene_index": 0},
        task_id="task-1",
    )

    assert result == {"status": "failed", "error": "api_key_missing"}
    fail_storybook.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_storybook_page_failure_marks_failed(monkeypatch):
    storybook = SimpleNamespace(
        id="sb-1",
        session_id="00000000-0000-0000-0000-000000000004",
        style_json={"generation": {"tool_name": "generate_storybook"}},
    )

    class _Repo:
        async def get_by_id(self, db_session, storybook_id):
            return storybook

    @asynccontextmanager
    async def _db_cm():
        yield object()

    fail_storybook = AsyncMock()
    monkeypatch.setattr(tasks, "_fail_storybook", fail_storybook)
    monkeypatch.setattr("ii_agent.core.db.manager.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.content.storybook.repository.StorybookRepository", lambda: _Repo())

    await tasks._handle_storybook_page_failure({"storybook_id": "sb-1"}, "boom")

    fail_storybook.assert_awaited_once()
