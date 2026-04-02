from __future__ import annotations

from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_hook_utils_module() -> ModuleType:
    module_name = "test_slide_hook_utils_module"
    module_path = (
        Path(__file__).resolve().parents[3]
        / "ii_agent"
        / "agents"
        / "tools"
        / "slide_system"
        / "hook_utils.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook_utils_module() -> ModuleType:
    return _load_hook_utils_module()


def _make_agent() -> MagicMock:
    agent = MagicMock()
    agent.session_id = "session-123"
    return agent


@pytest.mark.asyncio
async def test_persist_slide_tool_result_uses_injected_slide_service(
    hook_utils_module: ModuleType,
):
    db = object()
    slide_service = MagicMock()
    slide_service.persist_tool_slide_result = AsyncMock()

    @asynccontextmanager
    async def fake_db_session():
        yield db

    hook_utils_module.get_db_session_local = fake_db_session

    await hook_utils_module.persist_slide_tool_result(
        agent=_make_agent(),
        slide_service=slide_service,
        tool_name="SlideGenerate",
        tool_input={
            "presentation_name": "Deck",
            "slide_number": 2,
            "title": "Agenda",
        },
        user_display_content={
            "content": "<html><title>Agenda</title></html>",
            "filepath": "/workspace/presentations/Deck/slide_002.html",
        },
    )

    slide_service.persist_tool_slide_result.assert_awaited_once_with(
        db,
        session_id="session-123",
        presentation_name="Deck",
        slide_number=2,
        slide_title="Agenda",
        slide_content="<html><title>Agenda</title></html>",
        tool_name="SlideGenerate",
    )


@pytest.mark.asyncio
async def test_persist_slide_tool_result_parses_patch_metadata_from_filepath(
    hook_utils_module: ModuleType,
):
    db = object()
    slide_service = MagicMock()
    slide_service.persist_tool_slide_result = AsyncMock()

    @asynccontextmanager
    async def fake_db_session():
        yield db

    hook_utils_module.get_db_session_local = fake_db_session

    await hook_utils_module.persist_slide_tool_result(
        agent=_make_agent(),
        slide_service=slide_service,
        tool_name="slide_apply_patch",
        tool_input={"input": "*** Begin Slide Patch"},
        user_display_content=[
            {
                "new_content": "<html><title>Closing</title></html>",
                "filepath": "/workspace/presentations/Deck_Final/slide_005.html",
            }
        ],
    )

    slide_service.persist_tool_slide_result.assert_awaited_once_with(
        db,
        session_id="session-123",
        presentation_name="Deck_Final",
        slide_number=5,
        slide_title="Closing",
        slide_content="<html><title>Closing</title></html>",
        tool_name="slide_apply_patch",
    )
