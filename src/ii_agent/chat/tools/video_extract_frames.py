"""Video frame extraction tool for chat mode.

Extracts frames from a video at specified positions using ffmpeg.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import anyio
import httpx

from ii_agent.chat.types import (
    ArrayResultContent,
    ErrorTextContent,
    FileUrlContentPart,
    TextContentPart,
)
from ii_agent.core.db import get_db_session_local
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.files.types import AssetType

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse

logger = logging.getLogger(__name__)


class ExtractFramesTool(BaseTool):
    """Extract frames from a video at specified positions."""

    # Trusted domains for URL validation (SSRF prevention)
    TRUSTED_DOMAINS = [
        "storage.googleapis.com",
        "storage.cloud.google.com",
    ]

    def __init__(self, session_id: uuid.UUID, *, container):
        self._container = container
        self.session_id = session_id
        self._user_id: uuid.UUID | None = None
        self._name = "extract_frames"
        self._init_trusted_domains()

    async def _resolve_user_id(self) -> uuid.UUID:
        if self._user_id:
            return self._user_id
        from sqlalchemy import select
        from ii_agent.sessions.models import Session

        async with get_db_session_local() as db:
            result = await db.execute(select(Session).where(Session.id == self.session_id))
            session = result.scalar_one()
            self._user_id = session.user_id
        return self._user_id

    def _init_trusted_domains(self):
        """Initialize trusted domains from config."""
        custom_domain = self._get_custom_domain()
        if custom_domain:
            self.TRUSTED_DOMAINS = list(self.TRUSTED_DOMAINS) + [custom_domain]

    def _get_custom_domain(self) -> str | None:
        """Get custom domain from config."""
        try:
            from ii_agent_tools.client.tool_client_config import ToolClientSettings

            tool_settings = ToolClientSettings()
            video_config = tool_settings.video_generate_config
            return getattr(video_config, "custom_domain", None)
        except Exception as e:
            logger.warning(f"[EXTRACT_FRAMES] Failed to load custom domain: {e}")
            return None

    def _is_trusted_url(self, url: str) -> bool:
        """Validate URL against trusted domains to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                logger.warning(
                    f"[EXTRACT_FRAMES] Rejected URL with invalid scheme: {parsed.scheme}"
                )
                return False
            host = parsed.netloc.lower()
            for trusted in self.TRUSTED_DOMAINS:
                if host == trusted or host.endswith(f".{trusted}"):
                    return True
            logger.warning(f"[EXTRACT_FRAMES] Rejected URL from untrusted domain: {host}")
            return False
        except Exception as e:
            logger.error(f"[EXTRACT_FRAMES] URL validation error: {e}")
            return False

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="extract_frames",
            description=(
                "Extracts frames from a video at specified positions. "
                "Use this to get the last frame from a generated video segment for continuity "
                "when generating the next segment. "
                "Supports positions: 'first', 'last' (extracts at -0.5s for stability), "
                "'last-X' where X is offset in seconds (e.g., 'last-0.3'), "
                "or timestamp in 'MM:SS' format (e.g., '00:05'). "
                "Returns URLs of extracted frame images that can be used as start_frame in generate_video."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": "URL of the video to extract frames from",
                    },
                    "positions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Frame positions: 'first', 'last' (stable frame at -0.5s), 'last-0.3' (custom offset), or timestamp like '00:05' (MM:SS format)",
                    },
                },
            },
            required=["video_url", "positions"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        try:
            params = json.loads(tool_call.input)
            video_url = params.get("video_url")
            positions = params.get("positions", [])

            if not video_url:
                return ToolResponse(output=ErrorTextContent(value="No video URL provided"))

            if not positions:
                return ToolResponse(output=ErrorTextContent(value="No positions specified"))

            logger.debug(f"[EXTRACT_FRAMES] Extracting frames at: {positions}")

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[EXTRACT_FRAMES] Invalid tool input: {e}")
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            extracted_frames = await self._extract_frames(video_url, positions)

            if not extracted_frames:
                return ToolResponse(output=ErrorTextContent(value="Failed to extract any frames"))

            result_parts = []
            for frame in extracted_frames:
                result_parts.append(FileUrlContentPart(url=frame["url"], mime_type="image/png"))

            frame_summary = ", ".join(f"{f['position']}" for f in extracted_frames)
            result_parts.append(
                TextContentPart(
                    text=f"Extracted {len(extracted_frames)} frame(s) at positions: {frame_summary}. "
                    f"Use these URLs as start_frame or end_frame in generate_video."
                )
            )

            return ToolResponse(output=ArrayResultContent(value=result_parts))

        except Exception as e:
            logger.error(f"[EXTRACT_FRAMES] Frame extraction failed: {e}", exc_info=True)
            return ToolResponse(output=ErrorTextContent(value=f"Frame extraction failed: {str(e)}"))

    async def _extract_frames(self, video_url: str, positions: list[str]) -> list[dict]:
        """Extract frames at specified positions from a video."""
        extracted_frames = []

        try:
            if not self._is_trusted_url(video_url):
                logger.error(f"[EXTRACT_FRAMES] Rejected untrusted URL: {video_url[:80]}...")
                return []

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(video_url)
                if response.status_code != 200:
                    logger.error(
                        f"[EXTRACT_FRAMES] Failed to download video: {response.status_code}"
                    )
                    return []

            video_content = response.content

            def _setup_temp() -> tuple[Path, Path]:
                temp_dir = Path(tempfile.mkdtemp(prefix="extract_frames_", dir="/tmp"))
                video_path = temp_dir / "input.mp4"
                video_path.write_bytes(video_content)
                return temp_dir, video_path

            temp_dir, video_path = await anyio.to_thread.run_sync(_setup_temp)

            def _get_duration() -> float:
                try:
                    probe_cmd = [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(video_path),
                    ]
                    result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                    return float(result.stdout.strip())
                except Exception as e:
                    logger.error(f"[EXTRACT_FRAMES] Failed to get duration: {e}")
                    return 8.0

            duration = await anyio.to_thread.run_sync(_get_duration)

            for position in positions:
                seek_time = self._parse_position(position, duration)
                if seek_time is None:
                    logger.warning(f"[EXTRACT_FRAMES] Invalid position: {position}")
                    continue

                frame_path = temp_dir / f"frame_{position.replace(':', '_')}.png"

                def _extract_single_frame(
                    seek: float = seek_time, vpath: Path = video_path, fpath: Path = frame_path
                ) -> bool:
                    try:
                        cmd = [
                            "ffmpeg",
                            "-y",
                            "-ss",
                            str(seek),
                            "-i",
                            str(vpath),
                            "-vframes",
                            "1",
                            "-q:v",
                            "2",
                            str(fpath),
                        ]
                        result = subprocess.run(cmd, capture_output=True, timeout=60)
                        return fpath.exists()
                    except Exception as e:
                        logger.error(f"[EXTRACT_FRAMES] ffmpeg failed: {e}")
                        return False

                success = await anyio.to_thread.run_sync(_extract_single_frame)

                if success:
                    frame_result = await self._upload_frame(frame_path, position)
                    if frame_result:
                        extracted_frames.append(frame_result)

            def _cleanup():
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

            await anyio.to_thread.run_sync(_cleanup)

            return extracted_frames

        except Exception as e:
            logger.error(f"[EXTRACT_FRAMES] Extraction failed: {e}", exc_info=True)
            if "temp_dir" in locals() and temp_dir.exists():
                import shutil

                await anyio.to_thread.run_sync(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
            return []

    def _parse_position(self, position: str, duration: float) -> Optional[float]:
        """Parse position string to seek time in seconds."""
        position = position.strip().lower()

        if position == "first":
            return 0.0
        elif position == "last":
            return max(0, duration - 0.5)
        elif position.startswith("last-"):
            try:
                offset = float(position.replace("last-", ""))
                return max(0, duration - offset)
            except ValueError:
                logger.warning(f"[EXTRACT_FRAMES] Invalid last-offset format: {position}")
                return None
        else:
            try:
                if ":" in position:
                    parts = position.split(":")
                    if len(parts) == 2:
                        minutes, seconds = int(parts[0]), float(parts[1])
                        return minutes * 60 + seconds
                    elif len(parts) == 3:
                        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
                        return hours * 3600 + minutes * 60 + seconds
                else:
                    return float(position)
            except (ValueError, IndexError):
                return None

    async def _upload_frame(self, frame_path: Path, position: str) -> Optional[dict]:
        """Upload extracted frame to GCS and persist metadata."""
        try:
            from ii_agent_tools.client.tool_client_config import ToolClientSettings

            tool_settings = ToolClientSettings()
            video_config = tool_settings.video_generate_config
            gcs_project_id = video_config.gcp_project_id
            gcs_bucket_name = video_config.gcs_output_bucket
            custom_domain = self._get_custom_domain()

            file_id = str(uuid.uuid4())
            file_name = f"frame-{position.replace(':', '_')}-{file_id[:8]}.png"
            user_id = await self._resolve_user_id()
            blob_path = path_resolver.user_file(user_id, AssetType.IMAGE, file_id, "png")

            def _upload() -> tuple[int, str]:
                from google.cloud import storage as gcs_storage

                file_size = frame_path.stat().st_size

                client = gcs_storage.Client(project=gcs_project_id)
                bucket = client.bucket(gcs_bucket_name)
                blob = bucket.blob(blob_path)

                with open(frame_path, "rb") as f:
                    blob.upload_from_file(f, content_type="image/png")

                if custom_domain:
                    public_url = f"https://{custom_domain}/{blob_path}"
                else:
                    public_url = f"https://storage.googleapis.com/{gcs_bucket_name}/{blob_path}"

                return file_size, public_url

            file_size, public_url = await anyio.to_thread.run_sync(_upload)

            async with get_db_session_local() as db:
                await self._container.file_service.create_file_record(
                    db,
                    file_id=file_id,
                    file_name=file_name,
                    file_size=file_size,
                    storage_path=blob_path,
                    content_type="image/png",
                    session_id=self.session_id,
                )

            logger.debug("[EXTRACT_FRAMES] Frame uploaded")

            return {
                "url": public_url,
                "file_id": file_id,
                "position": position,
                "storage_path": blob_path,
            }

        except Exception as e:
            logger.error(f"[EXTRACT_FRAMES] Failed to upload frame: {e}", exc_info=True)
            return None
