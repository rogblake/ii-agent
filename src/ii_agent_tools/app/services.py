"""Backward-compatible exports for dependency factories."""

from ii_agent_tools.app.deps import (
    get_audio_generation_service,
    get_image_generation_service,
    get_image_search_service,
    get_llm_client,
    get_storage,
    get_video_generation_service,
    get_voice_generation_service,
    get_web_search_service,
    get_web_visit_service,
)

__all__ = [
    "get_image_search_service",
    "get_audio_generation_service",
    "get_web_visit_service",
    "get_video_generation_service",
    "get_voice_generation_service",
    "get_web_search_service",
    "get_image_generation_service",
    "get_storage",
    "get_llm_client",
]
