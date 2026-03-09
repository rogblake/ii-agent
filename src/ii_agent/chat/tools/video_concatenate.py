"""Video concatenation tool for chat mode.

Concatenates multiple video URLs into a single video using ffmpeg.
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

from ii_agent.chat.schemas import (
    ArrayResultContent,
    ErrorTextContent,
    FileUrlContentPart,
    TextContentPart,
)
from ii_agent.core.db.manager import get_db_session_local

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse

logger = logging.getLogger(__name__)


class ConcatenateVideosTool(BaseTool):
    """Concatenate multiple videos into a single video with smooth crossfade transitions."""

    # Default crossfade duration in seconds
    DEFAULT_CROSSFADE_DURATION = 0.0

    # Trusted domains for URL validation (SSRF prevention)
    TRUSTED_DOMAINS = [
        "storage.googleapis.com",
        "storage.cloud.google.com",
    ]

    def __init__(self, session_id: str, *, container):
        self._container = container
        self.session_id = session_id
        self._name = "concatenate_videos"
        self._init_trusted_domains()

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
            return getattr(video_config, 'custom_domain', None)
        except Exception as e:
            logger.warning(f"[CONCAT_VIDEO] Failed to load custom domain: {e}")
            return None

    def _is_trusted_url(self, url: str) -> bool:
        """Validate URL against trusted domains to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                logger.warning(f"[CONCAT_VIDEO] Rejected URL with invalid scheme: {parsed.scheme}")
                return False
            host = parsed.netloc.lower()
            for trusted in self.TRUSTED_DOMAINS:
                if host == trusted or host.endswith(f".{trusted}"):
                    return True
            logger.warning(f"[CONCAT_VIDEO] Rejected URL from untrusted domain: {host}")
            return False
        except Exception as e:
            logger.error(f"[CONCAT_VIDEO] URL validation error: {e}")
            return False

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="concatenate_videos",
            description=(
                "Concatenates multiple video URLs into a single video file with smooth crossfade transitions. "
                "Use this after generating multiple video segments to combine them into one continuous video. "
                "Videos are joined in the order provided with crossfade blending between segments. "
                "When returning the response to user, wrap it inside <video> tag with controls attribute."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "video_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of video URLs to concatenate, in the order they should appear",
                    },
                    "crossfade_duration": {
                        "type": "number",
                        "description": "(Optional) Duration of crossfade transition between segments in seconds (default: 0.0). Default with no crossfade, keep this default if user do not explicit requested",
                        "default": 0.0,
                    },
                    "transition_type": {
                        "type": "string",
                        "description": "Type of transition effect: 'fade', 'wipeleft', 'wiperight', 'slideright', 'slideleft' (default: 'fade')",
                        "default": "fade",
                        "enum": ["fade", "wipeleft", "wiperight", "slideright", "slideleft", "circlecrop", "dissolve"],
                    },
                },
            },
            required=["video_urls"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        try:
            params = json.loads(tool_call.input)
            video_urls = params.get("video_urls", [])
            crossfade_duration = params.get("crossfade_duration", self.DEFAULT_CROSSFADE_DURATION)
            transition_type = params.get("transition_type", "fade")

            if not video_urls:
                return ToolResponse(
                    output=ErrorTextContent(value="No video URLs provided")
                )

            if len(video_urls) == 1:
                return ToolResponse(
                    output=ArrayResultContent(
                        value=[
                            FileUrlContentPart(url=video_urls[0], mime_type="video/mp4"),
                            TextContentPart(text="Single video provided, no concatenation needed."),
                        ]
                    )
                )

            logger.info(f"[CONCAT_VIDEO] Concatenating {len(video_urls)} videos")

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[CONCAT_VIDEO] Invalid tool input: {e}")
            return ToolResponse(
                output=ErrorTextContent(value=f"Invalid tool input: {e}")
            )

        try:
            result = await self._concatenate_videos(video_urls, crossfade_duration, transition_type)

            if not result:
                return ToolResponse(
                    output=ErrorTextContent(value="Video concatenation failed")
                )

            if result.get("error"):
                error_msg = result["error"]
                failed_segments = result.get("failed_segments", [])
                details = "\n".join(failed_segments) if failed_segments else ""
                return ToolResponse(
                    output=ErrorTextContent(value=f"{error_msg}\n{details}".strip())
                )

            if not result.get("url"):
                return ToolResponse(
                    output=ErrorTextContent(value="Video concatenation failed - no output URL")
                )

            video_url = result["url"]
            storage_path = result.get("storage_path")
            file_size = result.get("size", 0)

            try:
                await self._persist_video(
                    video_url=video_url,
                    storage_path=storage_path,
                    file_size=file_size,
                )
            except Exception as persist_error:
                logger.warning(f"[CONCAT_VIDEO] Failed to persist video: {persist_error}")

            return ToolResponse(
                output=ArrayResultContent(
                    value=[
                        FileUrlContentPart(url=video_url, mime_type="video/mp4"),
                        TextContentPart(
                            text=f"Successfully concatenated {len(video_urls)} videos with {crossfade_duration}s crossfade transitions."
                        ),
                    ]
                )
            )

        except Exception as e:
            logger.error(f"[CONCAT_VIDEO] Video concatenation failed: {e}", exc_info=True)
            return ToolResponse(
                output=ErrorTextContent(value=f"Video concatenation failed: {str(e)}")
            )

    async def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        def _probe() -> float:
            try:
                cmd = [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return float(result.stdout.strip())
            except Exception as e:
                logger.error(f"[CONCAT_VIDEO] Failed to get duration: {e}")
                return 8.0

        return await anyio.to_thread.run_sync(_probe)

    async def _has_audio_stream(self, video_path: Path) -> bool:
        """Check if video has an audio stream using ffprobe."""
        def _probe() -> bool:
            try:
                cmd = [
                    "ffprobe", "-v", "error", "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return "audio" in result.stdout.strip().lower()
            except Exception as e:
                logger.warning(f"[CONCAT_VIDEO] Failed to check audio stream: {e}")
                return False

        return await anyio.to_thread.run_sync(_probe)

    async def _download_video_streaming(
        self,
        client: httpx.AsyncClient,
        url: str,
        dest: Path,
        semaphore: anyio.Semaphore | None = None,
        chunk_size: int = 64 * 1024,
    ) -> tuple[Path, bool, str | None]:
        """Stream download video to disk without loading entire file into memory."""
        async def _do_download() -> tuple[Path, bool, str | None]:
            try:
                async with client.stream("GET", url, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(f"[CONCAT_VIDEO] Stream response status: {response.status_code}")
                        return (dest, False, f"HTTP {response.status_code}")
                    async with await anyio.open_file(dest, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                            await f.write(chunk)
                return (dest, True, None)
            except Exception as e:
                logger.error(f"[CONCAT_VIDEO] Streaming download failed: {e}")
                return (dest, False, str(e))

        if semaphore:
            async with semaphore:
                return await _do_download()
        return await _do_download()

    async def _download_all_parallel(
        self,
        client: httpx.AsyncClient,
        urls: list[str],
        temp_dir: Path,
        max_concurrent: int = 10,
    ) -> tuple[list[Path], list[tuple[int, str]]]:
        """Download all videos in parallel with concurrency limit."""
        semaphore = anyio.Semaphore(max_concurrent)

        async def download_with_index(i: int, url: str):
            if not self._is_trusted_url(url):
                logger.error(f"[CONCAT_VIDEO] Untrusted URL {i + 1}: {url}")
                return (i, None, False, "untrusted domain")

            dest = temp_dir / f"segment_{i}.mp4"
            logger.info(f"[CONCAT_VIDEO] Downloading video {i + 1}/{len(urls)}")
            path, success, error = await self._download_video_streaming(
                client, url, dest, semaphore
            )
            return (i, path if success else None, success, error)

        async with anyio.create_task_group() as tg:
            results = [None] * len(urls)

            async def run_download(i: int, url: str):
                results[i] = await download_with_index(i, url)

            for i, url in enumerate(urls):
                tg.start_soon(run_download, i, url)

        video_paths = []
        failed_downloads = []

        for i, path, success, error in results:
            if success and path:
                video_paths.append((i, path))
            else:
                failed_downloads.append((i + 1, error or "download failed"))

        video_paths.sort(key=lambda x: x[0])
        ordered_paths = [path for _, path in video_paths]

        return ordered_paths, failed_downloads

    async def _concatenate_videos(
        self,
        video_urls: list[str],
        crossfade_duration: float = 0.5,
        transition_type: str = "fade",
    ) -> Optional[dict]:
        """Concatenate video URLs into a single video using ffmpeg with crossfade transitions."""
        try:
            def _make_temp_dir() -> Path:
                return Path(tempfile.mkdtemp(prefix="video_concat_", dir="/tmp"))

            temp_dir = await anyio.to_thread.run_sync(_make_temp_dir)
            video_paths = []
            failed_downloads = []

            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0)) as client:
                video_paths, failed_downloads = await self._download_all_parallel(
                    client, video_urls, temp_dir, max_concurrent=10
                )

            if failed_downloads:
                logger.error(f"[CONCAT_VIDEO] {len(failed_downloads)} of {len(video_urls)} downloads failed: {failed_downloads}")
                await self._cleanup_temp_files(temp_dir, video_paths)
                return {
                    "error": f"Failed to download {len(failed_downloads)} of {len(video_urls)} video segments",
                    "failed_segments": [f"Segment {idx}: {reason}" for idx, reason in failed_downloads],
                }

            if len(video_paths) < 2:
                logger.warning("[CONCAT_VIDEO] Not enough videos to concatenate")
                await self._cleanup_temp_files(temp_dir, video_paths)
                return {"url": video_urls[0]} if video_urls else None

            output_path = temp_dir / "concatenated.mp4"

            durations = []
            has_audio_list = []
            for video_path in video_paths:
                duration = await self._get_video_duration(video_path)
                durations.append(duration)
                has_audio = await self._has_audio_stream(video_path)
                has_audio_list.append(has_audio)

            all_have_audio = all(has_audio_list)
            if not all_have_audio:
                logger.info("[CONCAT_VIDEO] Not all videos have audio streams, will produce video-only output")

            def _run_ffmpeg_crossfade() -> bool:
                try:
                    input_args = []
                    for video_path in video_paths:
                        input_args.extend(["-i", str(video_path)])

                    video_filters = []
                    audio_filters = []
                    cumulative_offset = 0.0

                    for i in range(len(video_paths) - 1):
                        cumulative_offset += durations[i] - crossfade_duration

                        if i == 0:
                            input_v_a = "[0:v]"
                        else:
                            input_v_a = f"[v{i}]"
                        input_v_b = f"[{i+1}:v]"

                        if i < len(video_paths) - 2:
                            output_v = f"[v{i+1}]"
                        else:
                            output_v = "[vout]"

                        video_filters.append(
                            f"{input_v_a}{input_v_b}xfade=transition={transition_type}:duration={crossfade_duration}:offset={cumulative_offset}{output_v}"
                        )

                        if all_have_audio:
                            if i == 0:
                                input_a_a = "[0:a]"
                            else:
                                input_a_a = f"[a{i}]"
                            input_a_b = f"[{i+1}:a]"

                            if i < len(video_paths) - 2:
                                output_a = f"[a{i+1}]"
                            else:
                                output_a = "[aout]"

                            audio_filters.append(
                                f"{input_a_a}{input_a_b}acrossfade=d={crossfade_duration}{output_a}"
                            )

                    if all_have_audio:
                        filter_complex = ";".join(video_filters + audio_filters)
                    else:
                        filter_complex = ";".join(video_filters)

                    if all_have_audio:
                        cmd = [
                            "ffmpeg", "-y",
                            *input_args,
                            "-filter_complex", filter_complex,
                            "-map", "[vout]", "-map", "[aout]",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                            "-c:a", "aac", "-b:a", "192k",
                            str(output_path)
                        ]
                    else:
                        cmd = [
                            "ffmpeg", "-y",
                            *input_args,
                            "-filter_complex", filter_complex,
                            "-map", "[vout]",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                            "-an",
                            str(output_path)
                        ]

                    logger.debug(f"[CONCAT_VIDEO] Running ffmpeg with crossfade (audio={all_have_audio})")

                    result = subprocess.run(cmd, capture_output=True, timeout=600)
                    if result.returncode != 0:
                        logger.error(f"[CONCAT_VIDEO] ffmpeg crossfade failed: {result.stderr.decode()}")
                        return _run_ffmpeg_simple_concat()
                    return output_path.exists()
                except Exception as e:
                    logger.error(f"[CONCAT_VIDEO] ffmpeg crossfade exception: {e}")
                    return _run_ffmpeg_simple_concat()

            def _run_ffmpeg_simple_concat() -> bool:
                """Fallback to simple concatenation without crossfade."""
                try:
                    logger.debug("[CONCAT_VIDEO] Falling back to simple concatenation")
                    concat_file = temp_dir / "concat_list.txt"
                    with open(concat_file, "w") as f:
                        for video_path in video_paths:
                            f.write(f"file '{video_path}'\n")

                    if all_have_audio:
                        cmd = [
                            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(concat_file),
                            "-c", "copy",
                            str(output_path)
                        ]
                    else:
                        cmd = [
                            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(concat_file),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                            "-an",
                            str(output_path)
                        ]

                    result = subprocess.run(cmd, capture_output=True, timeout=300)
                    if result.returncode != 0:
                        logger.error(f"[CONCAT_VIDEO] ffmpeg simple concat failed: {result.stderr.decode()}")
                        return False
                    return output_path.exists()
                except Exception as e:
                    logger.error(f"[CONCAT_VIDEO] ffmpeg simple concat exception: {e}")
                    return False

            if crossfade_duration > 0:
                success = await anyio.to_thread.run_sync(_run_ffmpeg_crossfade)
            else:
                success = await anyio.to_thread.run_sync(_run_ffmpeg_simple_concat)

            if not success:
                logger.error("[CONCAT_VIDEO] ffmpeg concatenation failed")
                await self._cleanup_temp_files(temp_dir, video_paths)
                return {"url": video_urls[0]} if video_urls else None

            # Upload to GCS
            from ii_agent_tools.client.tool_client_config import ToolClientSettings

            tool_settings = ToolClientSettings()
            video_config = tool_settings.video_generate_config
            gcs_project_id = video_config.gcp_project_id
            gcs_bucket_name = video_config.gcs_output_bucket
            custom_domain = self._get_custom_domain()

            file_id = str(uuid.uuid4())
            file_name = f"video-concat-{file_id[:8]}.mp4"
            blob_path = f"sessions/{self.session_id}/generated/{file_name}"

            def _upload_to_gcs() -> tuple[int, str]:
                from google.cloud import storage as gcs_storage

                file_size = output_path.stat().st_size
                logger.debug(f"[CONCAT_VIDEO] Uploading {file_size} bytes")

                client = gcs_storage.Client(project=gcs_project_id)
                bucket = client.bucket(gcs_bucket_name)
                blob = bucket.blob(blob_path)

                with open(output_path, "rb") as f:
                    blob.upload_from_file(f, content_type="video/mp4")

                if custom_domain:
                    public_url = f"https://{custom_domain}/{blob_path}"
                else:
                    public_url = f"https://storage.googleapis.com/{gcs_bucket_name}/{blob_path}"

                return file_size, public_url

            file_size, public_url = await anyio.to_thread.run_sync(_upload_to_gcs)
            logger.info("[CONCAT_VIDEO] Concatenation complete")

            await self._cleanup_temp_files(temp_dir, video_paths, [output_path])

            return {
                "url": public_url,
                "storage_path": blob_path,
                "size": file_size,
            }

        except Exception as e:
            logger.error(f"[CONCAT_VIDEO] Concatenation failed: {e}", exc_info=True)
            if 'temp_dir' in locals() and temp_dir.exists():
                await self._cleanup_temp_files(temp_dir, video_paths if 'video_paths' in locals() else [])
            return {"url": video_urls[0]} if video_urls else None

    async def _cleanup_temp_files(
        self,
        temp_dir: Path,
        video_paths: list[Path] = None,
        extra_files: list[Path] = None,
    ):
        """Clean up temporary files and directory."""
        import shutil

        def _do_cleanup():
            shutil.rmtree(temp_dir, ignore_errors=True)

        await anyio.to_thread.run_sync(_do_cleanup)

    async def _persist_video(
        self,
        video_url: str,
        storage_path: Optional[str] = None,
        file_size: int = 0,
    ) -> Optional[str]:
        """Store video metadata in file_uploads for the session."""
        file_id = str(uuid.uuid4())

        parsed = urlparse(video_url)
        ext = Path(parsed.path).suffix or ".mp4"
        file_name = f"concatenated-{file_id[:8]}{ext}"

        async with get_db_session_local() as db:
            await self._container.file_service.create_file_record(
                db,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                storage_path=storage_path,
                content_type="video/mp4",
                session_id=self.session_id,
            )
        return file_id
