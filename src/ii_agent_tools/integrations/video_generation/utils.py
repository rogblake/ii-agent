import asyncio
import base64
import re
import uuid
from pathlib import Path

import aiohttp
import anyio

from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


PROMPT = """You are given a prompt describing a video. Your task is to break down the video description into {n_scenes} scene prompts.

Each scene prompt should:
- Represent a natural segment of the overall narrative described in the input prompt
- Contribute to a coherent flow across the entire video, with a logical progression in story, setting, characters, or actions
- Contain enough detail to guide high-quality video generation:
  - Subject: The object, person, animal, or scenery that you want in your video
  - Context: The background or setting in which the subject is placed
  - Action: What the subject is doing (for example, walking, running, or turning their head)
  - Style: This can be general or very specific. Consider using specific film style keywords, such as horror film, film noir, or animated styles like cartoon style render
  - Camera motion (Optional): What the camera is doing, such as an aerial view, eye-level, top-down shot, or low-angle shot
  - Composition (Optional): How the shot is framed, such as a wide shot, close-up, or extreme close-up
  - Ambiance (Optional): How color and light contribute to the scene, such as blue tones, night, or warm tones

The final video will be created by stitching the scenes together in sequence, so the breakdown should feel like a continuous video rather than separate clips

NOTE: Avoid violence, gore or any other inappropriate, unsafe terms.

<input_prompt>
{input_prompt}
</input_prompt>

Output the broken-down scenes in the following format:

<output_scenes>
<scene>
[Detailed description of the first scene]
</scene>
<scene>
[Detailed description of the second scene]
</scene>

[Continue for all remaining scenes until the last one]
</output_scenes>"""


def get_scene_breakdown_prompt(input_prompt: str, n_scenes: int) -> str:
    return PROMPT.format(input_prompt=input_prompt, n_scenes=n_scenes)


def parse_scenes(text: str) -> list[str]:
    """
    Parse <scene>...</scene> blocks from the model's output text.

    Args:
        text (str): The raw text containing <output_scenes> with <scene> blocks.

    Returns:
        list[str]: A list of scene descriptions, each as a string.
    """
    # Regex to capture text between <scene> and </scene>
    scenes = re.findall(r"<scene>\s*(.*?)\s*</scene>", text, re.DOTALL)

    # Strip whitespace from each scene
    return [scene.strip() for scene in scenes]


def _normalize_allowed_durations(
    allowed_durations: list[int] | tuple[int, ...] | None,
) -> list[int]:
    normalized = {
        int(duration)
        for duration in (allowed_durations or [4, 6, 8])
        if int(duration) > 0
    }
    return sorted(normalized, reverse=True)


def find_min_segment_solution(
    total_duration: int,
    allowed_durations: list[int] | tuple[int, ...] | None = None,
) -> list[int] | None:
    """Find an exact segment split that minimizes segment count."""
    durations = _normalize_allowed_durations(allowed_durations)
    if total_duration <= 0 or not durations:
        return None

    best_by_total: dict[int, list[int]] = {0: []}
    for current_total in range(1, total_duration + 1):
        best: list[int] | None = None
        for duration in durations:
            previous = best_by_total.get(current_total - duration)
            if previous is None:
                continue
            candidate = sorted([*previous, duration], reverse=True)
            if best is None:
                best = candidate
                continue
            if len(candidate) < len(best):
                best = candidate
                continue
            if len(candidate) == len(best) and tuple(candidate) > tuple(best):
                best = candidate
        if best is not None:
            best_by_total[current_total] = best

    return best_by_total.get(total_duration)


def split_long_duration(
    duration_seconds: int,
    *,
    allowed_durations: list[int] | tuple[int, ...] | None = None,
    allow_approximate: bool = True,
) -> list[int]:
    """Split a long duration into model-supported segment durations."""
    durations = _normalize_allowed_durations(allowed_durations)
    result = find_min_segment_solution(duration_seconds, durations)
    if result is not None:
        return result

    if not allow_approximate:
        logger.debug(
            "split_long_duration: %ss cannot be split exactly with durations=%s",
            duration_seconds,
            durations,
        )
        return []

    for adjusted in range(duration_seconds + 1, duration_seconds + max(durations, default=0) + 1):
        result = find_min_segment_solution(adjusted, durations)
        if result is not None:
            logger.debug(
                "split_long_duration: %ss rounded up to %ss using durations=%s",
                duration_seconds,
                adjusted,
                durations,
            )
            return result

    min_duration = min(durations) if durations else 1
    for adjusted in range(duration_seconds - 1, max(min_duration - 1, 0), -1):
        result = find_min_segment_solution(adjusted, durations)
        if result is not None:
            logger.debug(
                "split_long_duration: %ss rounded down to %ss using durations=%s",
                duration_seconds,
                adjusted,
                durations,
            )
            return result

    fallback_duration = durations[0] if durations else 8
    logger.debug(
        "split_long_duration: %ss cannot be split, using single %ss scene",
        duration_seconds,
        fallback_duration,
    )
    return [fallback_duration]


