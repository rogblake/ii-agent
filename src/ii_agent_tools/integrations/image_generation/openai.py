import base64
import mimetypes
import uuid
from io import BytesIO
from typing import Any, Literal, List

import anyio
import httpx
from google.cloud import storage
from openai import AsyncOpenAI

from ii_agent.core.storage.path_resolver import path_resolver
from .base import BaseImageGenerationClient, ImageGenerationResult, ImageGenerationError
from .registry import register_provider
from .constants import ImageGenerationProvider
from .pricing import calculate_openai_cost

OPENAI_IMAGE_MODEL = "gpt-image-1.5"

# Mapping aspect ratio to OpenAI size format
ASPECT_RATIO_TO_SIZE = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}


@register_provider(ImageGenerationProvider.OPENAI.value)
class OpenAIImageGenerationClient(BaseImageGenerationClient):
    """OpenAI implementation of image generation client using gpt-image-1.5."""

    def __init__(
        self,
        api_key: str,
        output_bucket: str | None = None,
        project_id: str | None = None,
        model_name: str | None = OPENAI_IMAGE_MODEL,
        result_expiration_seconds: int = 3600,
        blob_name_prefix: str = "tmp/image_generation",
    ):
        """
        Initialize OpenAI image generation client.

        Args:
            api_key: OpenAI API key
            output_bucket: GCS bucket to store generated images (optional)
            project_id: GCP project ID for GCS (optional, required if output_bucket is set)
            model_name: Name of the model to use (default: gpt-image-1.5)
            result_expiration_seconds: Expiration time for signed URLs
            blob_name_prefix: Prefix for the blob name of the generated image
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")

        self.api_key = api_key
        self.output_bucket = output_bucket
        self.project_id = project_id
        self.model_name = model_name or OPENAI_IMAGE_MODEL
        self.result_expiration_seconds = result_expiration_seconds
        self.blob_name_prefix = blob_name_prefix

        self.client = AsyncOpenAI(api_key=api_key)

        if output_bucket and project_id:
            self.bucket = storage.Client(project=project_id).bucket(output_bucket)
        else:
            self.bucket = None

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal["1:1", "2:3", "3:2"] = "1:1",
        **kwargs: Any,
    ) -> ImageGenerationResult:
        # Extract provider-specific parameters from kwargs
        image_urls = kwargs.get("image_urls")
        image_size = kwargs.get("image_size")
        metadata = kwargs.get("metadata", {})
        user_id = kwargs.get("user_id") or metadata.get("user_id")
        background = kwargs.get("background")

        # Route to appropriate method based on whether reference images are provided
        if image_urls:
            return await self._generate_with_images(
                prompt=prompt,
                image_urls=image_urls,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                user_id=user_id,
                background=background,
            )
        else:
            return await self._generate_without_images(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                user_id=user_id,
                background=background,
            )

    async def _generate_without_images(
        self,
        prompt: str,
        aspect_ratio: Literal["1:1", "2:3", "3:2"] = "1:1",
        image_size: str | None = None,
        user_id: uuid.UUID | None = None,
        background: Literal["transparent", "opaque", "auto"] | None = None,
        **kwargs: Any,
    ) -> ImageGenerationResult:
        size = ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1024")

        try:
            response = await self.client.images.generate(
                model=self.model_name,
                prompt=prompt,
                n=1,
                size=size,
                quality="high",
                background=background,
            )
        except Exception as e:
            raise ImageGenerationError(f"OpenAI image generation failed: {e}") from e

        image_data = response.data[0]

        # Get base64 data and decode
        if image_data.b64_json:
            image_bytes = base64.b64decode(image_data.b64_json)
        elif image_data.url:
            # If URL is returned, we need to download the image
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as http_client:
                resp = await http_client.get(image_data.url)
                resp.raise_for_status()
                image_bytes = resp.content
        else:
            raise ImageGenerationError("No image data returned from OpenAI API")

        # Upload to GCS if bucket is configured
        storage_path = None
        file_name = None
        if self.bucket:
            url, storage_path, file_name = await self._upload_bytes(image_bytes, user_id)
        elif image_data.url:
            url = image_data.url
        else:
            raise ImageGenerationError(
                "No GCS bucket configured and no URL returned from OpenAI API"
            )

        # Calculate cost based on usage (if available)
        cost = self._token_to_cost(response)

        return ImageGenerationResult(
            url=url,
            mime_type="image/png",
            size=len(image_bytes),
            cost=cost,
            storage_path=storage_path or url,
            file_name=file_name,
        )

    async def _download_image(self, url: str) -> tuple[bytes, str]:
        """Download image from URL (supports GCS and HTTP URLs)."""
        if url.startswith("gs://"):
            bucket_name, blob_name = url.replace("gs://", "").split("/", 1)
            blob = storage.Client(project=self.project_id).bucket(bucket_name).blob(blob_name)

            def _download_sync() -> tuple[bytes, str]:
                data = blob.download_as_bytes()
                return data, blob.content_type or "image/png"

            return await anyio.to_thread.run_sync(_download_sync)

        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "").split(";")[0].strip()
            if not mime_type:
                mime_type = mimetypes.guess_type(url)[0] or "image/png"
            return response.content, mime_type

    def _get_file_extension(self, mime_type: str) -> str:
        """Get file extension from mime type."""
        mime_to_ext = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/webp": "webp",
        }
        return mime_to_ext.get(mime_type, "png")

    async def _generate_with_images(
        self,
        prompt: str,
        image_urls: List[str],
        aspect_ratio: Literal["1:1", "2:3", "3:2"] = "1:1",
        image_size: str | None = None,
        user_id: uuid.UUID | None = None,
        background: Literal["transparent", "opaque", "auto"] | None = None,
        **kwargs: Any,
    ) -> ImageGenerationResult:
        if not image_urls:
            raise ImageGenerationError("At least one image URL is required for image editing")

        size = ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1024")

        # Download images from URLs and create file tuples with proper mime types
        image_files: List[tuple[str, bytes, str]] = []
        for idx, image_url in enumerate(image_urls):
            try:
                image_bytes, mime_type = await self._download_image(image_url)
                # Create tuple (filename, bytes, mime_type) for OpenAI API
                ext = self._get_file_extension(mime_type)
                filename = f"image_{idx}.{ext}"
                image_files.append((filename, image_bytes, mime_type))
            except Exception as e:
                raise ImageGenerationError(f"Failed to download image {image_url}: {e}") from e

        try:
            # Use images.edit API with image files as tuples
            response = await self.client.images.edit(
                model=self.model_name,
                image=image_files,
                prompt=prompt,
                n=1,
                size=size,
                quality="high",
                background=background,
            )
        except Exception as e:
            raise ImageGenerationError(f"OpenAI image edit failed: {e}") from e

        image_data = response.data[0]

        # GPT image models always return base64-encoded images
        if image_data.b64_json:
            result_image_bytes = base64.b64decode(image_data.b64_json)
        elif image_data.url:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as http_client:
                resp = await http_client.get(image_data.url)
                resp.raise_for_status()
                result_image_bytes = resp.content
        else:
            raise ImageGenerationError("No image data returned from OpenAI API")

        # Upload to GCS if bucket is configured
        storage_path = None
        file_name = None
        if self.bucket:
            url, storage_path, file_name = await self._upload_bytes(result_image_bytes, user_id)
        elif image_data.url:
            url = image_data.url
        else:
            raise ImageGenerationError(
                "No GCS bucket configured and no URL returned from OpenAI API"
            )

        # Calculate cost based on usage (if available)
        cost = self._token_to_cost(response)

        return ImageGenerationResult(
            url=url,
            mime_type="image/png",
            size=len(result_image_bytes),
            cost=cost,
            storage_path=storage_path or url,
            file_name=file_name,
        )

    async def _upload_bytes(self, image_bytes: bytes, user_id: uuid.UUID) -> tuple[str, str, str]:
        """Upload image bytes to GCS and return (public_url, storage_path, file_name)."""
        file_id = str(uuid.uuid4())
        file_name = f"{file_id}.png"
        blob_name = path_resolver.user_file(user_id, "image", file_id, "png")

        def _upload_sync() -> str:
            blob = self.bucket.blob(blob_name)
            blob.cache_control = "public, max-age=31536000"
            blob.upload_from_file(BytesIO(image_bytes), content_type="image/png")
            try:
                blob.make_public()
            except Exception:
                pass
            return blob.public_url

        url = await anyio.to_thread.run_sync(_upload_sync)
        return url, blob_name, file_name

    def _token_to_cost(self, response) -> float:
        """Calculate cost based on OpenAI response usage.

        Pricing is now configured in pricing.py - see that file to add new models.
        """
        if not hasattr(response, "usage") or response.usage is None:
            return 0.0

        usage = response.usage

        # Get token details
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)

        # Input tokens
        input_text_tokens = getattr(input_details, "text_tokens", 0) if input_details else 0
        input_image_tokens = getattr(input_details, "image_tokens", 0) if input_details else 0

        # Output tokens - output_tokens_details is a dict
        if output_details and isinstance(output_details, dict):
            output_text_tokens = output_details.get("text_tokens", 0)
            output_image_tokens = output_details.get("image_tokens", 0)
        else:
            output_text_tokens = 0
            output_image_tokens = 0

        # Use centralized pricing configuration
        return calculate_openai_cost(
            model_name=self.model_name,
            input_text_tokens=input_text_tokens,
            output_text_tokens=output_text_tokens,
            input_image_tokens=input_image_tokens,
            output_image_tokens=output_image_tokens,
        )
