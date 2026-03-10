from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.content.slides.content_processor import SlideContentProcessor
from ii_agent.core.storage.factory import create_storage_client
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.engine.runtime.agents.agent import IIAgent

def _build_storage():
    settings = get_settings()
    project_id = settings.storage.slide_assets_project_id or settings.storage.file_upload_project_id
    bucket_name = settings.storage.slide_assets_bucket_name or settings.storage.file_upload_bucket_name
    if not project_id or not bucket_name:
        logger.warning("Slide content processing skipped: storage config missing")
        return None

    try:
        return create_storage_client(
            settings.storage.provider,
            project_id,
            bucket_name,
            settings.storage.custom_domain,
        )
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

    sandbox_manager = getattr(agent, "sandbox", None)
    if not sandbox_manager:
        logger.warning("Slide content processing skipped: sandbox_manager not found")
        return user_display_content

    storage = _build_storage()
    if storage is None:
        return user_display_content

    content_processor = SlideContentProcessor(
        storage,
        sandbox_manager,
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
    from ii_agent.content.slides.service import _save_slide_to_db

    session_id = getattr(agent, "session_id", None)
    if not session_id:
        return

    try:
        if tool_name == "slide_apply_patch":
            await _persist_slide_apply_patch(
                session_id=str(session_id),
                user_display_content=user_display_content,
            )
            return

        presentation_name = tool_input.get("presentation_name")
        slide_number = tool_input.get("slide_number")
        if not presentation_name or not slide_number:
            return

        slide_content = None
        slide_title = tool_input.get("title", "")

        if isinstance(user_display_content, dict):
            if tool_name == "SlideEdit":
                slide_content = user_display_content.get("new_content", "")
            else:
                slide_content = user_display_content.get("content", "")

        if not slide_content:
            return

        async with get_db_session_local() as db_session:
            await _save_slide_to_db(
                db_session=db_session,
                session_id=str(session_id),
                presentation_name=presentation_name,
                slide_number=slide_number,
                slide_title=slide_title,
                slide_content=slide_content,
                tool_name=tool_name,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to persist slide tool result for %s: %s", tool_name, exc)


async def _persist_slide_apply_patch(
    *,
    session_id: str,
    user_display_content: Any,
) -> None:
    from ii_agent.content.slides.service import _save_slide_to_db

    if not isinstance(user_display_content, list):
        return

    for slide_data in user_display_content:
        if not isinstance(slide_data, dict):
            continue

        filepath = slide_data.get("filepath", "")
        if not filepath.startswith("/workspace/"):
            continue

        path_parts = filepath.replace("/workspace/presentations/", "").split("/")
        if len(path_parts) < 2:
            continue

        presentation_name = path_parts[0]
        slide_filename = path_parts[1]

        if not slide_filename.startswith("slide_") or not slide_filename.endswith(
            ".html"
        ):
            continue

        try:
            slide_number = int(
                slide_filename.replace("slide_", "").replace(".html", "")
            )
        except ValueError:
            continue

        slide_content = slide_data.get("new_content", "")
        if not slide_content:
            continue

        async with get_db_session_local() as db_session:
            await _save_slide_to_db(
                db_session=db_session,
                session_id=session_id,
                presentation_name=presentation_name,
                slide_number=slide_number,
                slide_title="",
                slide_content=slide_content,
                tool_name="slide_apply_patch",
            )
