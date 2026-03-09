"""Handler for video generation media type."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import (
    BinaryContent,
    TextContent,
    MediaPreferences,
)
from ii_agent.chat.tools import BaseTool
from ii_agent.chat.tools.video_generate import (
    VideoGenerationTool,
    VideoSettings,
    VideoFrameReference,
    DURATION_TO_SECONDS,
)
from ii_agent.chat.tools.video_concatenate import ConcatenateVideosTool
from ii_agent.chat.tools.video_extract_frames import ExtractFramesTool
from ii_agent.chat.prompts.video_prompts import (
    VIDEO_GENERATION_SYSTEM_PROMPT,
    build_audio_guidance_hint,
    build_frame_transition_hint,
)
from ii_agent.chat.file_processor import (
    compress_image_for_provider,
    DEFAULT_IMAGE_LIMIT,
)
from ii_agent.core.storage.client import media_storage, storage
from ..modes.base import BaseModeStrategy
from ..modes.normal_mode import NormalModeStrategy
from ..registry import register_handler
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


# Duration threshold for long video workflow (LLM uses multi-segment workflow above this)
LONG_VIDEO_THRESHOLD_SECONDS = 8


@register_handler("video")
class VideoMediaHandler(BaseMediaHandler):
    """
    Handler for video generation media type.

    Supports text-to-video and image-to-video generation with:
    - Start frame (first frame reference)
    - End frame (last frame reference)
    - Duration, resolution, aspect ratio settings
    - Audio generation toggle
    - Multishot mode for scene splitting
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        """Detect mode for video generation. Currently uses NormalMode only."""
        return NormalModeStrategy()

    async def create_tools(
        self,
        *,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ServiceContainer,
    ) -> List[BaseTool]:
        """
        Create all video-related tools.

        Returns:
            - VideoGenerationTool: Generate single video segment (max 8s)
            - ConcatenateVideosTool: Combine multiple videos into one
            - ExtractFramesTool: Extract frames for video continuity
        """
        video_settings = self._extract_video_settings(media_preferences)
        video_frames = self._extract_video_frames(media_preferences)

        logger.info(
            f"[VIDEO_HANDLER] Creating tools with settings: "
            f"duration={video_settings.duration}, resolution={video_settings.resolution}, "
            f"aspect_ratio={video_settings.aspect_ratio}, audio={video_settings.audio_included}"
        )

        tools = [
            VideoGenerationTool(
                session_id=session_id,
                container=container,
                media_preferences=media_preferences,
                video_settings=video_settings,
                video_frames=video_frames,
            ),
            ConcatenateVideosTool(session_id=session_id, container=container),
            ExtractFramesTool(session_id=session_id, container=container),
        ]

        return tools

    async def build_llm_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
    ) -> List[BinaryContent | TextContent]:
        """
        Build LLM message parts with reference frames as image URLs.

        For video generation, this provides:
        1. Start/end frame images via URLs so the LLM can see them AND use exact URLs
        2. Storybook reference images and scripts when switching from storybook to video mode
        """
        video_context_parts: List[BinaryContent | TextContent] = []

        # Add video frame references (start/end frames)
        video_frames = self._extract_video_frames(media_preferences)
        if video_frames:
            frame_configs = [
                ("start", "START FRAME (Video should begin with this scene)"),
                ("end", "END FRAME (Video should end with this scene)"),
            ]

            for frame_type, label in frame_configs:
                for frame in video_frames:
                    if frame.type != frame_type:
                        continue

                    frame_url = await self._get_frame_public_url(frame, db_session)
                    if not frame_url:
                        continue

                    video_context_parts.append(
                        TextContent(text=f"\n--- {label} ---\nURL: {frame_url}")
                    )
                    image_content = await self._download_image_as_binary(frame_url)
                    if image_content:
                        video_context_parts.append(image_content)
                    logger.debug(f"[VIDEO_HANDLER] Added {frame_type} frame")

        # Add storybook context when switching from storybook to video mode
        storybook_ctx = self._extract_storybook_context(media_preferences)
        if storybook_ctx and storybook_ctx.get("reference_images"):
            reference_images = storybook_ctx["reference_images"]
            scripts = storybook_ctx.get("scripts", [])
            lines = [
                "\n\n--- STORYBOOK CONTEXT FOR VIDEO GENERATION ---",
                f"Storybook ID: {storybook_ctx.get('storybook_id', 'unknown')}",
                "Use these scenes as visual style references for the video.",
                "The video should match the visual style, characters, and scenes shown.\n",
                "Generated story:",
            ]

            for i, image_url in enumerate(reference_images):
                lines.append(f"- Scene {i + 1}:")
                lines.append(f"  + url: {image_url}")
                if i < len(scripts) and scripts[i]:
                    lines.append(f"  + script: {scripts[i]}")

            video_context_parts.append(TextContent(text="\n".join(lines)))

            logger.info(
                f"[VIDEO_HANDLER] Added storybook context: "
                f"{len(reference_images)} images, {len(scripts)} scripts"
            )

        return video_context_parts

    def build_system_prompt_addition(
        self,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build system prompt addition for video generation mode."""
        return VIDEO_GENERATION_SYSTEM_PROMPT

    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        """Generate tool hint text for video generation."""
        video_settings = self._extract_video_settings(media_preferences)

        # Build explicit user configuration block
        user_config = (
            f"\n⚙️ USER VIDEO SETTINGS (MUST RESPECT):"
            f"\n  • Duration: {video_settings.duration}"
            f"\n  • Resolution: {video_settings.resolution}"
            f"\n  • Aspect Ratio: {video_settings.aspect_ratio}"
            f"\n  • Audio: {'enabled' if video_settings.audio_included else 'disabled'}"
            f"\n  • Multishot: {'enabled' if video_settings.multishot_mode else 'disabled'}"
        )

        # Determine duration
        duration_str = video_settings.duration
        duration_seconds = DURATION_TO_SECONDS.get(duration_str, 6)

        video_frames = self._extract_video_frames(media_preferences)
        has_start = video_frames and any(f.type == "start" for f in video_frames)
        has_end = video_frames and any(f.type == "end" for f in video_frames)

        frame_context = ""
        if video_frames:
            if has_start and has_end:
                frame_context = " The user provided start and end frames (shown above with URLs) - generate a video that transitions between them."
            elif has_start:
                frame_context = " The user provided a start frame (shown above with URL) - generate a video starting from this image."
            elif has_end:
                frame_context = " The user provided an end frame (shown above with URL) - generate a video ending at this image."

        # Check if this needs multi-segment workflow
        needs_multi_segment = duration_seconds > LONG_VIDEO_THRESHOLD_SECONDS

        logger.debug(
            f"[VIDEO_HANDLER] Tool hint: duration={duration_seconds}s, multi_segment={needs_multi_segment}"
        )

        # Build audio guidance
        audio_hint = build_audio_guidance_hint(
            video_settings.audio_included,
            is_multi_segment=needs_multi_segment
        )

        # Build frame transition guidance
        frame_hint = build_frame_transition_hint(has_start, has_end)

        # Build storybook context hint
        storybook_hint = ""
        storybook_ctx = self._extract_storybook_context(media_preferences)
        if storybook_ctx and storybook_ctx.get("reference_images"):
            reference_images = storybook_ctx["reference_images"]
            image_list = "\n".join(
                f"  • Image {i + 1}: {url}"
                for i, url in enumerate(reference_images[:5])
            )
            storybook_hint = (
                f"\n\n📚 STORYBOOK CONTEXT AVAILABLE:"
                f"\nReference images and scripts from a storybook are provided above."
                f"\nWhen calling generate_video, you MUST pass the image URLs in the "
                f"'reference_images' parameter to maintain visual consistency."
                f"\nUse the scripts to guide the narrative/story of the video."
                f"\n\nReference image URLs to use:\n{image_list}"
            )

        # Build the hint based on whether multi-segment is needed
        if needs_multi_segment:
            initial_duration = 8
            remaining_duration = duration_seconds - initial_duration
            extensions_needed = (remaining_duration + 6) // 7

            extension_steps = []
            current_total = initial_duration
            for i in range(extensions_needed):
                ext_duration = min(7, duration_seconds - current_total)
                current_total += ext_duration
                step_num = i + 2
                if i == extensions_needed - 1 and has_end:
                    extension_steps.append(
                        f"\n   Step {step_num}: generate_video(prompt=\"[continue description]\", "
                        f"source_video=<previous_url>, use_extension_api=True, is_final_segment=True)"
                        f"\n           → Returns {current_total}s merged video (with end frame applied)"
                    )
                else:
                    extension_steps.append(
                        f"\n   Step {step_num}: generate_video(prompt=\"[continue description]\", "
                        f"source_video=<previous_url>, use_extension_api=True)"
                        f"\n           → Returns {current_total}s merged video"
                    )

            extension_steps_str = "".join(extension_steps)

            media_hint = (
                f"\n\n[User selected video generation: "
                f"type={media_preferences.type}, "
                f"model_name={media_preferences.model_name}"
                f"{user_config}"
                f"{frame_context}"
                f"\n\n📹 LONG VIDEO ({duration_seconds}s) - USE EXTENSION API"
                f"\n"
                f"\n🎯 YOUR TASK: Generate a {duration_seconds}s video using the Extension API."
                f"\nThis requires {extensions_needed + 1} total API calls: 1 initial (8s) + {extensions_needed} extension(s)."
                f"\n"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n📋 EXACT STEPS TO FOLLOW:"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n"
                f"\n   Step 1: generate_video(prompt=\"[your detailed prompt]\")"
                f"\n           → Returns 8s video URL (initial segment)"
                f"{extension_steps_str}"
                f"\n"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n✅ KEY POINTS:"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n• Extension API returns MERGED video (original + extension combined)"
                f"\n• NO concat_video needed - each extension builds on the previous"
                f"\n• Audio coherence is maintained across extensions"
                f"\n• Always pass the LATEST video URL as source_video"
                f"\n• The prompt for extensions should describe how the scene CONTINUES"
                f"\n• Resolution: Extensions use 720p (API limitation)"
                + (
                    f"\n• END FRAME: User provided end frame - set is_final_segment=True on last extension"
                    if has_end else ""
                )
                + (
                    f"\n• START FRAME: User's start frame is applied automatically to Step 1"
                    if has_start else ""
                )
                + f"\n\nSTART NOW: Call generate_video with your prompt for Step 1!]"
                + f"{storybook_hint}"
                + f"{audio_hint}"
                + f"{frame_hint}"
            )
        else:
            # Single segment hint
            media_hint = (
                f"\n\n[User selected video generation: "
                f"type={media_preferences.type}, "
                f"model_name={media_preferences.model_name}"
                f"{user_config}"
                f"{frame_context}"
                f"\n\n⚠️ IMPORTANT: Do NOT pass 'duration' parameter to generate_video - the user's duration setting ({video_settings.duration}) will be used automatically."
                f"\n\nYou MUST call the generate_video tool immediately with just the 'prompt' parameter.]"
                + f"{storybook_hint}"
                + f"{audio_hint}"
                + f"{frame_hint}"
            )

        return media_hint

    # ── Helper methods ────────────────────────────────────────────────

    def _extract_video_settings(self, media_preferences: MediaPreferences) -> VideoSettings:
        """Extract video settings from media preferences."""
        # Try to get video_settings from media_preferences if available
        video_settings_data = getattr(media_preferences, 'video_settings', None)
        if video_settings_data and isinstance(video_settings_data, dict):
            return VideoSettings(
                duration=video_settings_data.get("duration", "8s"),
                resolution=video_settings_data.get("resolution", "720p"),
                aspect_ratio=video_settings_data.get("aspect_ratio", "16:9"),
                audio_included=video_settings_data.get("audio_included", True),
                multishot_mode=video_settings_data.get("multishot_mode", False),
            )
        elif video_settings_data and hasattr(video_settings_data, 'duration'):
            return VideoSettings(
                duration=getattr(video_settings_data, 'duration', '8s'),
                resolution=getattr(video_settings_data, 'resolution', '720p'),
                aspect_ratio=getattr(video_settings_data, 'aspect_ratio', '16:9'),
                audio_included=getattr(video_settings_data, 'audio_included', True),
                multishot_mode=getattr(video_settings_data, 'multishot_mode', False),
            )
        return VideoSettings(
            aspect_ratio=media_preferences.aspect_ratio or "16:9",
            resolution=media_preferences.resolution or "720p",
        )

    def _extract_video_frames(self, media_preferences: MediaPreferences) -> list[VideoFrameReference]:
        """Extract video frames from media preferences."""
        video_frames_data = getattr(media_preferences, 'video_frames', None)
        if not video_frames_data:
            return []

        frames = []
        for frame_data in video_frames_data:
            if isinstance(frame_data, dict):
                frames.append(VideoFrameReference(
                    id=frame_data.get("id", ""),
                    url=frame_data.get("url", ""),
                    type=frame_data.get("type", "start"),
                    file_id=frame_data.get("file_id"),
                ))
            elif hasattr(frame_data, 'id'):
                frames.append(VideoFrameReference(
                    id=getattr(frame_data, 'id', ''),
                    url=getattr(frame_data, 'url', ''),
                    type=getattr(frame_data, 'type', 'start'),
                    file_id=getattr(frame_data, 'file_id', None),
                ))
        return frames

    def _extract_storybook_context(self, media_preferences: MediaPreferences) -> dict | None:
        """Extract storybook context from media preferences."""
        storybook_ctx = getattr(media_preferences, 'storybook_context', None)
        if not storybook_ctx:
            return None

        if isinstance(storybook_ctx, dict):
            if storybook_ctx.get("reference_images"):
                return storybook_ctx
        elif hasattr(storybook_ctx, 'reference_images'):
            ref_images = getattr(storybook_ctx, 'reference_images', [])
            if ref_images:
                return {
                    "storybook_id": getattr(storybook_ctx, 'storybook_id', 'unknown'),
                    "reference_images": ref_images,
                    "scripts": getattr(storybook_ctx, 'scripts', []),
                }
        return None

    async def _get_frame_public_url(
        self,
        frame: VideoFrameReference,
        db_session: AsyncSession,
    ) -> str | None:
        """Get the public URL for a video frame reference."""
        if frame.url and frame.url.startswith(("http://", "https://")):
            return frame.url

        file_id = frame.file_id or frame.url
        if file_id:
            url = await self._resolve_file_to_public_url(file_id)
            if url:
                return url

        return None

    async def _resolve_file_to_public_url(self, file_id: str) -> str | None:
        """Resolve a file ID to its public URL."""
        from ii_agent.core.db.manager import get_db_session_local
        from ii_agent.files.service import FileService

        try:
            async with get_db_session_local() as db:
                from ii_agent.files.dependencies import get_file_repository
                from ii_agent.sessions.dependencies import get_session_repository

                file_repo = get_file_repository()
                session_repo = get_session_repository()
                from ii_agent.files.service import FileService
                file_svc = FileService(file_repo=file_repo, session_repo=session_repo)

                file_data = await file_svc.get_file_by_id(db, file_id)
                if not file_data or not file_data.storage_path:
                    return None

                storage_path = file_data.storage_path
                if storage_path.startswith("sessions/"):
                    public_url = media_storage.get_public_url(storage_path)
                else:
                    public_url = await self._copy_to_public_storage(
                        file_id, storage_path, file_data.content_type
                    )

                logger.info(f"[VIDEO_HANDLER] Resolved file {file_id} -> {public_url}")
                return public_url
        except Exception as e:
            logger.warning(f"[VIDEO_HANDLER] Failed to get URL for file {file_id}: {e}")
            return None

    async def _copy_to_public_storage(
        self, file_id: str, source_path: str, content_type: str | None
    ) -> str:
        """Copy a file from private storage to public media storage."""
        import anyio

        ext = source_path.rsplit(".", 1)[-1] if "." in source_path else "png"
        public_path = f"video_generation_frames/{file_id[:8]}.{ext}"

        def _copy_sync():
            file_data = storage.read(source_path)
            return media_storage.upload_and_get_permanent_url(
                file_data, public_path, content_type or "image/png"
            )

        return await anyio.to_thread.run_sync(_copy_sync)

    async def _download_image_as_binary(self, url: str) -> Optional[BinaryContent]:
        """Download image from URL and return as BinaryContent."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if ";" in content_type:
                    content_type = content_type.split(";")[0].strip()

                url_path = url.split("?")[0]
                filename = url_path.split("/")[-1]

                if not content_type or content_type == "application/octet-stream":
                    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                    content_type = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                    }.get(ext, "image/png")

                image_data = response.content
                if content_type and content_type.startswith("image/"):
                    try:
                        image_data, content_type = compress_image_for_provider(
                            image_data, content_type, DEFAULT_IMAGE_LIMIT
                        )
                    except Exception as e:
                        logger.warning(
                            f"[VIDEO_HANDLER] Failed to compress frame image: {e}, using original"
                        )

                return BinaryContent(
                    path=filename,
                    mime_type=content_type,
                    data=image_data,
                )
        except httpx.HTTPStatusError as e:
            logger.warning(f"[VIDEO_HANDLER] HTTP {e.response.status_code} downloading image: {url}")
            return None
        except Exception as e:
            logger.warning(f"[VIDEO_HANDLER] Failed to download image: {e}")
            return None
