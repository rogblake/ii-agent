"""Video generation tool for chat mode."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse

from ii_agent.chat.types import (
    ArrayResultContent,
    ErrorTextContent,
    FileUrlContentPart,
    MediaPreferences,
    VideoSettings,
    VideoFrameReference,
)
from ii_agent.core.db import get_db_session_local
from ii_agent.core.storage.client import get_storage

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)

# Duration string to seconds mapping
DURATION_TO_SECONDS = {
    "4s": 4,
    "6s": 6,
    "8s": 8,
    "10s": 10,
    "12s": 12,
    "18s": 18,
    "24s": 24,
    "30s": 30,
}

# Maximum duration for single segment generation
MAX_SINGLE_SEGMENT_SECONDS = 8

# Maximum number of reference images supported by Veo API
MAX_REFERENCE_IMAGES = 3

# Resolution mapping from frontend to API-compatible values
RESOLUTION_MAPPING = {
    "720p": "720p",
    "1080p": "1080p",
    "2160p": "4k",
    "2460p": "4k",
    "4k": "4k",
}

# Default person generation setting
DEFAULT_PERSON_GENERATION = "allow_all"

# Trusted domains for SSRF protection
TRUSTED_DOMAINS = [
    "storage.googleapis.com",
    "sfile.ii.inc",
]

DEFAULT_VIDEO_COST_USD_PER_8S_SEGMENT = 0.75


def is_trusted_url(url: str) -> bool:
    """Check if URL host is a trusted domain for SSRF protection."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return False
        for trusted in TRUSTED_DOMAINS:
            if host == trusted or host.endswith(f".{trusted}"):
                return True
        return False
    except Exception:
        return False


