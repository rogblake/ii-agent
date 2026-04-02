"""Image generation tool for chat mode."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple, TYPE_CHECKING
from urllib.parse import urlparse

from ii_agent.chat.types import (
    ArrayResultContent,
    ErrorTextContent,
    ImageUrlContentPart,
    MediaPreferences,
    MediaReference,
)
from ii_agent.content.media.service import _generate_image
from ii_agent.core.db import get_db_session_local

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_GENERATION_MAX_COST_USD = 0.05


# Model-specific resolution and aspect ratio configurations
# GPT Image 1.5: Only supports fixed resolutions - 1024x1024, 1536x1024, 1024x1536
GPT_IMAGE_ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",  # landscape
    "2:3": "1024x1536",  # portrait
}

# Gemini 3 Pro (nano-banana-pro): Supports 1K, 2K, 4K and various aspect ratios
GEMINI_SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
GEMINI_SUPPORTED_RESOLUTIONS = ["1K", "2K", "4K"]

# Default aspect ratios for models that support all standard ratios
DEFAULT_ASPECT_RATIOS = ["16:9", "1:1", "9:16", "4:3", "3:4"]


class ImageGenerationTool(BaseTool):
    """Generate images from text prompts."""

    max_cost_usd = DEFAULT_IMAGE_GENERATION_MAX_COST_USD

    def __init__(
        self,
        session_id: uuid.UUID,
        *,
        container: ApplicationContainer,
        media_preferences: Optional[MediaPreferences] = None,
        image_aspect_ratio: Optional[str] = None,
        image_resolution: Optional[str] = None,
        references: Optional[list[MediaReference] | list[dict[str, Any]]] = None,
        mini_tools_mode: bool = False,
    ):
        self._container = container
        self.session_id = session_id
        self.media_preferences = media_preferences
        self.image_model_name = media_preferences.model_name if media_preferences else None
        self.image_provider = media_preferences.provider if media_preferences else None
        # Prioritize reference_file_ids from mini tool, fallback to user_file_ids from message
        if (
            media_preferences
            and media_preferences.mini_tools
            and media_preferences.mini_tools.reference_file_ids
        ):
            self.user_file_ids = media_preferences.mini_tools.reference_file_ids
        else:
            self.user_file_ids = []
        self.image_aspect_ratio = image_aspect_ratio
        self.image_resolution = image_resolution
        self.references = references or []
        self.mini_tools_mode = mini_tools_mode
        self._name = "generate_image"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        description = (
            "Generates a high quality image from a text prompt. "
            "Use this when the user wants to create a visual summary, diagram, chart, infographic, or poster."
        )

        return ToolInfo(
            name="generate_image",
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the image to generate.",
                    },
                },
            },
            required=["prompt"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        try:
            params = json.loads(tool_call.input)
            prompt = params["prompt"]

            aspect_ratio_input = (
                self.image_aspect_ratio if self.image_aspect_ratio is not None else "1:1"
            )
            resolution_input = self.image_resolution if self.image_resolution is not None else "1K"
            model_name = self.image_model_name

            aspect_ratio, image_size = self._get_model_adjusted_settings(
                aspect_ratio_input, resolution_input
            )
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            logger.info(
                f"Generating image for session {self.session_id}: "
                f"model={model_name}, "
                f"frontend_aspect_ratio={self.image_aspect_ratio}, "
                f"frontend_resolution={self.image_resolution}, "
                f"final_aspect_ratio={aspect_ratio}, "
                f"final_image_size={image_size}"
            )

            # Resolve user API key for tool server call
            async with get_db_session_local() as db:
                session = await self._container.session_service.get_session_by_id(
                    db, self.session_id
                )
                if not session:
                    raise RuntimeError("Session not found for image generation")
                user_api_key = await self._container.user_service.get_active_api_key(
                    db, session.user_id
                )
                if not user_api_key:
                    logger.warning("No active API key found for user")

            # Collect all file IDs from all sources
            all_file_ids: list[str] = []

            # 1. From user references (media_preferences.references)
            if self.references:
                for ref in self.references:
                    if hasattr(ref, "file_id"):
                        all_file_ids.append(str(ref.file_id))
                    elif isinstance(ref, dict) and ref.get("file_id"):
                        all_file_ids.append(str(ref["file_id"]))

            # 2. From mini_tools reference_file_ids
            if self.user_file_ids:
                all_file_ids.extend([str(fid) for fid in self.user_file_ids if fid])

            # 3. Load all session images (exclude mini tools mode)
            if not self.mini_tools_mode:
                session_images = await self._get_all_session_images()
                if session_images:
                    all_file_ids.extend(session_images)

            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_file_ids: list[str] = []
            for fid in all_file_ids:
                if fid not in seen:
                    seen.add(fid)
                    unique_file_ids.append(fid)

            # Batch-resolve all unique file IDs to signed URLs via FileService
            resolved_file_urls: list[str] = []
            if unique_file_ids:
                try:
                    async with get_db_session_local() as url_db:
                        url_map = await self._container.file_service.resolve_signed_urls(
                            url_db, [uuid.UUID(fid) for fid in unique_file_ids]
                        )
                    for fid in unique_file_ids:
                        url = url_map.get(uuid.UUID(fid))
                        if url:
                            resolved_file_urls.append(url)
                except Exception as e:
                    logger.warning(f"Failed to batch-resolve file URLs: {e}")

            logger.info(f"Resolved {len(resolved_file_urls)} file URLs for image generation")

            # Determine background parameter based on mini tool
            background = None
            if (
                self.mini_tools_mode
                and self.media_preferences
                and self.media_preferences.mini_tools
            ):
                if self.media_preferences.mini_tools.name == "Remove Background":
                    background = "transparent"
                    logger.info("Setting background to transparent for Remove Background tool")

            # Generate image using tool server
            response = await _generate_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                session_id=self.session_id,
                user_api_key=user_api_key,
                image_urls=resolved_file_urls or None,
                model_name=model_name,
                provider=self.image_provider,
                background=background,
            )
            image_url = response.get("url")
            image_cost = response.get("cost") or 0.0
            if not image_url:
                raise RuntimeError("Image generation did not return an image URL")

            logger.info(f"Image generated successfully: {image_url}")

            # Persist generated image into session library (best-effort)
            try:
                storage_path = response.get("storage_path")
                file_size = response.get("size", 0)
                mime_type = response.get("mime_type", "image/png")
                file_name = response.get("file_name")
                await self._persist_generated_image(
                    image_url=image_url,
                    storage_path=storage_path,
                    file_size=file_size,
                    mime_type=mime_type,
                    file_name=file_name,
                )
            except Exception as persist_error:
                logger.warning(
                    f"Failed to persist generated image for session {self.session_id}: {persist_error}"
                )

            # Return image URL result
            return ToolResponse(
                output=ArrayResultContent(value=[ImageUrlContentPart(url=image_url)]),
                cost_usd=image_cost,
            )

        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            return ToolResponse(output=ErrorTextContent(value=f"Image generation failed: {str(e)}"))

    async def _persist_generated_image(
        self,
        image_url: str,
        storage_path: str | None = None,
        file_size: int = 0,
        mime_type: str = "image/png",
        file_name: str | None = None,
    ) -> str | None:
        """Store generated image metadata from /image-generation in file_uploads for the session."""
        file_id = str(uuid.uuid4())

        # Use file_name from /image-generation response, or generate one as fallback
        if not file_name:
            parsed = urlparse(image_url)
            ext = Path(parsed.path).suffix or ".png"
            file_name = f"generated-{file_id[:8]}{ext}"

        async with get_db_session_local() as db:
            await self._container.file_service.create_file_record(
                db,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                storage_path=storage_path,
                content_type=mime_type,
                session_id=self.session_id,
            )
        return file_id

    def _get_model_adjusted_settings(
        self, aspect_ratio: str, resolution: str
    ) -> Tuple[str, Optional[str]]:
        """
        Adjust aspect_ratio and resolution based on model constraints.

        Returns:
            Tuple of (aspect_ratio, image_size) where image_size may be None for models
            that use fixed resolutions (like GPT Image 1.5).

        GPT Image 1.5 (OpenAI):
            - Only supports: 1024x1024 (1:1), 1536x1024 (3:2), 1024x1536 (2:3)
            - Resolution is fixed, so image_size is passed as the actual pixel size

        Gemini 3 Pro (nano-banana-pro):
            - Supports: 1K, 2K, 4K resolutions
            - Supports: 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, 21:9 aspect ratios
        """
        model_name = self.image_model_name or ""
        provider = self.image_provider or ""

        # GPT Image 1.5 - use fixed pixel sizes based on aspect ratio
        if model_name == "gpt-image-1.5" or provider == "openai":
            # Map aspect ratio to GPT's fixed sizes
            if aspect_ratio in GPT_IMAGE_ASPECT_TO_SIZE:
                pixel_size = GPT_IMAGE_ASPECT_TO_SIZE[aspect_ratio]
            else:
                # Default to 1:1 if unsupported aspect ratio
                logger.warning(
                    f"GPT Image 1.5 does not support aspect ratio {aspect_ratio}, "
                    "defaulting to 1:1 (1024x1024)"
                )
                aspect_ratio = "1:1"
                pixel_size = "1024x1024"

            # For GPT Image 1.5, return the pixel size as image_size
            return aspect_ratio, pixel_size

        # Gemini 3 Pro (nano-banana-pro) and other Gemini models
        if provider == "gemini" or model_name in ["gemini-3-pro-image-preview"]:
            # Validate aspect ratio
            if aspect_ratio not in GEMINI_SUPPORTED_ASPECT_RATIOS:
                logger.warning(
                    f"Gemini does not support aspect ratio {aspect_ratio}, defaulting to 1:1"
                )
                aspect_ratio = "1:1"

            # Validate resolution
            if resolution not in GEMINI_SUPPORTED_RESOLUTIONS:
                logger.warning(f"Gemini does not support resolution {resolution}, defaulting to 1K")
                resolution = "1K"

            return aspect_ratio, resolution

        # Default behavior for other models - pass through as-is
        return aspect_ratio, resolution

    async def _get_all_session_images(self) -> list[str]:
        """Get all images (generated + uploaded) from the current session."""
        try:
            async with get_db_session_local() as db:
                all_files = await self._container.file_service.get_files_by_session_id(
                    db, self.session_id
                )
            if not all_files:
                return []

            # Filter for images only
            image_file_ids = []
            for file_data in all_files:
                is_image = (
                    file_data.content_type and file_data.content_type.startswith("image/")
                ) or (
                    file_data.storage_path
                    and ("/generated/" in file_data.storage_path or "/uploads/" in file_data.storage_path)
                )
                if is_image:
                    image_file_ids.append(str(file_data.id))

            logger.info(f"Found {len(image_file_ids)} images in session {self.session_id}")
            return image_file_ids

        except Exception as e:
            logger.error(f"Error fetching session images: {e}", exc_info=True)
            return []

