"""HEIC/HEIF to JPEG conversion utilities for agent runtime.

All LLM providers (Anthropic, OpenAI, Google) reject HEIC natively,
so images must be converted to JPEG before sending.
"""

import io
from typing import Optional


def is_heic_format(
    image_format: Optional[str] = None,
    mime_type: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    url: Optional[str] = None,
) -> bool:
    """Check if the image format is HEIC/HEIF.

    Detection uses metadata first (format string, MIME type), then falls
    back to URL extension check and magic-byte sniffing of the ISOBMFF
    ``ftyp`` box.  This handles cases where uploads arrive with
    ``application/octet-stream``, no MIME type, or URL-only references
    without metadata.
    """
    if image_format and image_format.lower() in ("heic", "heif"):
        return True
    if mime_type and mime_type in ("image/heic", "image/heif"):
        return True
    # URL extension check for URL-backed images without metadata
    if url:
        from urllib.parse import urlparse

        path = urlparse(url).path.lower()
        if path.endswith((".heic", ".heif")):
            return True
    # Magic-byte sniffing: HEIC/HEIF files are ISOBMFF with an ftyp box
    # starting at offset 4, followed by a brand like heic, heix, mif1, etc.
    if image_bytes and len(image_bytes) >= 12:
        if image_bytes[4:8] == b"ftyp":
            brand = image_bytes[8:12].lower()
            if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"heif"):
                return True
    return False


def convert_heic_to_jpeg(
    image_bytes: bytes,
    max_size: int = 10 * 1024 * 1024,
) -> tuple[bytes, str]:
    """Convert HEIC/HEIF bytes to JPEG.

    Applies EXIF orientation so the image is not rotated incorrectly.
    Uses progressive compression (multiple dimension × quality combinations)
    to stay within *max_size* bytes.

    Args:
        image_bytes: Raw HEIC/HEIF bytes.
        max_size: Target output size in bytes (default 10 MB).

    Returns:
        ``(jpeg_bytes, "image/jpeg")``

    Raises:
        ValueError: If the image cannot be compressed below *max_size*.
    """
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    img = Image.open(io.BytesIO(image_bytes))
    # Apply EXIF orientation (iPhone HEIC photos carry rotation metadata)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Progressive compression: 5 dimension levels × 7 quality levels
    # Matches the strategy in compress_image_for_provider (file_processor.py)
    max_dimensions = [4096, 3072, 2048, 1536, 1024]
    quality_levels = [95, 85, 75, 65, 55, 45, 35]

    last_buffer: io.BytesIO | None = None
    for max_dim in max_dimensions:
        resized = img.copy()
        if max(img.size) > max_dim:
            resized.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        for quality in quality_levels:
            last_buffer = io.BytesIO()
            resized.save(last_buffer, format="JPEG", quality=quality, optimize=True)
            if last_buffer.tell() <= max_size:
                return last_buffer.getvalue(), "image/jpeg"

    # All attempts exceeded the limit — raise so callers don't send
    # invalid over-limit payloads to providers
    final_size = last_buffer.tell() if last_buffer else 0
    raise ValueError(
        f"HEIC image could not be compressed to {max_size} bytes "
        f"(best effort: {final_size} bytes after all attempts)"
    )
