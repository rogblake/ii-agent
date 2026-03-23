"""
Celery tasks for ii-agent background processing.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from celery import shared_task
from sqlalchemy import select

from ii_agent.billing.types import (
    BillingContextValue,
    BillingResult,
    BillingScope,
)
from ii_agent.content.storybook.billing import finalize_storybook_async_operation
from ii_agent.workers.celery.decorators import with_task_context
from ii_agent.workers.celery.manager import get_celery_container
from ii_agent.workers.celery.utils import queue_task
from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.core.logger import logger
from ii_agent.core.redis import cancel

# Reuse a single event loop per worker process to avoid cross-loop futures.
_celery_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_celery_loop() -> asyncio.AbstractEventLoop:
    global _celery_loop
    if _celery_loop is None or _celery_loop.is_closed():
        _celery_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_celery_loop)
    return _celery_loop


def _run_async(coro: Any) -> Any:
    loop = _get_celery_loop()
    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    return loop.run_until_complete(coro)


# Default image generation cost in USD (fallback if not returned by tool)
DEFAULT_IMAGE_COST_USD = 0.02

# Match storybook generation task expiry (seconds)
STORYBOOK_TASK_EXPIRES_SECONDS = 300


def _scene_base_page_number(scene_index: int, separate_page: bool) -> int:
    """Compute the base page number for a scene (1-indexed)."""
    if scene_index == 0:
        return 1
    if separate_page:
        return scene_index * 2
    return scene_index + 1


def _db_page_to_display_page(db_page_number: int, separate_page_mode: bool) -> int:
    """Convert DB page number to display page number."""
    if db_page_number == 1:
        return 1
    if not separate_page_mode:
        return db_page_number
    return db_page_number // 2 + 1


def _resolve_storybook_language(style_json: dict[str, Any]) -> Optional[str]:
    """Resolve storybook language code from style json."""
    for key in ("language_code", "languageCode", "language", "storybook_language"):
        value = style_json.get(key)
        if value:
            return str(value)
    return None


def _get_voice_cost_usd(scene: dict[str, Any]) -> float:
    """Get voice generation cost in USD from scene metadata (if provided)."""
    for key in ("voice_cost_usd", "audio_cost_usd", "voice_cost", "audio_cost"):
        value = scene.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 0.0


def _estimate_page_credits(
    image_cost_usd: float = DEFAULT_IMAGE_COST_USD,
    audio_cost_usd: float = 0.0,
) -> float:
    """Estimate total credits needed for one storybook page."""
    total_usd = image_cost_usd + max(audio_cost_usd, 0.0)
    return float(usd_to_credits(total_usd))


async def _mark_scene_completed(
    storybook_id: str,
    scene_index: int,
    *,
    actual_cost_usd: float,
) -> bool:
    """Atomically record a completed scene and accumulate its actual billed cost."""
    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.content.storybook.models import Storybook

    async with get_db_session_local() as db_session:
        result = await db_session.execute(
            select(Storybook).where(Storybook.id == storybook_id).with_for_update()
        )
        storybook = result.scalar_one_or_none()
        if not storybook:
            return False

        style_json = dict(storybook.style_json or {})
        generation = dict(style_json.get("generation", {}))
        completed_scenes = generation.get("completed_scenes")
        if not isinstance(completed_scenes, list):
            completed_scenes = []

        if scene_index in completed_scenes:
            return False

        completed_scenes.append(scene_index)
        generation["completed_scenes"] = completed_scenes
        generation["actual_cost_usd_total"] = float(
            generation.get("actual_cost_usd_total") or 0.0
        ) + max(actual_cost_usd, 0.0)
        generation["completed_pages"] = max(
            int(generation.get("completed_pages") or 0), len(completed_scenes)
        )
        generation["updated_at"] = datetime.now(timezone.utc).isoformat()
        style_json["generation"] = generation
        storybook.style_json = style_json
        storybook.updated_at = datetime.now(timezone.utc)
        await db_session.flush()
        return True


async def _finalize_storybook_billing(
    storybook_id: str,
    *,
    terminal_status: str,
) -> None:
    """Settle or release the reserved storybook billing hold exactly once."""
    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.content.storybook.repository import StorybookRepository
    from ii_agent.billing.reservations.repository import CreditReservationRepository

    container = get_celery_container()
    repo = StorybookRepository()
    reservation_repo = CreditReservationRepository()

    try:
        async with get_db_session_local() as db_session:
            storybook = await repo.get_by_id(db_session, storybook_id)
            if not storybook:
                return

            style_json = storybook.style_json or {}
            if not isinstance(style_json, dict):
                style_json = {}
            generation = style_json.get("generation")
            if not isinstance(generation, dict):
                generation = {}

            reservation_id = generation.get("reservation_id")
            if not reservation_id:
                return

            reservation = await reservation_repo.get_by_id(db_session, reservation_id)
            if reservation is None:
                logger.warning(
                    "Storybook %s references missing billing reservation %s",
                    storybook_id,
                    reservation_id,
                )
                return

            tool_name = generation.get("tool_name", "generate_storybook")
            actual_cost_usd = float(generation.get("actual_cost_usd_total") or 0.0)
            if reservation.subject_kind != "session" or not reservation.subject_id:
                await container.credit_reservation_service.mark_settlement_failed(
                    db_session,
                    reservation_id=reservation_id,
                    error="storybook_invalid_subject",
                )
                await db_session.commit()
                return

            scope = BillingScope.for_session(
                user_id=str(reservation.user_id),
                app_kind=str(generation.get("app_kind") or "chat"),
                session_id=str(reservation.subject_id),
                billing_context=BillingContextValue.STORYBOOK,
                run_id=reservation.run_id,
            )

            if actual_cost_usd > 0:
                await finalize_storybook_async_operation(
                    reservation_service=container.credit_reservation_service,
                    scope=scope,
                    reservation_id=reservation_id,
                    result=BillingResult(
                        value=None,
                        actual_usd=actual_cost_usd,
                        usage_payload={
                            "provider": None,
                            "latency_ms": None,
                            "cost_usd": actual_cost_usd,
                            "tool_name": tool_name,
                            "run_id": str(reservation.run_id) if reservation.run_id else None,
                        },
                    ),
                    release_reason="unused",
                    settlement_error="storybook_settle_exception",
                )
            else:
                await finalize_storybook_async_operation(
                    reservation_service=container.credit_reservation_service,
                    scope=scope,
                    reservation_id=reservation_id,
                    result=None,
                    release_reason=(
                        "storybook_cancelled"
                        if terminal_status == "cancelled"
                        else ("unused" if terminal_status == "completed" else "storybook_failed")
                    ),
                )
    except Exception:
        logger.opt(exception=True).error(
            "Failed to finalize storybook billing for {}", storybook_id
        )


async def _create_storybook_tool_result(
    *,
    storybook_id: str,
    tool_call_id: Optional[str],
    session_id: str,
    parent_message_id: Optional[str],
    model_id: Optional[str],
    tool_name: str,
) -> None:
    """Persist a final tool_result message for storybook generation."""
    if not tool_call_id or not model_id:
        return

    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.chat.messages.service import MessageService
    from ii_agent.chat.types import (
        MessageRole,
        StorybookPageResult,
        StorybookResultContent,
        ToolResult,
    )

    container = get_celery_container()

    async with get_db_session_local() as db_session:
        storybook = await container.storybook_service.get_storybook_detail(
            db_session, storybook_id=storybook_id, include_pages=True
        )
        if not storybook:
            return

    style_json = storybook.style_json or {}
    separate_page_mode = (
        style_json.get("user_text_position") == "separate_page"
        if isinstance(style_json, dict)
        else False
    )

    page_results: list[StorybookPageResult] = []
    for page in sorted(storybook.pages or [], key=lambda p: p.page_number):
        if not page.image_url:
            continue
        display_page = _db_page_to_display_page(page.page_number, separate_page_mode)
        metadata = page.metadata or {}
        page_results.append(
            StorybookPageResult(
                page_number=display_page,
                image_url=page.image_url or "",
                text_content=page.text_content,
                audio_link=page.audio_link,
                text_position=str(metadata.get("text_position", "none")),
                text_percentage=int(metadata.get("text_percentage", 30) or 30),
            )
        )

    output = StorybookResultContent(
        storybook_id=storybook.id,
        storybook_name=storybook.name,
        version=storybook.version,
        pages=page_results,
        aspect_ratio=storybook.aspect_ratio,
        resolution=storybook.resolution,
    )

    tool_result = ToolResult(
        tool_call_id=tool_call_id,
        name=tool_name,
        output=output,
    )

    parent_uuid = uuid.UUID(parent_message_id) if parent_message_id else None
    async with get_db_session_local() as db_session:
        await MessageService().create_message(
            db_session,
            session_id=session_id,
            role=MessageRole.TOOL,
            parts=[tool_result],
            parent_message_id=parent_uuid,
            model_id=model_id,
        )


async def _create_storybook_tool_error(
    *,
    error_message: str,
    tool_call_id: Optional[str],
    session_id: str,
    parent_message_id: Optional[str],
    model_id: Optional[str],
    tool_name: str,
) -> None:
    """Persist a failure tool_result message for storybook generation."""
    if not tool_call_id or not model_id:
        return

    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.chat.messages.service import MessageService
    from ii_agent.chat.types import ErrorTextContent, MessageRole, ToolResult

    tool_result = ToolResult(
        tool_call_id=tool_call_id,
        name=tool_name,
        output=ErrorTextContent(value=error_message),
    )

    parent_uuid = uuid.UUID(parent_message_id) if parent_message_id else None
    async with get_db_session_local() as db_session:
        await MessageService().create_message(
            db_session,
            session_id=session_id,
            role=MessageRole.TOOL,
            parts=[tool_result],
            parent_message_id=parent_uuid,
            model_id=model_id,
        )


async def _fail_storybook(
    storybook_id: str,
    error_msg: str,
    payload: dict[str, Any],
) -> None:
    """Mark a storybook as failed and send an error tool result message."""
    from ii_agent.core.db.manager import get_db_session_local

    container = get_celery_container()
    async with get_db_session_local() as db_session:
        await container.storybook_service.update_generation_status(
            db_session,
            storybook_id,
            status="failed",
            generating_pages=[],
            error_message=error_msg,
        )

    session_id = payload.get("session_id")
    if session_id:
        try:
            await _create_storybook_tool_error(
                error_message=error_msg,
                tool_call_id=payload.get("tool_call_id"),
                session_id=session_id,
                parent_message_id=payload.get("parent_message_id"),
                model_id=payload.get("model_id"),
                tool_name=payload.get("tool_name", "generate_storybook"),
            )
        except Exception:
            logger.opt(exception=True).error(
                "Failed to create storybook error tool result for {}", storybook_id
            )

    await _finalize_storybook_billing(storybook_id, terminal_status="failed")


def _setup_storybook_tool(payload: dict[str, Any], session_id: str):
    """Create and configure a StorybookGenerationTool (or MangaGenerationTool) from payload settings."""
    container = get_celery_container()
    manga_layout = bool(payload.get("manga_layout", False))

    if manga_layout:
        from ii_agent.chat.tools.manga_generate import MangaGenerationTool

        tool = MangaGenerationTool(session_id=session_id, container=container)
    else:
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(session_id=session_id, container=container)

    tool.image_model_name = payload.get("image_model_name")
    tool.image_provider = payload.get("image_provider") or tool.image_provider
    tool.aspect_ratio = payload.get("aspect_ratio") or tool.aspect_ratio
    tool.resolution = payload.get("resolution") or tool.resolution
    tool.user_text_position = payload.get("user_text_position")
    tool.voice_enabled = bool(payload.get("voice_enabled", False))
    tool.storybook_language = payload.get("storybook_language")
    return tool


async def _generate_storybook_page_async(
    payload: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    """Generate a single storybook page (scene) and enqueue the next one."""
    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.content.storybook.repository import StorybookRepository

    storybook_id = payload.get("storybook_id")
    scene_index_value = payload.get("scene_index")
    if not storybook_id or scene_index_value is None:
        return {"status": "invalid_payload"}

    try:
        scene_index = int(scene_index_value)
    except (TypeError, ValueError):
        return {"status": "invalid_payload"}

    if scene_index < 0:
        return {"status": "invalid_payload"}

    repo = StorybookRepository()
    async with get_db_session_local() as db_session:
        storybook = await repo.get_by_id(db_session, storybook_id)
    if not storybook:
        return {"status": "storybook_not_found"}

    style_json = storybook.style_json or {}
    if not isinstance(style_json, dict):
        style_json = {}

    generation = style_json.get("generation")
    if not isinstance(generation, dict):
        generation = {}

    if generation.get("status") == "failed":
        return {"status": "failed"}

    if await cancel.is_cancelled(storybook_id):
        logger.info("Storybook {} cancelled before scene {}", storybook_id, scene_index)
        await _finalize_storybook_billing(storybook_id, terminal_status="cancelled")
        return {"status": "cancelled"}

    scenes = generation.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        await _fail_storybook(
            storybook_id,
            "No scenes found for storybook generation.",
            {
                "session_id": storybook.session_id,
                "tool_call_id": generation.get("tool_call_id"),
                "parent_message_id": generation.get("parent_message_id"),
                "model_id": generation.get("model_id"),
                "tool_name": generation.get("tool_name", "generate_storybook"),
            },
        )
        return {"status": "failed", "error": "scenes_missing"}

    total_scenes = len(scenes)
    if scene_index >= total_scenes:
        return {"status": "out_of_range", "completed_pages": generation.get("completed_pages", 0)}

    session_id = storybook.session_id
    failure_payload = {
        "session_id": session_id,
        "tool_call_id": generation.get("tool_call_id"),
        "parent_message_id": generation.get("parent_message_id"),
        "model_id": generation.get("model_id"),
        "tool_name": generation.get("tool_name", "generate_storybook"),
    }

    if not session_id:
        await _fail_storybook(
            storybook_id,
            "Session not found for storybook generation.",
            failure_payload,
        )
        return {"status": "failed", "error": "session_not_found"}

    container = get_celery_container()
    async with get_db_session_local() as db_session:
        session = await container.session_service.get_session_by_id(
            db_session, uuid.UUID(session_id)
        )
        if not session:
            await _fail_storybook(
                storybook_id,
                "Session not found for storybook generation.",
                failure_payload,
            )
            return {"status": "failed", "error": "session_not_found"}

        user_api_key = await container.user_service.get_active_api_key(db_session, session.user_id)
        if not user_api_key:
            await _fail_storybook(
                storybook_id,
                "No active API key found for user.",
                failure_payload,
            )
            return {"status": "failed", "error": "api_key_missing"}

    voice_enabled = bool(style_json.get("voice_enabled", False))

    tool = _setup_storybook_tool(
        {
            "image_model_name": style_json.get("image_model_name"),
            "image_provider": style_json.get("image_provider"),
            "aspect_ratio": storybook.aspect_ratio,
            "resolution": storybook.resolution,
            "user_text_position": style_json.get("user_text_position"),
            "voice_enabled": voice_enabled,
            "storybook_language": _resolve_storybook_language(style_json),
            "manga_layout": bool(style_json.get("manga_layout", False)),
        },
        session_id,
    )

    style_context = tool._build_style_context(style_json)
    separate_page_mode = tool.user_text_position == "separate_page"

    display_page = scene_index + 1
    async with get_db_session_local() as db_session:
        await container.storybook_service.update_generation_status(
            db_session,
            storybook_id,
            status="generating",
            total_pages=total_scenes,
            generating_pages=[display_page],
            generation_meta={
                "active_task_id": task_id,
            },
        )

    base_page_number = _scene_base_page_number(scene_index, separate_page_mode)
    async with get_db_session_local() as db_session:
        existing_page = await repo.get_page_by_number(db_session, storybook_id, base_page_number)

    image_url: Optional[str] = None
    voice_cost_usd: float = 0.0

    if existing_page and existing_page.image_url:
        image_url = existing_page.image_url
        logger.info(
            "Storybook {} scene {} already has an image, skipping generation",
            storybook_id,
            scene_index + 1,
        )
    else:
        reference_image_url: Optional[str] = None
        if scene_index > 0:
            prev_base_page = _scene_base_page_number(scene_index - 1, separate_page_mode)
            async with get_db_session_local() as db_session:
                prev_page = await repo.get_page_by_number(db_session, storybook_id, prev_base_page)
            if prev_page and prev_page.image_url:
                reference_image_url = prev_page.image_url

        scene = scenes[scene_index]

        try:
            scene_pages, image_url, voice_cost_usd = await tool._process_single_scene(
                scene_index=scene_index,
                scene=scene,
                storybook_id=storybook_id,
                user_api_key=user_api_key,
                style_context=style_context,
                storybook_title=storybook.name,
                cover_image_url=reference_image_url,
                page_number=base_page_number,
            )
        except Exception as exc:
            logger.opt(exception=True).error(
                "Storybook page {} (scene {}) failed: {}", display_page, scene_index + 1, exc
            )
            await _fail_storybook(storybook_id, str(exc), failure_payload)
            return {"status": "failed", "error": str(exc)}

        if not scene_pages:
            error_msg = f"Page {display_page} generation returned no pages"
            logger.error(error_msg)
            await _fail_storybook(storybook_id, error_msg, failure_payload)
            return {"status": "failed", "error": error_msg}

    actual_image_cost = DEFAULT_IMAGE_COST_USD
    actual_audio_cost = voice_cost_usd if voice_enabled else 0.0
    await _mark_scene_completed(
        storybook_id,
        scene_index,
        actual_cost_usd=actual_image_cost + actual_audio_cost,
    )

    async with get_db_session_local() as db_session:
        await container.storybook_service.update_generation_status(
            db_session,
            storybook_id,
            generating_pages=[],
        )

    if scene_index >= total_scenes - 1:
        async with get_db_session_local() as db_session:
            await container.storybook_service.update_generation_status(
                db_session,
                storybook_id,
                status="completed",
                generating_pages=[],
            )

        await _finalize_storybook_billing(storybook_id, terminal_status="completed")

        if session_id:
            try:
                await _create_storybook_tool_result(
                    storybook_id=storybook_id,
                    tool_call_id=generation.get("tool_call_id"),
                    session_id=session_id,
                    parent_message_id=generation.get("parent_message_id"),
                    model_id=generation.get("model_id"),
                    tool_name=generation.get("tool_name", "generate_storybook"),
                )
            except Exception:
                logger.opt(exception=True).error(
                    "Failed to create storybook tool result for {}", storybook_id
                )

        return {"status": "completed", "completed_pages": total_scenes}

    if await cancel.is_cancelled(storybook_id):
        logger.info(
            "Storybook {} cancelled after scene {}, not queuing next page",
            storybook_id,
            scene_index,
        )
        await _finalize_storybook_billing(storybook_id, terminal_status="cancelled")
        return {"status": "cancelled", "completed_pages": scene_index + 1}

    next_scene_index = scene_index + 1
    next_task_id = queue_task(
        "ii_agent.workers.celery.tasks.storybook_generate_page",
        {
            "storybook_id": storybook_id,
            "scene_index": next_scene_index,
        },
        expires=STORYBOOK_TASK_EXPIRES_SECONDS,
        headers={
            "session_id": session_id,
            "user_id": session.user_id,
        },
    )

    async with get_db_session_local() as db_session:
        await container.storybook_service.update_generation_status(
            db_session,
            storybook_id,
            generation_meta={
                "active_task_id": next_task_id,
            },
        )

    return {"status": "queued", "next_scene_index": next_scene_index}


async def _handle_storybook_page_failure(payload: dict[str, Any], error_message: str) -> None:
    """Best-effort failure handler for per-page storybook tasks."""
    from ii_agent.core.db.manager import get_db_session_local
    from ii_agent.content.storybook.repository import StorybookRepository

    storybook_id = payload.get("storybook_id", "")
    if not storybook_id:
        return

    repo = StorybookRepository()
    async with get_db_session_local() as db_session:
        storybook = await repo.get_by_id(db_session, storybook_id)
    if not storybook:
        return

    style_json = storybook.style_json or {}
    if not isinstance(style_json, dict):
        style_json = {}
    generation = style_json.get("generation")
    if not isinstance(generation, dict):
        generation = {}

    await _fail_storybook(
        storybook_id,
        error_message,
        {
            "session_id": storybook.session_id,
            "tool_call_id": generation.get("tool_call_id"),
            "parent_message_id": generation.get("parent_message_id"),
            "model_id": generation.get("model_id"),
            "tool_name": generation.get("tool_name", "generate_storybook"),
        },
    )


@shared_task(bind=True, name="ii_agent.workers.celery.tasks.storybook_generate_page")
@with_task_context
def storybook_generate_page(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Celery task to generate a single storybook page."""
    try:
        return _run_async(_generate_storybook_page_async(payload, self.request.id))
    except Exception as exc:
        logger.opt(exception=True).error("Storybook page task failed: {}", exc)
        try:
            _run_async(_handle_storybook_page_failure(payload, str(exc)))
        except Exception:
            logger.opt(exception=True).error(
                "Failed to update storybook generation after page task error"
            )
        return {"status": "failed", "error": str(exc)}
