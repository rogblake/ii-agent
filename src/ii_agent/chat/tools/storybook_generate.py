"""Storybook generation tool for chat mode."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from io import BytesIO
from typing import Any, Literal, Optional, TYPE_CHECKING, cast

import anyio
import httpx

from ii_agent.workers.celery.utils import queue_task
from ii_agent.core.db.manager import get_db_session_local

from ii_agent.content.media.service import _generate_image
from ii_agent.chat.types import (
    ErrorTextContent,
    MediaPreferences,
    StorybookProgressContent,
    StorybookPageResult,
)
from ii_agent.core.storage.client import media_storage
from ii_agent.content.storybook.html_generator import (
    generate_storybook_page_html,
    generate_text_only_page_html,
)

from ii_agent.billing.reservations.types import BillingQuote
from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_RESOLUTION = "1K"
DEFAULT_TEXT_POSITION = "right"
DEFAULT_TEXT_PERCENTAGE = 30
STORYBOOK_TASK_EXPIRES_SECONDS = 300
MAX_CONTENT_SCENES = 50
# Per-page image generation cost used for upfront reservation
_STORYBOOK_PER_PAGE_COST_USD = 0.05
MAX_RETRIES = 3

TextPositionLiteral = Literal[
    "left",
    "right",
    "top",
    "bottom",
    "none",
    "separate_page",
]
ALLOWED_TEXT_POSITIONS: set[str] = {
    "left",
    "right",
    "top",
    "bottom",
    "none",
    "separate_page",
}

# Aspect ratio constants
AR_1_1 = 1.0
AR_4_3 = 1.333
AR_3_4 = 0.75
AR_3_2 = 1.5
AR_2_3 = 0.666
AR_16_9 = 1.777
AR_9_16 = 0.562
AR_21_9 = 2.333

# Supported aspect ratios per provider
SUPPORTED_ASPECT_RATIOS_BY_PROVIDER = {
    "openai": {
        "1:1": AR_1_1,
        "2:3": AR_2_3,
        "3:2": AR_3_2,
    },
    "gemini": {
        "1:1": AR_1_1,
        "2:3": AR_2_3,
        "3:2": AR_3_2,
        "16:9": AR_16_9,
        "9:16": AR_9_16,
        "4:3": AR_4_3,
        "3:4": AR_3_4,
        "21:9": AR_21_9,
    },
    "vertex": {  # Alias for gemini in some contexts
        "1:1": AR_1_1,
        "2:3": AR_2_3,
        "3:2": AR_3_2,
        "16:9": AR_16_9,
        "9:16": AR_9_16,
        "4:3": AR_4_3,
        "3:4": AR_3_4,
        "21:9": AR_21_9,
    },
}
# Default to wide support if provider unknown
DEFAULT_SUPPORTED_RATIOS = SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["gemini"]


class StorybookGenerationTool(BaseTool):
    """Generate illustrated storybooks with multiple scenes."""

    supports_streaming: bool = True

    def __init__(
        self,
        session_id: str,
        *,
        container: ServiceContainer,
        media_preferences: Optional[MediaPreferences] = None,
    ):
        self._container = container
        self.session_id = session_id
        self.media_preferences = media_preferences
        self._name = "generate_storybook"

        # Extract preferences with defaults
        if media_preferences:
            self.image_model_name = media_preferences.model_name
            self.image_provider = media_preferences.provider or "gemini"
            self.aspect_ratio = media_preferences.aspect_ratio or DEFAULT_ASPECT_RATIO
            self.resolution = media_preferences.resolution or DEFAULT_RESOLUTION
            self.page_count = getattr(media_preferences, "page_count", None)
            self.user_text_position = getattr(media_preferences, "text_position", None)
            self.voice_enabled = bool(getattr(media_preferences, "voice_enabled", False))
            self.storybook_language = getattr(media_preferences, "language", None)
            self.manga_layout = False
        else:
            self.image_model_name = None
            self.image_provider = "gemini"
            self.aspect_ratio = DEFAULT_ASPECT_RATIO
            self.resolution = DEFAULT_RESOLUTION
            self.page_count = None
            self.user_text_position = None
            self.voice_enabled = False
            self.storybook_language = None
            self.manga_layout = False

        self._voice_service = None

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        description = (
            "Generates an illustrated storybook with multiple scenes. "
            "Each scene combines an AI-generated image with narrative text in a specified layout. "
            "Use this when the user wants to create a story, children's book, or narrative sequence."
        )

        return ToolInfo(
            name="generate_storybook",
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A descriptive title for the storybook (e.g., 'The Adventures of Luna the Brave Cat', 'A Journey Through the Enchanted Forest')",
                    },
                    "scenes": {
                        "type": "array",
                        "description": "Array of story scenes, each with image and text",
                        "items": {
                            "type": "object",
                            "properties": {
                                "image_prompt": {
                                    "type": "string",
                                    "description": "Detailed description for AI image generation",
                                },
                                "text_content": {
                                    "type": "string",
                                    "description": "Narrative text (1-3 sentences)",
                                },
                                "text_position": {
                                    "type": "string",
                                    "enum": [
                                        "left",
                                        "right",
                                        "top",
                                        "bottom",
                                        "none",
                                        "separate_page",
                                    ],
                                    "description": "Position of text relative to image; use 'none' to omit text",
                                },
                                "text_percentage": {
                                    "type": "integer",
                                    "description": "Percentage of space for text (20-30)",
                                    "minimum": 20,
                                    "maximum": 30,
                                },
                            },
                            "required": [
                                "image_prompt",
                                "text_content",
                                "text_position",
                                "text_percentage",
                            ],
                        },
                    },
                    "style": {
                        "type": "object",
                        "description": "Optional style parameters for consistency across scenes",
                        "properties": {
                            "character_description": {
                                "type": "string",
                                "description": "Physical description of main character(s)",
                            },
                            "art_style": {
                                "type": "string",
                                "description": "Art style (e.g., watercolor, cartoon, realistic)",
                            },
                            "color_palette": {
                                "type": "string",
                                "description": "Color palette (e.g., warm, cool, monochrome)",
                            },
                        },
                    },
                },
            },
            required=["title", "scenes"],
        )

    def _get_content_scene_cap(self) -> int:
        """Return the maximum allowed content scenes based on preferences."""
        requested_content = None
        if self.page_count and self.page_count != "unlimited":
            try:
                requested_content = int(self.page_count)
            except (TypeError, ValueError):
                requested_content = None

        if requested_content is None:
            return MAX_CONTENT_SCENES

        return max(0, min(requested_content, MAX_CONTENT_SCENES))

    def _apply_scene_cap(self, scenes: list[dict]) -> tuple[list[dict], bool, int]:
        """Cap scenes to the allowed max. Returns (scenes, capped, max_content_scenes)."""
        max_content_scenes = self._get_content_scene_cap()
        max_total_scenes = max_content_scenes + 1  # +1 cover page

        if len(scenes) > max_total_scenes:
            return scenes[:max_total_scenes], True, max_content_scenes

        return scenes, False, max_content_scenes

    def _validate_page_count(self, num_scenes: int) -> None:
        """Validate page_count against number of scenes provided by LLM."""
        if self.page_count is None:
            return

        expected_content_scenes = self._get_content_scene_cap()
        expected_total_scenes = expected_content_scenes + 1  # +1 for cover page
        if num_scenes != expected_total_scenes:
            logger.warning(
                f"[STORYBOOK] Expected {expected_total_scenes} total scenes "
                f"(up to {expected_content_scenes} content pages + 1 cover page), "
                f"but received {num_scenes} scenes from LLM"
            )
        elif self.page_count == "unlimited":
            logger.info(f"[STORYBOOK] Unlimited mode: LLM generated {num_scenes} scenes")

    def _get_voice_service(self):
        if self._voice_service is not None:
            return self._voice_service

        try:
            from ii_agent_tools.client.tool_client_config import ToolClientSettings
            from ii_agent_tools.integrations.voice_generation.service import (
                VoiceGenerationService,
            )
        except Exception as exc:
            logger.warning("[STORYBOOK] Voice generation imports unavailable: %s", exc)
            self._voice_service = None
            return None

        try:
            tool_settings = ToolClientSettings()
            self._voice_service = VoiceGenerationService(tool_settings.voice_generate_config)
        except Exception as exc:
            logger.warning("[STORYBOOK] Failed to initialize voice generation: %s", exc)
            self._voice_service = None
        return self._voice_service

    async def _generate_voice_audio(self, text: str) -> tuple[Optional[str], float]:
        """Generate voice audio for text.

        Returns:
            Tuple of (audio_url, cost_usd). Returns (None, 0.0) if generation fails.
        """
        if not self.voice_enabled:
            return None, 0.0

        if not text or not text.strip():
            return None, 0.0

        voice_service = self._get_voice_service()
        if not voice_service:
            return None, 0.0

        try:
            voice_kwargs: dict[str, Any] = {
                "text": text.strip(),
                "session_id": self.session_id,
            }
            if self.storybook_language:
                voice_kwargs["language_code"] = self.storybook_language
            result = await voice_service.generate_voice(**voice_kwargs)
            return result.url, getattr(result, "cost", 0.0) or 0.0
        except Exception as exc:
            logger.warning("[STORYBOOK] Voice generation failed: %s", exc)
            return None, 0.0

    async def _process_single_scene(
        self,
        *,
        scene_index: int,
        scene: dict,
        storybook_id: str,
        user_api_key: str,
        style_context: str,
        storybook_title: Optional[str] = None,
        cover_image_url: Optional[str] = None,
        page_number: Optional[int] = None,
    ) -> tuple[list[StorybookPageResult], Optional[str], float]:
        """
        Process a single scene: validate, generate image, create page record(s).

        For "separate_page" mode, this generates two pages: an image-only page
        followed by a text-only page.
        """
        base_page_num = page_number if page_number is not None else scene_index + 1
        is_cover_page = scene_index == 0

        image_prompt = scene.get("image_prompt", "")
        text_content = scene.get("text_content", "")
        if is_cover_page and (not text_content or not text_content.strip()):
            if storybook_title:
                text_content = storybook_title.strip()

        if not image_prompt:
            raise ValueError(f"Scene {scene_index + 1} missing image_prompt")

        text_position = self._resolve_text_position(
            is_cover_page=is_cover_page,
            scene_text_position=scene.get("text_position"),
        )
        text_position_literal = cast(TextPositionLiteral, text_position)

        is_separate_page_mode = text_position_literal == "separate_page" and not is_cover_page

        if is_separate_page_mode:
            image_text_position: TextPositionLiteral = "none"
            image_text_percentage = 0
            image_text_content = ""
            effective_text_content = text_content.strip()
            if not effective_text_content:
                raise ValueError(
                    f"Scene {scene_index + 1} missing text_content for separate_page layout"
                )
        else:
            image_text_position = text_position_literal
            effective_text_content = text_content.strip()
            has_text = text_position_literal != "none" and bool(effective_text_content)
            image_text_percentage = (
                scene.get("text_percentage", DEFAULT_TEXT_PERCENTAGE) if has_text else 0
            )
            image_text_content = effective_text_content if has_text else ""

            if text_position_literal != "none" and not effective_text_content:
                raise ValueError(f"Scene {scene_index + 1} missing text_content for text layout")

        reference_image_urls = None
        reference_type = None

        if not is_cover_page and cover_image_url:
            reference_image_urls = [cover_image_url]
            reference_type = "style_only"
            logger.info(f"[STORYBOOK] Scene {scene_index + 1}: Using cover as style reference")
        elif not is_cover_page and not cover_image_url:
            logger.warning(
                f"[STORYBOOK] Scene {scene_index + 1}: Cover failed, generating without reference"
            )

        # Explicitly control text inclusion for non-cover pages in the base prompt
        if not is_cover_page:
            image_prompt = self._augment_non_cover_prompt(image_prompt, effective_text_content)

        if is_separate_page_mode:
            gen_aspect_ratio = self.aspect_ratio
        else:
            gen_aspect_ratio = self._get_optimal_aspect_ratio(
                self.aspect_ratio,
                image_text_position,
                image_text_percentage,
            )

        safe_w, safe_h = 100, 100
        if not is_separate_page_mode:
            safe_w, safe_h = self._calculate_safe_zones(
                self.aspect_ratio,
                gen_aspect_ratio,
                image_text_position,
                image_text_percentage,
            )

        composition_rule = None
        if (
            not is_separate_page_mode
            and image_text_position != "none"
            and image_text_percentage > 0
        ):
            composition_rule = (
                f"CRITICAL LAYOUT INSTRUCTION: The final image will be displayed in a container where "
                f"only the CENTER {safe_w}% WIDTH and CENTER {safe_h}% HEIGHT is visible. "
                f"You MUST keep all main subjects, faces, and critical details strictly inside this central safe zone. "
                f"Everything outside this central area will be cropped off. "
                f"Do NOT place any text or important elements near the edges. "
                f"Fill the outer margins with background scenery only."
            )

        enhanced_prompt = self._enhance_prompt_with_style(
            image_prompt,
            style_context,
            is_cover_page=is_cover_page,
            reference_type=reference_type,
            composition_rule=composition_rule,
        )

        image_url = await self._generate_scene_image(
            prompt=enhanced_prompt,
            user_api_key=user_api_key,
            scene_number=scene_index + 1,
            reference_image_urls=reference_image_urls,
            aspect_ratio=gen_aspect_ratio,
        )

        image_audio_link: Optional[str] = None
        text_audio_link: Optional[str] = None
        voice_cost_usd: float = 0.0
        if self.voice_enabled:
            if is_separate_page_mode:
                text_audio_link, voice_cost_usd = await self._generate_voice_audio(
                    effective_text_content
                )
            else:
                image_audio_link, voice_cost_usd = await self._generate_voice_audio(
                    effective_text_content
                )

        page_results: list[StorybookPageResult] = []

        image_html_content = generate_storybook_page_html(
            image_url=image_url,
            text_content=image_text_content,
            text_position=image_text_position,
            text_percentage=image_text_percentage,
            aspect_ratio=self.aspect_ratio,
            resolution=self.resolution,
            page_number=base_page_num,
        )

        async with get_db_session_local() as db:
            await self._container.storybook_service.create_storybook_page(
                db,
                storybook_id=storybook_id,
                page_number=base_page_num,
                image_url=image_url,
                image_prompt=image_prompt,
                text_content=effective_text_content,
                text_position=image_text_position,
                text_percentage=image_text_percentage,
                html_content=image_html_content,
                audio_link=image_audio_link,
                metadata={
                    "enhanced_prompt": enhanced_prompt,
                    "gen_aspect_ratio": gen_aspect_ratio,
                    "is_cover_page": is_cover_page,
                    "is_separate_page_image": is_separate_page_mode,
                },
            )

        image_page_result = StorybookPageResult(
            page_number=base_page_num,
            image_url=image_url,
            text_content=effective_text_content,
            audio_link=image_audio_link,
            text_position=image_text_position,
            text_percentage=image_text_percentage,
        )
        page_results.append(image_page_result)

        logger.info(f"[STORYBOOK] Scene {scene_index + 1} image page completed: {image_url}")

        if is_separate_page_mode:
            text_page_num = base_page_num + 1

            text_html_content = generate_text_only_page_html(
                text_content=effective_text_content,
                aspect_ratio=self.aspect_ratio,
                resolution=self.resolution,
                page_number=text_page_num,
            )

            async with get_db_session_local() as db:
                await self._container.storybook_service.create_storybook_page(
                    db,
                    storybook_id=storybook_id,
                    page_number=text_page_num,
                    image_url="",
                    image_prompt=None,
                    text_content=effective_text_content,
                    text_position="separate_page",
                    text_percentage=100,
                    html_content=text_html_content,
                    audio_link=text_audio_link,
                    metadata={
                        "is_text_only_page": True,
                        "linked_image_page": base_page_num,
                    },
                )

            text_page_result = StorybookPageResult(
                page_number=text_page_num,
                image_url="",
                text_content=effective_text_content,
                audio_link=text_audio_link,
                text_position="separate_page",
                text_percentage=100,
            )
            page_results.append(text_page_result)

            logger.info(
                f"[STORYBOOK] Scene {scene_index + 1} text page completed (page {text_page_num})"
            )

        return (page_results, image_url, voice_cost_usd)

    async def quote_cost(self, tool_call: ToolCallInput) -> BillingQuote | None:
        """Bounded quote based on scene count × per-page image cost."""
        try:
            params = json.loads(tool_call.input)
            scenes = params.get("scenes", [])
            page_count = max(len(scenes), 1)
            page_count = min(page_count, MAX_CONTENT_SCENES)
        except (json.JSONDecodeError, KeyError):
            page_count = 5  # safe default
        reserve_usd = page_count * _STORYBOOK_PER_PAGE_COST_USD
        return BillingQuote(
            strategy="bounded",
            reserve_usd=reserve_usd,
            max_usd=reserve_usd,
            metadata={"tool_name": self.name, "page_count": page_count},
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        return ToolResponse(
            output=ErrorTextContent(
                value="Storybook generation runs via Celery background workers. "
                "Direct execution is disabled to avoid blocking."
            )
        )

    async def start_celery_generation(
        self,
        tool_call: ToolCallInput,
        *,
        parent_message_id: uuid.UUID,
        model_id: str,
        run_id: str | None = None,
        reservation_id: str | None = None,
    ) -> ToolResponse:
        """Start storybook generation via Celery and return initial progress."""
        try:
            params = json.loads(tool_call.input)
            title = params.get("title", "").strip()
            scenes = params.get("scenes", [])
            style = params.get("style", {})

            if not scenes:
                return ToolResponse(
                    output=ErrorTextContent(
                        value="No scenes provided. Please provide at least one scene."
                    )
                )

            scenes, capped, max_content_scenes = self._apply_scene_cap(scenes)
            if capped:
                logger.warning(
                    f"[STORYBOOK] Capping scenes to {max_content_scenes} content pages "
                    f"({max_content_scenes + 1} total scenes including cover)"
                )

            self._validate_page_count(len(scenes))
            logger.info(
                f"[STORYBOOK] Queueing Celery generation of {len(scenes)} scenes for session {self.session_id}"
            )
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        storybook_id: Optional[str] = None
        try:
            async with get_db_session_local() as db:
                session = await self._container.session_service.get_session_by_id(
                    db, uuid.UUID(self.session_id)
                )
                if not session:
                    raise RuntimeError("Session not found for storybook generation")
                user_api_key = await self._container.user_service.get_active_api_key(
                    db, session.user_id
                )
                if not user_api_key:
                    raise RuntimeError("No active API key found for user")

            storybook_name = title or style.get("title") or f"Storybook {uuid.uuid4().hex[:8]}"
            style_with_model = {
                **style,
                "image_model_name": self.image_model_name,
                "image_provider": self.image_provider,
                "user_text_position": self.user_text_position,
                "voice_enabled": self.voice_enabled,
                "language_code": self.storybook_language,
                "manga_layout": self.manga_layout,
            }

            async with get_db_session_local() as db:
                storybook = await self._container.storybook_service.create_storybook(
                    db,
                    session_id=self.session_id,
                    name=storybook_name,
                    style_json=style_with_model,
                    aspect_ratio=self.aspect_ratio,
                    resolution=self.resolution,
                    page_count=len(scenes),
                )
            storybook_id = storybook.id
            logger.info(f"[STORYBOOK] Created storybook record for Celery: {storybook_id}")

            total_pages = len(scenes)
            async with get_db_session_local() as db:
                await self._container.storybook_service.update_generation_status(
                    db,
                    storybook_id,
                    status="generating",
                    total_pages=total_pages,
                    completed_pages=0,
                    generating_pages=[1] if total_pages else [],
                    error_message=None,
                    generation_meta={
                        "cancelled": False,
                        "scenes": scenes,
                        "completed_scenes": [],
                        "actual_cost_usd_total": 0.0,
                        "tool_call_id": tool_call.id,
                        "parent_message_id": str(parent_message_id) if parent_message_id else None,
                        "model_id": model_id,
                        "run_id": run_id,
                        "user_id": session.user_id,
                        "reservation_id": reservation_id,
                        "tool_name": self.name,
                    },
                )

            task_id = queue_task(
                "ii_agent.workers.celery.tasks.storybook_generate_page",
                {
                    "storybook_id": storybook_id,
                    "scene_index": 0,
                },
                expires=STORYBOOK_TASK_EXPIRES_SECONDS,
                headers={
                    "session_id": self.session_id,
                    "user_id": session.user_id,
                },
            )

            async with get_db_session_local() as db:
                await self._container.storybook_service.update_generation_status(
                    db,
                    storybook_id,
                    generation_meta={
                        "active_task_id": task_id,
                    },
                )

            progress = StorybookProgressContent(
                storybook_id=storybook_id,
                storybook_name=storybook_name,
                total_pages=total_pages,
                completed_pages=0,
                current_page=1 if total_pages else 0,
                status="generating",
                pages=[],
                generating_pages=[1] if total_pages else [],
                polling=True,
            )

            return ToolResponse(output=progress)

        except Exception as e:
            logger.error(f"[STORYBOOK] Failed to queue Celery generation: {e}", exc_info=True)
            if storybook_id:
                async with get_db_session_local() as db:
                    await self._container.storybook_service.update_generation_status(
                        db,
                        storybook_id,
                        status="failed",
                        generating_pages=[],
                        error_message=str(e),
                    )
            return ToolResponse(
                output=ErrorTextContent(value=f"Storybook generation failed to start: {str(e)}")
            )

    def _augment_non_cover_prompt(self, image_prompt: str, text_content: str) -> str:
        """Augment the image prompt for non-cover pages.

        Subclasses (e.g. MangaGenerationTool) override this to inject
        speech-bubble text instead of the no-text instruction.
        """
        return (
            f"{image_prompt}\nIMPORTANT: Do NOT include any text, letters, captions, "
            "titles, or typography in the image. This is an interior page illustration only. "
            "Also IMPORTANT: This is NOT the cover. Do NOT recreate the cover layout, "
            "composition, or camera angle. Depict a distinct scene that differs clearly "
            "from the cover while keeping character consistency."
        )

    def _resolve_text_position(
        self,
        *,
        is_cover_page: bool,
        scene_text_position: Optional[str],
    ) -> str:
        """Resolve text position based on preferences and scene context."""
        if is_cover_page:
            return "none"

        if self.user_text_position is not None:
            position = self.user_text_position
        else:
            position = scene_text_position or DEFAULT_TEXT_POSITION

        if position not in ALLOWED_TEXT_POSITIONS:
            return DEFAULT_TEXT_POSITION

        return position

    def _build_style_context(self, style: dict[str, Any]) -> str:
        """Build style context string for prompt enhancement."""
        style_parts = []

        character_description = style.get("character_description")
        art_style = style.get("art_style")
        color_palette = style.get("color_palette")

        if character_description:
            style_parts.append(f"Character: {character_description}")

        if art_style:
            style_parts.append(f"Art style: {art_style}")

        if color_palette:
            style_parts.append(f"Color palette: {color_palette}")

        return ". ".join(style_parts) if style_parts else ""

    def _enhance_prompt_with_style(
        self,
        image_prompt: str,
        style_context: str,
        is_cover_page: bool = False,
        reference_type: Optional[str] = None,
        composition_rule: Optional[str] = None,
    ) -> str:
        """Enhance image prompt with style context for consistency.

        Args:
            image_prompt: The base image prompt
            style_context: Style information to apply
            is_cover_page: Whether this is the cover page
            reference_type: Type of reference being used - currently only "style_only" is used
            composition_rule: Optional rule for subject placement/safe zones
        """
        # EXTREMELY strong borderless instructions to prevent cropped/centered images with empty borders
        borderless_note = (
            f"CRITICAL TECHNICAL REQUIREMENTS - READ CAREFULLY: "
            f"This image MUST be generated at EXACTLY {self.aspect_ratio} aspect ratio and fill 100% of the canvas (FULL BLEED). "
            f"STRICTLY PROHIBITED: Empty borders, letterboxing, pillarboxing, white bars, gray bars, black bars, "
            f"centered content with surrounding empty space, frames, vignettes, padding, margins, or ANY unfilled areas. "
            f"ALSO PROHIBITED: Do NOT include any decorative borders, ornamental frames, book-style page borders, "
            f"or edge designs within the artwork itself. The scene should not look like a page inside a book, "
            f"but rather a full-screen illustration. "
            f"REQUIRED: The artwork must extend completely to all four edges (top, bottom, left, right) with zero empty space. "
            f"The composition must be designed to naturally fill the {self.aspect_ratio} frame edge-to-edge. "
            f"If the subject doesn't naturally fit {self.aspect_ratio}, adjust the composition (zoom, crop, add background elements) "
            f"to ensure 100% canvas coverage. NEVER add borders or empty space to fit - fill the entire frame with content."
        )

        # Add negative prompt for safety + non-cover rules
        negative_prompt = (
            " NEGATIVE PROMPT / STRICTLY PROHIBITED: No violence, gore, blood, injury, weapons, war, crime, "
            "threats, hate symbols, harassment, or bullying. No sexual or suggestive content, nudity, fetish, "
            "pornography, or sexualized minors. No self-harm or suicide. No drugs, alcohol abuse, smoking, or vaping. "
            "No gambling, political propaganda, extremist imagery, or controversial symbols. No real person likeness, "
            "no copyrighted characters/brands, no watermarks, and no text overlays."
        )
        if not is_cover_page:
            negative_prompt += (
                " Also, do NOT include any titles, text, letters, captions, typography, branding, logos, "
                "book cover elements, thumbnails, or headings. The image should be a pure illustration without "
                "any textual elements whatsoever. Ensure it does not look like a cover page or a table of contents. "
                "Do NOT repeat the cover scene, cover composition, or a cover-like centered pose/layout."
            )

        if composition_rule:
            borderless_note += f" {composition_rule}"

        # Add reference type context if applicable
        reference_note = ""
        if reference_type == "style_only":
            reference_note = (
                " Match the art style, color palette, and visual aesthetic of the reference image. "
                "CRITICAL CHARACTER LOCK: All characters appearing in the reference image MUST look identical "
                "in this new scene — same face, body proportions, hairstyle, hair color, skin tone, clothing, "
                "accessories, and all distinguishing features. Do NOT alter any aspect of the characters' appearance. "
                "Only the scene composition, camera angle, background, and action should change — "
                "the characters themselves must remain visually consistent with the reference."
            )

        if not style_context:
            return f"{image_prompt}. {borderless_note}{negative_prompt}{reference_note}"

        # Append style context to prompt and enforce borderless output
        return (
            f"{image_prompt}. {style_context}. {borderless_note}{negative_prompt}{reference_note}"
        )

    async def _generate_scene_image(
        self,
        prompt: str,
        user_api_key: str,
        scene_number: int,
        reference_image_urls: Optional[list[str]] = None,
        aspect_ratio: Optional[str] = None,
    ) -> str:
        """
        Generate AI image for a scene using the image generation service.

        Args:
            prompt: Enhanced image prompt
            user_api_key: User's API key for image generation
            scene_number: Scene number for logging
            reference_image_urls: Optional list of reference image URLs for style/character consistency
            aspect_ratio: Optional aspect ratio override (defaults to self.aspect_ratio)

        Returns:
            str: URL of generated image
        """
        target_aspect_ratio = aspect_ratio or self.aspect_ratio

        if reference_image_urls:
            logger.info(
                f"[STORYBOOK] Generating AI image for scene {scene_number} "
                f"with {len(reference_image_urls)} reference image(s) (AR: {target_aspect_ratio})"
            )
        else:
            logger.info(
                f"[STORYBOOK] Generating AI image for scene {scene_number} (AR: {target_aspect_ratio})"
            )

        # Generate image using tool server
        response = await _generate_image(
            prompt=prompt,
            aspect_ratio=target_aspect_ratio,
            image_size=self.resolution,
            session_id=self.session_id,
            user_api_key=user_api_key,
            image_urls=reference_image_urls,
            model_name=self.image_model_name,
            provider=self.image_provider,
            background=None,
        )

        image_url = response.get("url")
        if not image_url:
            raise RuntimeError(
                f"Image generation for scene {scene_number} did not return an image URL"
            )

        logger.info(f"[STORYBOOK] Scene {scene_number} AI image generated: {image_url}")
        return image_url

    def _get_optimal_aspect_ratio(
        self,
        base_aspect_ratio: str,
        text_position: str,
        text_percentage: int,
    ) -> str:
        """Calculate the best aspect ratio for generation to minimize cropping."""
        if text_position == "none" or text_percentage <= 0:
            return base_aspect_ratio

        # Parse base ratio (e.g., "16:9" -> 1.77)
        try:
            w, h = map(int, base_aspect_ratio.split(":"))
            base_ratio = w / h
        except ValueError:
            return base_aspect_ratio

        # Calculate target container ratio
        if text_position in ["left", "right"]:
            # Width is reduced
            target_ratio = base_ratio * (1 - text_percentage / 100.0)
        elif text_position in ["top", "bottom"]:
            # Height is reduced, so ratio (W/H) increases
            target_ratio = base_ratio / (1 - text_percentage / 100.0)
        else:
            return base_aspect_ratio

        # Select supported ratios based on provider
        provider_key = self.image_provider.lower() if self.image_provider else "gemini"
        supported = SUPPORTED_ASPECT_RATIOS_BY_PROVIDER.get(provider_key, DEFAULT_SUPPORTED_RATIOS)

        # Find closest match from supported ratios
        closest_ar = min(supported.keys(), key=lambda k: abs(supported[k] - target_ratio))
        return closest_ar

    def _calculate_safe_zones(
        self,
        base_aspect_ratio: str,
        gen_aspect_ratio: str,
        text_position: str,
        text_percentage: int,
    ) -> tuple[int, int]:
        """
        Calculate visible percentage of width and height.
        Returns (visible_width_pct, visible_height_pct).
        """
        if text_position == "none" or text_percentage <= 0:
            return 100, 100

        try:
            bw, bh = map(int, base_aspect_ratio.split(":"))
            base_ratio = bw / bh

            gw, gh = map(int, gen_aspect_ratio.split(":"))
            gen_ratio = gw / gh
        except ValueError:
            return 100, 100

        # Calculate container ratio
        if text_position in ["left", "right"]:
            container_ratio = base_ratio * (1 - text_percentage / 100.0)
        elif text_position in ["top", "bottom"]:
            container_ratio = base_ratio / (1 - text_percentage / 100.0)
        else:
            return 100, 100

        # Calculate overlap
        # If gen > container (wider): horizontal crop. visible = container / gen
        # If gen < container (taller): vertical crop. visible = gen / container

        if gen_ratio > container_ratio:
            # Generated image is wider than container -> Sides cropped
            visible_width = int((container_ratio / gen_ratio) * 100)
            return visible_width, 100
        else:
            # Generated image is taller than container -> Top/Bottom cropped
            visible_height = int((gen_ratio / container_ratio) * 100)
            return 100, visible_height

    async def _download_image(self, image_url: str) -> bytes:
        """Download an image from a URL and return its bytes."""
        logger.info(f"[STORYBOOK] Downloading image from {image_url}")

        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    image_bytes = response.content
                    logger.info(
                        f"[STORYBOOK] Successfully downloaded image ({len(image_bytes)} bytes)"
                    )
                    return image_bytes

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[STORYBOOK] Download attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[STORYBOOK] Download failed after {MAX_RETRIES} attempts: {e}")

        raise RuntimeError(f"Failed to download image after {MAX_RETRIES} attempts: {last_error}")

    async def _upload_composite(
        self,
        composite_png: bytes,
        scene_number: int,
    ) -> str:
        """Upload composite image to GCS and persist metadata."""
        file_id = str(uuid.uuid4())
        file_name = f"storybook-scene-{scene_number}-{file_id[:8]}.png"
        storage_path = f"sessions/{self.session_id}/storybook/{file_name}"

        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                content_io = BytesIO(composite_png)
                url = await anyio.to_thread.run_sync(
                    media_storage.upload_and_get_permanent_url,
                    content_io,
                    storage_path,
                    "image/png",
                )

                logger.info(f"[STORYBOOK] Uploaded composite to GCS: {storage_path}")

                await self._persist_composite_image(
                    file_id=file_id,
                    file_name=file_name,
                    storage_path=storage_path,
                    file_size=len(composite_png),
                )

                return url

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[STORYBOOK] Upload attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[STORYBOOK] Upload failed after {MAX_RETRIES} attempts: {e}")

        raise RuntimeError(f"Failed to upload composite after {MAX_RETRIES} attempts: {last_error}")

    async def _persist_composite_image(
        self,
        file_id: str,
        file_name: str,
        storage_path: str,
        file_size: int,
    ) -> None:
        """Store composite image metadata in file_uploads for the session."""
        async with get_db_session_local() as db:
            await self._container.file_service.create_file_record(
                db,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                storage_path=storage_path,
                content_type="image/png",
                session_id=self.session_id,
            )
        logger.info(f"[STORYBOOK] Persisted composite metadata: {file_id}")
