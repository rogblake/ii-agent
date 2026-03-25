import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from ii_agent.agent.runtime.media import Image
from ii_agent.agent.runtime.utils.heic import convert_heic_to_jpeg, is_heic_format
from ii_agent.core.logger import logger

# OpenAI image size limit: 10 MB
_OPENAI_IMAGE_LIMIT = 10 * 1024 * 1024


def _process_bytes_image(
    image: bytes,
    image_format: Optional[str] = None,
    image_mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Process bytes image data."""
    # Use provided format or attempt detection, defaulting to JPEG
    if image_format:
        mime_type = f"image/{image_format.lower()}"
    elif image_mime_type:
        mime_type = image_mime_type
    else:
        # Try to detect the image format from the bytes
        try:
            import imghdr

            detected_format = imghdr.what(None, h=image)
            mime_type = f"image/{detected_format}" if detected_format else "image/jpeg"
        except Exception:
            mime_type = "image/jpeg"

    # Convert HEIC/HEIF to JPEG since OpenAI doesn't support them
    if is_heic_format(image_format, mime_type, image_bytes=image):
        try:
            image, mime_type = convert_heic_to_jpeg(image, max_size=_OPENAI_IMAGE_LIMIT)
        except Exception as e:
            logger.error(f"Failed to convert HEIC to JPEG: {e}")
            raise

    base64_image = base64.b64encode(image).decode("utf-8")
    image_url = f"data:{mime_type};base64,{base64_image}"
    return {"type": "input_image", "image_url": image_url}


def _process_image_path(
    image_path: Union[Path, str],
    image_format: Optional[str] = None,
    image_mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Process image ( file path)."""
    # Process local file image
    path = Path(image_path)  # Ensure it's a Path object
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not path.is_file():
        raise IsADirectoryError(f"Image path is not a file: {image_path}")

    # Use caller-provided mime_type, then mimetypes.guess_type, then default
    mime_type = (
        image_mime_type
        or mimetypes.guess_type(path)[0]
        or "image/jpeg"
    )
    # Also derive format from file extension for HEIC detection fallback
    ext_format = image_format or path.suffix.lstrip(".").lower() or None
    try:
        with open(path, "rb") as image_file:
            image_bytes = image_file.read()

            # Convert HEIC/HEIF to JPEG since providers don't support them
            if is_heic_format(image_format=ext_format, mime_type=mime_type, image_bytes=image_bytes):
                image_bytes, mime_type = convert_heic_to_jpeg(image_bytes, max_size=_OPENAI_IMAGE_LIMIT)

            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            image_url = f"data:{mime_type};base64,{base64_image}"
            return {"type": "input_image", "image_url": image_url}
    except Exception as e:
        logger.error(e)
        raise  # Re-raise the exception after logging


def _process_image_url(image_url: str) -> Dict[str, Any]:
    """Process image (base64 or URL)."""

    if image_url.startswith("data:image") or image_url.startswith(
        ("http://", "https://")
    ):
        return {"type": "input_image", "image_url": image_url}
    else:
        raise ValueError("Image URL must start with 'data:image' or 'http(s)://'.")


def process_image(image: Image) -> Optional[Dict[str, Any]]:
    """Process an image based on the format."""
    image_payload: Optional[Dict[str, Any]] = None  # Initialize
    try:
        if image.url is not None:
            # HEIC URLs must be downloaded and converted since OpenAI doesn't support HEIC
            if is_heic_format(image_format=image.format, mime_type=image.mime_type, url=image.url):
                content_bytes = image.get_content_bytes()
                if content_bytes:
                    jpeg_bytes, mime_type = convert_heic_to_jpeg(content_bytes, max_size=_OPENAI_IMAGE_LIMIT)
                    b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                    image_payload = {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{b64}",
                    }
                else:
                    logger.error("Failed to download HEIC image from URL")
                    return None
            else:
                image_payload = _process_image_url(image.url)

        elif image.filepath is not None:
            image_payload = _process_image_path(image.filepath, image.format, image.mime_type)

        elif image.content is not None:
            # Pass format and mime_type from the Image object for HEIC detection
            image_payload = _process_bytes_image(image.content, image.format, image.mime_type)

        else:
            logger(f"Unsupported image format or no data provided: {image}")
            return None

        if image_payload and image.detail:
            image_payload["detail"] = image.detail

        return image_payload

    except (FileNotFoundError, IsADirectoryError, ValueError) as e:
        logger(f"Failed to process image due to invalid input: {str(e)}")
        return None  # Return None for handled validation errors
    except Exception as e:
        logger(f"An unexpected error occurred while processing image: {str(e)}")
        # Depending on policy, you might want to return None or re-raise
        return None  # Return None for unexpected errors as well, preventing crashes




def images_to_message(images: Sequence[Image]) -> List[Dict[str, Any]]:
    """
    Add images to a message for the model. By default, we use the OpenAI image format but other Models
    can override this method to use a different image format.

    Args:
        images: Sequence of images in various formats:
            - str: base64 encoded image, URL, or file path
            - Dict: pre-formatted image data
            - bytes: raw image data

    Returns:
        Message content with images added in the format expected by the model
    """

    # Create a default message content with text
    image_messages: List[Dict[str, Any]] = []

    # Add images to the message content
    for image in images:
        try:
            image_data = process_image(image)
            if image_data:
                image_messages.append(image_data)
        except Exception as e:
            logger.error(f"Failed to process image: {str(e)}")
            continue

    return image_messages