def get_nearest_valid_duration(
    duration_seconds: int,
    *,
    allowed_durations: list[int] | tuple[int, ...] | None = None,
) -> int:
    """Calculate the nearest valid duration to the given duration."""
    durations = _normalize_allowed_durations(allowed_durations)
    if not durations:
        return duration_seconds

    if duration_seconds <= min(durations):
        return min(durations)

    if duration_seconds in durations:
        return duration_seconds

    result = find_min_segment_solution(duration_seconds, durations)
    if result is not None:
        return sum(result)

    upward_total: int | None = None
    for adjusted in range(duration_seconds + 1, duration_seconds + max(durations) + 1):
        if find_min_segment_solution(adjusted, durations) is not None:
            upward_total = adjusted
            break

    downward_total: int | None = None
    for adjusted in range(duration_seconds - 1, max(min(durations) - 1, 0), -1):
        if find_min_segment_solution(adjusted, durations) is not None:
            downward_total = adjusted
            break

    if upward_total is None and downward_total is None:
        return max(durations)
    if upward_total is None:
        return downward_total
    if downward_total is None:
        return upward_total
    if (duration_seconds - downward_total) <= (upward_total - duration_seconds):
        return downward_total
    return upward_total


async def download_video(url: str, output_path: Path):
    """
    Download video from a public URL and save it as output_path.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()  # Raise error if the request failed

            # Stream directly to disk using async file I/O
            async with await anyio.open_file(output_path, "wb") as file:
                async for chunk in response.content.iter_chunked(8192):
                    await file.write(chunk)


async def download_video_bytes(url: str) -> bytes:
    """
    Download video from a public URL and return as bytes.

    Args:
        url: HTTP(S) URL of the video to download

    Returns:
        Video content as bytes
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()


async def extract_last_frame(video_path: Path, output_path: Path):
    """
    Extracts the last frame from a video using ffmpeg.

    Args:
        video_path (str): Path to the input video file.
        output_path (str): Path where the last frame image will be saved.
    """
    video_path_str = str(video_path)
    output_path_str = str(output_path)

    # ffmpeg command
    cmd = [
        "ffmpeg",
        "-sseof",
        "-1",  # Seek to 1 second before end (last frame)
        "-i",
        video_path_str,  # Input video file
        "-update",
        "1",  # Overwrite single output file
        "-q:v",
        "1",  # Best quality image
        output_path_str,  # Output file path
        "-y",  # Overwrite without asking
    ]

    # Run command
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    # Check for errors
    if proc.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg extract_last_frame failed with return code {proc.returncode}: {error_msg}")

    # Verify output file exists
    output_path_obj = Path(output_path_str)
    if not output_path_obj.exists():
        raise RuntimeError(f"ffmpeg did not create output file: {output_path_str}")

    if output_path_obj.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg created empty output file: {output_path_str}")


async def read_image_to_base64(image_path: Path) -> str:
    """
    Read an image file and return its base64-encoded string.
    """
    image_path_str = str(image_path)

    def _read_and_encode() -> str:
        with open(image_path_str, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    return await anyio.to_thread.run_sync(_read_and_encode)


async def merge_videos(
    video_paths: list[Path], output_path: Path, temp_dir: Path | None = None
):
    """
    Merge videos into a single video using ffmpeg.
    """
    # Create file list for ffmpeg concat
    if not temp_dir:
        temp_dir = Path(f"./tmp/video_generation_{uuid.uuid4().hex}")
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Validate input videos exist
    for video_path in video_paths:
        if not video_path.exists():
            raise RuntimeError(f"Video file does not exist: {video_path}")
        logger.debug(f"Input video: {video_path} (size: {video_path.stat().st_size} bytes)")

    concat_file = temp_dir / "concat_list.txt"

    def _write_concat_file():
        with open(concat_file, "w") as f:
            for video_path in video_paths:
                f.write(f"file '{video_path.absolute()}'\n")

    await anyio.to_thread.run_sync(_write_concat_file)

    # Merge videos
    concat_cmd = [
        "ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output_path),
        "-y",
    ]

    logger.debug(f"Running ffmpeg command: {' '.join(concat_cmd)}")

    # Run command
    proc = await asyncio.create_subprocess_exec(
        *concat_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    # Check for errors
    if proc.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg merge failed with return code {proc.returncode}: {error_msg}")

    # Verify output file exists and has content
    if not output_path.exists():
        raise RuntimeError(f"ffmpeg did not create output file: {output_path}")

    output_size = output_path.stat().st_size
    if output_size == 0:
        raise RuntimeError(f"ffmpeg created empty output file: {output_path}")

    logger.debug(f"Merged video created: {output_path} (size: {output_size} bytes)")


def generate_unique_video_name(length=12):
    """
    Generates a short, unique hexadecimal name suitable for a filename.

    Args:
        length (int): The desired length of the unique name. Defaults to 12.

    Returns:
        str: A unique hexadecimal string of the specified length.
    """
    # Generate a random UUID and take the first `length` characters of its hex representation
    return uuid.uuid4().hex[:length]


def construct_blob_path(file_name: str, session_id: str | None = None) -> str:
    """
    Construct the blob storage path for a video file.

    Args:
        file_name: Name of the video file
        session_id: Optional session ID for organizing by session

    Returns:
        Storage path string
    """
    if session_id:
        return f"sessions/{session_id}/generated/video_generation/{file_name}"
    return f"video_generation/{file_name}"
