from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from ii_agent.core.config.settings import get_settings
from ii_agent.realtime.events.app_events import AgentToolResultEvent, EventGroup
from ii_agent.content.slides.content_processor import SlideContentProcessor
# TODO: handle_slide_tool_result was removed — slide event handling needs migration
from ii_agent.core.storage.client import get_storage
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent

def _build_storage():
    try:
        return get_storage()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Slide content processing skipped: %s", exc)
        return None


async def process_slide_content(
    *,
    agent: "IIAgent",
    tool_name: str,
    user_display_content: Any,
    url_cache: Optional[Dict[str, str]] = None,
) -> Any:
    if not get_settings().storage.custom_domain:
        return user_display_content

    sandbox = getattr(agent, "sandbox", None)
    if not sandbox:
        return user_display_content

    storage = _build_storage()
    if storage is None:
        return user_display_content

    content_processor = SlideContentProcessor(
        storage,
        sandbox,
        url_cache=url_cache or {},
    )

    try:
        if tool_name == "slide_apply_patch" and isinstance(user_display_content, list):
            for slide_data in user_display_content:
                if not isinstance(slide_data, dict):
                    continue
                html_content = slide_data.get("new_content")
                slide_file_path = slide_data.get("filepath")
                if html_content and slide_file_path:
                    processed_html = await content_processor.process_html_content(
                        html_content, slide_file_path
                    )
                    slide_data["new_content"] = processed_html
            return user_display_content

        if isinstance(user_display_content, dict) and "content" in user_display_content:
            html_content = user_display_content.get("content")
            slide_file_path = user_display_content.get("filepath")
            if html_content and slide_file_path:
                processed_html = await content_processor.process_html_content(
                    html_content, slide_file_path
                )
                user_display_content["content"] = processed_html
            return user_display_content

        if isinstance(user_display_content, list):
            for slide_data in user_display_content:
                if not isinstance(slide_data, dict):
                    continue
                if "new_content" not in slide_data:
                    continue
                html_content = slide_data.get("new_content")
                slide_file_path = slide_data.get("filepath")
                if html_content and slide_file_path:
                    processed_html = await content_processor.process_html_content(
                        html_content, slide_file_path
                    )
                    slide_data["new_content"] = processed_html
            return user_display_content

        return user_display_content
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error processing slide content for %s: %s", tool_name, exc)
        return user_display_content


async def persist_slide_tool_result(
    *,
    agent: "IIAgent",
    tool_name: str,
    tool_input: Dict[str, Any],
    user_display_content: Any,
) -> None:
    session_id = getattr(agent, "session_id", None)
    if not session_id:
        return

    import uuid as _uuid
    session_uuid = _uuid.UUID(session_id) if isinstance(session_id, str) else session_id
    event = AgentToolResultEvent(
        session_id=session_uuid,
        content={
            "tool_input": tool_input,
            "result": user_display_content,
            "user_display_content": user_display_content,
        },
    )

    # TODO: slide event handling needs migration (handle_slide_tool_result was removed)
