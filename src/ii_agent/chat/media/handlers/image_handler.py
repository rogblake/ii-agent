from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import (
    BinaryContent,
    TextContent,
    MediaPreferences,
)
from ii_agent.chat.tools import ImageGenerationTool
from ii_agent.chat.file_processor import process_files_for_message
from ii_agent.core.storage.client import storage
from ..modes.base import BaseModeStrategy
from ..modes.advanced_mode import AdvancedModeStrategy
from ..modes.mini_tools_mode import MiniToolsModeStrategy
from ..modes.normal_mode import NormalModeStrategy
from ..utils import ReferenceResolver, PromptBuilder
from ..registry import register_handler
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


@register_handler("image")
class ImageMediaHandler(BaseMediaHandler):
    """
    Handler for image generation media type.

    Supports three modes:
    - AdvancedMode: Reference-based generation with subject/scene/style
    - MiniToolsMode: Template-based generation
    - NormalMode: Standard image generation
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        """
        Detect mode for image generation.

        Priority order:
        1. Advanced mode (if advanced_mode flag is set)
        2. Mini tools mode (if mini_tools is provided)
        3. Normal mode (default)
        """
        # Advanced mode takes precedence
        if media_preferences.advanced_mode:
            return AdvancedModeStrategy()

        # Mini tools mode
        if media_preferences.mini_tools is not None:
            return MiniToolsModeStrategy()

        # Default to normal mode
        return NormalModeStrategy()

    async def create_tool(
        self,
        *,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ServiceContainer,
    ) -> ImageGenerationTool:
        """Create ImageGenerationTool with configuration."""

        # Determine if this is mini tools mode
        is_mini_tools_mode = isinstance(mode_strategy, MiniToolsModeStrategy)

        # Get media references
        media_refs = media_preferences.references if media_preferences.references else None

        return ImageGenerationTool(
            session_id=session_id,
            media_preferences=media_preferences,
            image_aspect_ratio=media_preferences.aspect_ratio,
            image_resolution=media_preferences.resolution,
            references=media_refs,
            mini_tools_mode=is_mini_tools_mode,
            container=container,
        )

    async def build_llm_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
    ) -> List[BinaryContent | TextContent]:
        """Build LLM message parts with reference images and labels."""
        # Only advanced mode needs to load reference images
        if not isinstance(mode_strategy, AdvancedModeStrategy):
            return []

        # Load and attach advanced mode reference images for LLM to "see"
        # Images are organized with labels so LLM knows exactly which image is which type
        advanced_mode_parts: List[BinaryContent | TextContent] = []

        # Track current image index for labeling
        current_idx = 1

        # 1. Load reference images by type (subject, scene, style) in order
        if media_preferences.references:
            refs = media_preferences.references

            # Group references by type to maintain order: subject -> scene -> style
            subject_refs = [r for r in refs if r.type == "subject"]
            scene_refs = [r for r in refs if r.type == "scene"]
            style_refs = [r for r in refs if r.type == "style"]

            # Load SUBJECT references first
            if subject_refs:
                subject_file_ids = [ref.file_id for ref in subject_refs]
                indices_str = ", ".join([f"#{i}" for i in range(current_idx, current_idx + len(subject_refs))])
                advanced_mode_parts.append(
                    TextContent(text=f"\n SUBJECT REFERENCE {indices_str} - THIS PERSON/CHARACTER MUST APPEAR IN OUTPUT:")
                )
                processed = await process_files_for_message(
                    db_session=db_session,
                    file_ids=subject_file_ids,
                    storage=storage,
                    session_id=session_id,
                )
                if processed.binary_parts:
                    advanced_mode_parts.extend(processed.binary_parts)
                    current_idx += len(processed.binary_parts)
                    logger.info(f"[ADVANCED_MODE] Loaded {len(processed.binary_parts)} SUBJECT reference(s)")

            # Load SCENE references second
            if scene_refs:
                scene_file_ids = [ref.file_id for ref in scene_refs]
                indices_str = ", ".join([f"#{i}" for i in range(current_idx, current_idx + len(scene_refs))])
                advanced_mode_parts.append(
                    TextContent(text=f"\n SCENE REFERENCE {indices_str} - USE THIS ENVIRONMENT AS BACKGROUND:")
                )
                processed = await process_files_for_message(
                    db_session=db_session,
                    file_ids=scene_file_ids,
                    storage=storage,
                    session_id=session_id,
                )
                if processed.binary_parts:
                    advanced_mode_parts.extend(processed.binary_parts)
                    current_idx += len(processed.binary_parts)
                    logger.info(f"[ADVANCED_MODE] Loaded {len(processed.binary_parts)} SCENE reference(s)")

            # Load STYLE references third
            if style_refs:
                style_file_ids = [ref.file_id for ref in style_refs]
                indices_str = ", ".join([f"#{i}" for i in range(current_idx, current_idx + len(style_refs))])
                advanced_mode_parts.append(
                    TextContent(text=f"\n STYLE REFERENCE {indices_str} - COPY ART STYLE ONLY (DO NOT COPY ANY SUBJECT/PERSON FROM THIS IMAGE):")
                )
                processed = await process_files_for_message(
                    db_session=db_session,
                    file_ids=style_file_ids,
                    storage=storage,
                    session_id=session_id,
                )
                if processed.binary_parts:
                    advanced_mode_parts.extend(processed.binary_parts)
                    current_idx += len(processed.binary_parts)
                    logger.info(f"[ADVANCED_MODE] Loaded {len(processed.binary_parts)} STYLE reference(s)")

        # 2. Load previously generated images in this session
        generated_images = await ReferenceResolver.get_session_images(
            db_session=db_session,
            session_id=session_id,
        )
        if generated_images:
            # Calculate starting index for generated images (continue from current_idx)
            indices_str = ", ".join([f"#{i}" for i in range(current_idx, current_idx + len(generated_images))])
            advanced_mode_parts.append(
                TextContent(text=f"\n--- PREVIOUSLY GENERATED IMAGE(S) {indices_str} (Modify these when user asks for changes) ---")
            )
            processed_generated = await process_files_for_message(
                db_session=db_session,
                file_ids=generated_images,
                storage=storage,
                session_id=session_id,
            )
            if processed_generated.binary_parts:
                advanced_mode_parts.extend(processed_generated.binary_parts)
                logger.info(
                    f"[ADVANCED_MODE] Loaded {len(processed_generated.binary_parts)} generated image(s) from conversation"
                )

        return advanced_mode_parts

    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        """Generate tool hint text for image generation."""
        # Build mode-specific prompt context
        mode_context = await mode_strategy.build_prompt_context(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
        )

        # Build settings constraint notice
        settings_constraint = PromptBuilder.build_settings_constraint(
            aspect_ratio=media_preferences.aspect_ratio,
            resolution=media_preferences.resolution,
        )

        # Build base media hint
        tool_fragment = ""
        if media_preferences.mini_tools:
            mini_tool = media_preferences.mini_tools
            tool_fragment = PromptBuilder.build_mini_tool_hint(
                mini_tool_id=mini_tool.id,
                mini_tool_name=mini_tool.name,
            )

        media_hint = (
            f"\n\n[User selected media generation: "
            f"type={media_preferences.type}, "
            f"model_name={media_preferences.model_name}."
            f"{tool_fragment} You MUST call the generate_image tool immediately.]"
            f"{settings_constraint}"
            f"{mode_context}"
        )

        return media_hint
