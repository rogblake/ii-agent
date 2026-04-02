"""Gemini image preview model integration for slide generation."""

import base64
import hashlib
import mimetypes
import uuid
from datetime import timedelta
from io import BytesIO

import anyio
from google import genai
from google.cloud import storage
from google.genai import types

from ii_agent_tools.integrations.slide_generation.base import (
    BaseSlideGenerationClient,
    SlideGenerationError,
    SlideGenerationResult,
)
from ii_agent_tools.integrations.slide_generation.config import SlideGenerationConfig


class GeminiSlideGenerationClient(BaseSlideGenerationClient):
    """Generates presentation slides as images using Gemini image preview model."""

    # 16:9 aspect ratio for presentations
    DEFAULT_IMAGE_SIZE = "1K"

    SYSTEM_INSTRUCTION = """
Use this tool if no template info is provided. If there's template involved, default to create slide tool

You are a world-class presentation designer and visual storyteller.
Your task is to create a single, visually stunning presentation slide as an image.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY ONE slide image in 16:9 aspect ratio (landscape orientation)
2. The slide must be self-contained and visually complete
3. Use professional design principles: clear hierarchy, balanced composition, readable text
4. Incorporate modern design trends: clean layouts, strategic use of white space
5. Text should be large and readable - minimum 24pt equivalent for body, 48pt+ for titles
6. Use high contrast for text readability
7. Include visual elements that support the content (icons, shapes, images where appropriate)
8. Maintain consistent visual style appropriate for business/educational presentations

DESIGN GUIDELINES:
- Title slides: Bold, centered title with subtitle, clean background
- Content slides: Clear title, organized bullet points or sections, supporting visuals
- Data slides: Clean charts/graphs with clear labels and legends
- Image-heavy slides: High-quality imagery with minimal overlaid text
- Conclusion slides: Memorable key takeaways, call-to-action if relevant

COLOR AND STYLE:
- Use professional color palettes that work for presentations
- Ensure sufficient contrast between text and background
- Apply consistent styling throughout
"""

    def __init__(self, config: SlideGenerationConfig):
        """
        Initialize the Gemini slide generator.

        Args:
            config: Configuration for slide generation
        """
        self.config = config
        if config.gcp_project_id and config.gcp_location:
            self.client = genai.Client(
                vertexai=True,
                project=config.gcp_project_id,
                location=config.gcp_location,
            )
        else:
            self.client = genai.Client(api_key=config.gemini_api_key)

        self.model_name = config.gemini_model_name
        self.custom_domain = config.custom_domain
        self.blob_name_prefix = config.blob_name_prefix

        # Initialize GCS client if bucket is configured
        self.gcs_client = None
        self.bucket = None
        self.bucket_name = config.gcs_output_bucket
        if config.gcs_output_bucket and config.gcp_project_id:
            self.gcs_client = storage.Client(project=config.gcp_project_id)
            self.bucket = self.gcs_client.bucket(config.gcs_output_bucket)

    async def generate_slide(
        self,
        full_prompt: str,
        **kwargs,
    ) -> SlideGenerationResult:
        """
        Generate a single slide as an image.

        Args:
            full_prompt: Complete prompt describing the slide to generate
            **kwargs: Additional arguments (ignored, for compatibility)

        Returns:
            SlideGenerationResult with the generated image URL and metadata
        """
        # Generate the image using Gemini
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=full_prompt)],
            ),
        ]

        generate_config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(
                image_size=self.DEFAULT_IMAGE_SIZE,
            ),
            system_instruction=[
                types.Part.from_text(text=self.SYSTEM_INSTRUCTION),
            ],
        )

        # Stream the response and capture the image
        image_data = None
        image_mime_type = None
        prompt_tokens = 0
        output_tokens = 0

        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=generate_config,
            )

            async for chunk in stream:
                if chunk.usage_metadata:
                    prompt_tokens = chunk.usage_metadata.prompt_token_count or 0
                    output_tokens = chunk.usage_metadata.candidates_token_count or 0

                if (
                    chunk.candidates is None
                    or chunk.candidates[0].content is None
                    or chunk.candidates[0].content.parts is None
                ):
                    continue

                for part in chunk.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        image_data = part.inline_data.data
                        image_mime_type = part.inline_data.mime_type
                        break

                if image_data:
                    break
        except Exception as e:
            raise SlideGenerationError(f"Failed to generate slide image: {e}")

        if not image_data:
            raise SlideGenerationError("Failed to generate slide image - no image data returned")

        cost = self._token_to_cost(prompt_tokens, output_tokens)

        # Upload to GCS and get permanent URL
        result = await self._upload_to_storage(
            image_data=image_data,
            mime_type=image_mime_type or "image/png",
            cost=cost,
        )

        return result

    async def _upload_to_storage(
        self,
        image_data: bytes,
        mime_type: str,
        cost: float,
    ) -> SlideGenerationResult:
        """
        Upload the generated image to GCS storage.

        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            cost: Cost of the generation

        Returns:
            SlideGenerationResult with URL and metadata
        """
        # Generate content hash for deduplication
        content_hash = hashlib.md5(image_data).hexdigest()

        # Determine file extension from MIME type
        extension = mimetypes.guess_extension(mime_type) or ".png"
        if extension == ".jpe":
            extension = ".jpg"

        # Create storage path using blob_name_prefix
        unique_id = str(uuid.uuid4())[:8]
        storage_path = f"{self.blob_name_prefix}/{unique_id}_{content_hash[:8]}{extension}"

        if self.bucket:

            def _upload_sync() -> str:
                blob = self.bucket.blob(storage_path)
                blob.cache_control = "public, max-age=31536000"
                blob.upload_from_file(BytesIO(image_data), content_type=mime_type)
                try:
                    blob.patch()
                except Exception:
                    pass
                try:
                    blob.make_public()
                except Exception:
                    pass  # Continue if already public or permission error
                return blob.public_url

            url = await anyio.to_thread.run_sync(_upload_sync)

            # Generate permanent URL - use custom domain if configured
            if self.custom_domain:
                url = f"https://{self.custom_domain}/{storage_path}"
        else:
            # If no GCS configured, return a base64 data URL (for testing)
            encoded = base64.b64encode(image_data).decode("utf-8")
            url = f"data:{mime_type};base64,{encoded}"

        return SlideGenerationResult(
            url=url,
            mime_type=mime_type,
            size=len(image_data),
            storage_path=storage_path,
            width=1920,
            height=1080,
            cost=cost,
        )

    def get_signed_url(self, storage_path: str, expiration_hours: int = 24) -> str:
        """Get a signed URL for a stored slide image."""
        if not self.bucket:
            raise SlideGenerationError("GCS bucket not configured")

        blob = self.bucket.blob(storage_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=expiration_hours),
            method="GET",
        )

    def _token_to_cost(self, input_tokens_count: int, output_tokens_count: int) -> float:
        return input_tokens_count * 2 / 1_000_000 + output_tokens_count * 12 / 1_000_000