class VideoGenerationTool(BaseTool):
    """Generate videos from text prompts."""

    def __init__(
        self,
        session_id: uuid.UUID,
        *,
        container: ApplicationContainer,
        media_preferences: Optional[MediaPreferences] = None,
        video_settings: Optional[VideoSettings] = None,
        video_frames: Optional[list[VideoFrameReference]] = None,
    ):
        self._container = container
        self.session_id = session_id
        self.media_preferences = media_preferences
        self.video_model_name = (
            media_preferences.model_name if media_preferences else "veo-3.1-generate-preview"
        )
        self.video_provider = media_preferences.provider if media_preferences else "vertex"
        self.video_settings = video_settings or VideoSettings()
        self.video_frames = video_frames or []
        self._name = "generate_video"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        description = (
            "Generates a video from a text prompt OR extends an existing video. "
            "For fresh generation: Creates video clips up to 8s. "
            "For extension: When source_video is provided with use_extension_api=True, extends the video by 7s "
            "while maintaining audio coherence. The result is a SINGLE merged video (original + extension). "
            "FRAME HANDLING for multi-segment videos (>8s): "
            "- User's START frame is automatically applied to the FIRST segment only. "
            "- User's END frame is ONLY applied when is_final_segment=True. "
            "- For the first segment of a long video, do NOT expect end frame to be used. "
            "For best results, use the five-part formula: [Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]. "
            "When returning the response to user, wrap it inside <video> tag with controls attribute. "
            "For example: <video src='https://example.com/video.mp4' controls autoplay></video>."
        )

        return ToolInfo(
            name="generate_video",
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Detailed description of the video to generate. "
                            "Include: cinematography (camera movement, composition), "
                            "subject, action, context, and style/ambiance. "
                            "For extensions: describe how the video should continue."
                        ),
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": (
                            "Optional. Describe what to exclude from the video. "
                            "Example: 'no text or watermarks, no buildings'"
                        ),
                    },
                    "source_video": {
                        "type": "string",
                        "description": (
                            "Optional. URL of video to extend. When provided with use_extension_api=True, "
                            "the API returns the FULL extended video (original + extension merged). "
                            "Pass the URL from a previous generate_video result. "
                            "Note: Extensions are limited to 720p resolution."
                        ),
                    },
                    "use_extension_api": {
                        "type": "boolean",
                        "description": (
                            "Optional. Default False. When True AND source_video is provided: "
                            "Extends the source video by up to 7s while maintaining audio coherence. "
                            "The result is a SINGLE merged video containing original + extension. "
                            "Use this for continuous scenes with seamless audio. "
                            "Note: Extensions limited to 720p resolution."
                        ),
                    },
                    "start_frame": {
                        "type": "string",
                        "description": (
                            "Optional. ONLY for CONTINUATION segments (2nd, 3rd, etc.) in multi-segment workflows. "
                            "Pass ONLY URLs returned by extract_frames tool. "
                            "DO NOT use for the FIRST segment - user's frame is applied automatically. "
                            "DO NOT invent URLs - the user's frame URLs are shown in [USER FRAMES: ...] context."
                        ),
                    },
                    "end_frame": {
                        "type": "string",
                        "description": (
                            "Optional. URL of an image to use as the last frame of the video. "
                            "When used with start_frame, creates smooth frame interpolation (requires 16:9 and 8s). "
                            "If not provided, uses the user's uploaded end frame (if any)."
                        ),
                    },
                    "duration": {
                        "type": "string",
                        "enum": ["4s", "6s", "8s"],
                        "description": (
                            "Optional. Duration of this video segment. Defaults to user's selected duration (max 8s). "
                            "For extensions, this controls the extension duration (max 7s). "
                            "Use this to control segment length in multi-segment workflows."
                        ),
                    },
                    "is_final_segment": {
                        "type": "boolean",
                        "description": (
                            "REQUIRED for multi-segment videos (>8s). Set to true for the LAST segment only. "
                            "When true, user's end frame will be applied to this final segment. "
                            "For the FIRST segment of multi-segment videos, do NOT set this - "
                            "end frame is reserved for the final segment only."
                        ),
                    },
                    "reference_images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": MAX_REFERENCE_IMAGES,
                        "description": (
                            f"Optional. List of up to {MAX_REFERENCE_IMAGES} image URLs to use as visual references "
                            "for style, characters, and scenes. Use these when creating video "
                            "based on storybook or other image references. "
                            f"Pass the URLs from storybook context when available. Maximum {MAX_REFERENCE_IMAGES} images."
                        ),
                    },
                },
            },
            required=["prompt"],
        )

    async def quote_cost(self, tool_call: ToolCallInput) -> None:
        """Return None; billing uses direct deduction after execution."""
        return None

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        logger.debug("[VIDEO_TOOL] Processing request")
        try:
            params = json.loads(tool_call.input)
            prompt = params["prompt"]
            negative_prompt = params.get("negative_prompt")

            # Get LLM-provided parameters for extension mode
            source_video = params.get("source_video")
            llm_use_extension_api = params.get("use_extension_api", False)

            # Get LLM-provided frame parameters (for multi-segment workflow)
            llm_start_frame = params.get("start_frame")
            llm_end_frame = params.get("end_frame")
            llm_duration = params.get("duration")
            is_final_segment = params.get("is_final_segment", False)
            reference_images = params.get("reference_images", [])[:MAX_REFERENCE_IMAGES]

            # Get video settings from user preferences
            aspect_ratio = self.video_settings.aspect_ratio
            raw_resolution = self.video_settings.resolution
            audio_included = self.video_settings.audio_included
            multishot_mode = self.video_settings.multishot_mode
            user_duration = self.video_settings.duration

            # Duration: Use user's setting, LLM can only override for multi-segment workflows
            if llm_duration:
                logger.info(
                    f"[VIDEO_TOOL] LLM overriding duration: user={user_duration}, llm={llm_duration}"
                )
                duration = llm_duration
            else:
                duration = user_duration

            logger.info(
                f"[VIDEO_TOOL] User settings received: duration={user_duration}, "
                f"resolution={raw_resolution}, aspect_ratio={aspect_ratio}, "
                f"audio={audio_included}, multishot={multishot_mode}"
            )

            if reference_images:
                logger.info(
                    f"[VIDEO_TOOL] Reference images provided: {len(reference_images)} images"
                )

            # Map resolution to API-compatible value
            resolution = RESOLUTION_MAPPING.get(raw_resolution, "720p")

            # Convert duration string to seconds
            duration_seconds = DURATION_TO_SECONDS.get(duration, 6)

            # Determine person generation setting based on mode
            person_generation = DEFAULT_PERSON_GENERATION

            # Determine extension mode
            is_extension_mode = source_video and llm_use_extension_api

            logger.debug(
                f"[VIDEO_TOOL] Settings: duration={duration_seconds}s, "
                f"aspect_ratio={aspect_ratio}, resolution={resolution}, "
                f"multishot={multishot_mode}, extension_mode={is_extension_mode}"
            )

            # Duration handling: extension max 7s, fresh generation max 8s
            if is_extension_mode:
                extension_seconds = min(duration_seconds, 7)
            elif duration_seconds > MAX_SINGLE_SEGMENT_SECONDS:
                logger.info(
                    f"[VIDEO_TOOL] Capping duration from {duration_seconds}s to {MAX_SINGLE_SEGMENT_SECONDS}s"
                )
                duration_seconds = MAX_SINGLE_SEGMENT_SECONDS

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[VIDEO_TOOL] Invalid tool input: {e}")
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            logger.info(
                f"Generating video: model={self.video_model_name}, duration={duration_seconds}s"
            )

            # Validate and use LLM-provided frame URLs (SSRF protection)
            start_frame_url = None
            end_frame_url = None

            if llm_start_frame and is_trusted_url(llm_start_frame):
                start_frame_url = await self._ensure_jpeg_url(llm_start_frame)
            elif llm_start_frame:
                logger.warning("[VIDEO_TOOL] Rejecting untrusted start_frame URL")

            if llm_end_frame and is_trusted_url(llm_end_frame):
                end_frame_url = await self._ensure_jpeg_url(llm_end_frame)
            elif llm_end_frame:
                logger.warning("[VIDEO_TOOL] Rejecting untrusted end_frame URL")

            # Track if LLM provided frames (indicates continuation segment)
            is_continuation_segment = start_frame_url is not None

            # Fall back to user's frames based on segment position
            user_total_duration = DURATION_TO_SECONDS.get(self.video_settings.duration, 6)
            is_multi_segment_video = user_total_duration > MAX_SINGLE_SEGMENT_SECONDS

            if self.video_frames:
                for frame in self.video_frames:
                    # User's START frame: only for first segment
                    if (
                        frame.type == "start"
                        and not start_frame_url
                        and not is_continuation_segment
                    ):
                        frame_url = await self._get_frame_url(frame)
                        if frame_url:
                            start_frame_url = frame_url

                    # User's END frame: single-segment or final segment only
                    elif frame.type == "end" and not end_frame_url:
                        is_single_segment_first = (
                            not is_multi_segment_video and not is_continuation_segment
                        )
                        should_use_end_frame = is_final_segment or is_single_segment_first

                        if should_use_end_frame:
                            frame_url = await self._get_frame_url(frame)
                            if frame_url:
                                end_frame_url = frame_url

            # Frame interpolation requires both start and end frames
            if end_frame_url and not start_frame_url:
                logger.warning(
                    "[VIDEO_TOOL] End frame provided without start frame - "
                    "clearing end frame (frame interpolation requires both)"
                )
                end_frame_url = None

            # Frame interpolation mode: enforce 16:9 and 8s (API constraint)
            using_frame_interpolation = start_frame_url is not None and end_frame_url is not None
            if using_frame_interpolation:
                logger.info(
                    f"[VIDEO_TOOL] Frame interpolation mode: overriding to 16:9 and 8s "
                    f"(was aspect_ratio={aspect_ratio}, duration={duration_seconds}s)"
                )
                aspect_ratio = "16:9"
                duration_seconds = 8

            # Use "allow_adult" when using image input
            if start_frame_url or end_frame_url:
                person_generation = "allow_adult"

            # Get tool client
            from ii_agent.agents.tools.clients import _get_client

            tool_client = _get_client()

            # EXTENSION MODE: Extend existing video
            if is_extension_mode:
                response = await tool_client.video_extension(
                    source_video_url=source_video,
                    prompt=prompt,
                    extension_seconds=extension_seconds,
                    generate_audio=audio_included,
                    person_generation=person_generation,
                    end_frame=end_frame_url,
                )
            else:
                # Fresh generation mode
                effective_duration = duration_seconds
                if reference_images:
                    effective_duration = 8
                    if duration_seconds != 8:
                        logger.info(
                            f"[VIDEO_TOOL] Reference images require 8s duration, "
                            f"overriding from {duration_seconds}s to 8s"
                        )

                generation_kwargs = {
                    "prompt": prompt,
                    "model_name": self.video_model_name,
                    "provider": self.video_provider or "vertex",
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": effective_duration,
                    "resolution": resolution,
                    "audio_included": audio_included,
                    "person_generation": person_generation,
                    "use_extension_api": False,
                    "start_frame": start_frame_url,
                    "end_frame": end_frame_url,
                }

                if negative_prompt:
                    generation_kwargs["negative_prompt"] = negative_prompt

                # Convert reference image URLs to VideoReferenceImage objects
                if reference_images:
                    converted_refs = self._convert_urls_to_reference_images(reference_images)
                    if converted_refs:
                        generation_kwargs["reference_images"] = converted_refs
                        logger.info(
                            f"[VIDEO_TOOL] Passing {len(converted_refs)} reference images to API"
                        )

                response = await tool_client.video_generation(**generation_kwargs)

            video_url = response.url
            storage_path = response.storage_path
            video_mime_type = response.mime_type or "video/mp4"
            video_size = response.size or 0
            video_cost = response.cost or 0.0

            if not video_url:
                error_message = getattr(response, "error", None)
                if error_message:
                    logger.warning(f"Video generation failed: {error_message}")
                    return ToolResponse(
                        output=ErrorTextContent(value=f"Video generation failed: {error_message}")
                    )
                else:
                    logger.warning("Video generation completed but no URL returned")
                    return ToolResponse(
                        output=ErrorTextContent(
                            value="Video generation completed but no video URL was returned. Please try again."
                        )
                    )

            logger.info(f"Video generated successfully: {video_url}, cost: {video_cost}")

            # Persist generated video metadata (best-effort)
            # Use the public URL as storage_path so resolve_signed_urls returns
            # it directly instead of signing against the wrong (private) bucket.
            try:
                await self._persist_generated_video(
                    video_url=video_url,
                    storage_path=video_url,
                    file_size=video_size,
                    mime_type=video_mime_type,
                )
            except Exception as persist_error:
                logger.warning(
                    f"Failed to persist generated video for session {self.session_id}: {persist_error}"
                )

            return ToolResponse(
                output=ArrayResultContent(
                    value=[
                        FileUrlContentPart(
                            url=video_url,
                            mime_type=video_mime_type,
                        )
                    ]
                ),
                cost_usd=video_cost,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}", exc_info=True)
            return ToolResponse(output=ErrorTextContent(value=f"Video generation failed: {str(e)}"))

    async def _ensure_jpeg_url(self, url: str) -> str:
        """If *url* points to a HEIC/HEIF file, convert to JPEG and return a
        new public URL.  Otherwise return the original URL unchanged."""
        url_path = url.split("?")[0].lower()
        if url_path.endswith((".heic", ".heif")):
            try:
                return await self._convert_heic_url_and_upload(url)
            except Exception as e:
                logger.warning(f"[VIDEO_TOOL] HEIC URL conversion failed: {e}, using original")
        return url

    async def _get_frame_url(self, frame: VideoFrameReference) -> Optional[str]:
        """Get public URL for a video frame reference.

        If the frame is HEIC/HEIF, it is converted to JPEG first because
        the video generation API does not support HEIC.  When a ``file_id``
        is available we always prefer it so the conversion path in
        ``_get_file_public_url`` can kick in.
        """
        try:
            # Prefer file_id path — it handles HEIC conversion
            if frame.file_id:
                return await self._get_file_public_url(frame.file_id)

            if frame.url and frame.url.startswith(("http://", "https://")):
                # Check if the URL itself points to a HEIC file
                url_path = frame.url.split("?")[0].lower()
                if url_path.endswith((".heic", ".heif")):
                    return await self._convert_heic_url_and_upload(frame.url)
                return frame.url

            return None
        except Exception as e:
            logger.warning(f"Failed to get frame URL for {frame.id}: {e}")
            return None

    async def _get_file_public_url(self, file_id: str) -> Optional[str]:
        """Get public URL for a file by its ID.

        HEIC/HEIF files are converted to JPEG before uploading because the
        video generation API (Veo) does not accept HEIC input.
        """
        try:
            async with get_db_session_local() as db:
                file_data = await self._container.file_service.get_file_by_id(db, file_id)
                if file_data and file_data.storage_path:
                    storage_path = file_data.storage_path
                    url = get_storage().public_url(storage_path)
                    logger.info(f"[VIDEO_TOOL] Resolved file {file_id} -> {url}")
                    return url
        except Exception as e:
            logger.warning(f"Failed to get public URL for file {file_id}: {e}")
        return None

    async def _convert_heic_and_upload(self, file_id: str, source_path: str) -> str:
        """Convert a HEIC file to JPEG and upload to public storage."""
        import io
        import anyio
        from ii_agent.agents.utils.heic import convert_heic_to_jpeg

        logger.info(f"[VIDEO_TOOL] Converting HEIC frame {file_id} to JPEG")
        public_path = f"video_generation_frames/{file_id[:8]}.jpg"

        file_obj = await get_storage().read(source_path)
        heic_bytes = file_obj.read()
        file_obj.close()

        def _convert(data: bytes) -> bytes:
            jpeg_bytes, _ = convert_heic_to_jpeg(data)
            return jpeg_bytes

        jpeg_bytes = await anyio.to_thread.run_sync(lambda: _convert(heic_bytes))
        await get_storage().write(public_path, io.BytesIO(jpeg_bytes), "image/jpeg")
        return get_storage().public_url(public_path)

    async def _convert_heic_url_and_upload(self, heic_url: str) -> str:
        """Download a HEIC image from a URL, convert to JPEG, and upload."""
        import io
        import anyio
        import httpx
        from ii_agent.agents.utils.heic import convert_heic_to_jpeg

        logger.info(f"[VIDEO_TOOL] Converting HEIC URL frame to JPEG")

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(heic_url)
            resp.raise_for_status()
            heic_bytes = resp.content

        def _convert(data: bytes) -> bytes:
            jpeg_bytes, _ = convert_heic_to_jpeg(data)
            return jpeg_bytes

        jpeg_bytes = await anyio.to_thread.run_sync(lambda: _convert(heic_bytes))
        file_id = str(uuid.uuid4())[:8]
        public_path = f"video_generation_frames/{file_id}.jpg"
        await get_storage().write(public_path, io.BytesIO(jpeg_bytes), "image/jpeg")
        return get_storage().public_url(public_path)

    async def _copy_to_public_storage(
        self, file_id: str, source_path: str, content_type: str | None
    ) -> str:
        """Copy a file from private storage to public media storage."""
        ext = source_path.rsplit(".", 1)[-1] if "." in source_path else "png"
        public_path = f"video_generation_frames/{file_id[:8]}.{ext}"

        file_data = await get_storage().read(source_path)
        await get_storage().write(public_path, file_data, content_type or "image/png")
        return get_storage().public_url(public_path)

    def _convert_urls_to_reference_images(self, urls: list[str]) -> list:
        """Convert image URLs to VideoReferenceImage objects for the API."""
        try:
            from ii_agent_tools.integrations.video_generation.base import VideoReferenceImage
        except ImportError:
            logger.warning("[VIDEO_TOOL] VideoReferenceImage not available")
            return []

        reference_images = []
        for url in urls:
            if not is_trusted_url(url):
                logger.warning(f"[VIDEO_TOOL] Skipping untrusted reference image URL: {url}")
                continue
            reference_images.append(VideoReferenceImage(url=url, reference_type="asset"))
            logger.debug(f"[VIDEO_TOOL] Added reference image URL: {url}")

        return reference_images

    async def _persist_generated_video(
        self,
        video_url: str,
        storage_path: Optional[str] = None,
        file_size: int = 0,
        mime_type: str = "video/mp4",
    ) -> Optional[str]:
        """Store generated video metadata in file_uploads for the session."""
        file_id = str(uuid.uuid4())

        parsed = urlparse(video_url)
        ext = Path(parsed.path).suffix or ".mp4"
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
