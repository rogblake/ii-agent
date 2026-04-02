from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent_tools.client.input_validator import InputValidator
from ii_agent_tools.client.tool_client import IIToolClient
from ii_agent_tools.integrations.video_generation.base import VideoGenerationResult
from ii_agent_tools.integrations.video_generation.service import VideoGenerationService


class RecordingStorage:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    async def write(self, content, path: str, content_type: str | None = None):
        content.seek(0)
        self.writes.append(
            {
                "path": path,
                "content": content.read(),
                "content_type": content_type,
            }
        )

    async def write_from_url(self, url: str, path: str, content_type: str | None = None) -> str:
        raise AssertionError("write_from_url should not be used in this test")

    async def write_from_local_path(
        self, local_path: str, target_path: str, content_type: str | None = None
    ) -> str:
        raise AssertionError("write_from_local_path should not be used in this test")

    def get_public_url(self, path: str) -> str:
        return f"https://public.local/{path}"


@pytest.mark.asyncio
async def test_tool_client_video_generation_accepts_inline_base64_frames():
    expected = VideoGenerationResult(url="https://videos.local/generated.mp4")
    client = IIToolClient.__new__(IIToolClient)
    client.input_validator = InputValidator()
    client.video_generation_service = SimpleNamespace(
        generate_video=AsyncMock(return_value=expected)
    )

    frame_base64 = base64.b64encode(b"inline-frame").decode("utf-8")

    result = await client.video_generation(
        prompt="Generate a short clip",
        start_frame_base64=frame_base64,
        start_frame_mime_type="image/png",
    )

    assert result == expected
    client.video_generation_service.generate_video.assert_awaited_once()
    kwargs = client.video_generation_service.generate_video.await_args.kwargs
    assert kwargs["start_frame_base64"] == frame_base64
    assert kwargs["start_frame_mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_video_generation_service_uploads_inline_frames_before_generation():
    storage = RecordingStorage()
    service = VideoGenerationService(
        video_generate_config=SimpleNamespace(),
        llm_client=None,
        storage=storage,
    )
    fake_client = SimpleNamespace(
        generate_video=AsyncMock(
            return_value=VideoGenerationResult(url="https://videos.local/generated.mp4")
        )
    )
    service._get_client = MagicMock(return_value=fake_client)

    frame_bytes = b"png-frame-bytes"
    frame_base64 = base64.b64encode(frame_bytes).decode("utf-8")

    result = await service.generate_video(
        prompt="Generate a short clip",
        model_name="veo-3.1-generate-preview",
        duration_seconds=6,
        start_frame_base64=frame_base64,
        start_frame_mime_type="image/png",
    )

    assert result.url == "https://videos.local/generated.mp4"
    assert len(storage.writes) == 1
    assert storage.writes[0]["content"] == frame_bytes
    assert storage.writes[0]["content_type"] == "image/png"

    fake_client.generate_video.assert_awaited_once()
    kwargs = fake_client.generate_video.await_args.kwargs
    assert kwargs["start_frame"] == f"https://public.local/{storage.writes[0]['path']}"
    assert kwargs["end_frame"] is None


@pytest.mark.asyncio
async def test_video_generation_service_rejects_url_and_base64_for_same_frame():
    storage = RecordingStorage()
    service = VideoGenerationService(
        video_generate_config=SimpleNamespace(),
        llm_client=None,
        storage=storage,
    )

    frame_base64 = base64.b64encode(b"inline-frame").decode("utf-8")

    with pytest.raises(ValueError, match="start_frame accepts either a URL or base64 content"):
        await service.generate_video(
            prompt="Generate a short clip",
            model_name="veo-3.1-generate-preview",
            duration_seconds=6,
            start_frame="https://public.local/frame.png",
            start_frame_base64=frame_base64,
            start_frame_mime_type="image/png",
        )
