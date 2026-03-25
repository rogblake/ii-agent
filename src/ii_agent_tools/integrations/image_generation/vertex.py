import asyncio
import datetime
import mimetypes
import uuid
from io import BytesIO
from typing import Any, Literal, List

import httpx

import anyio
from google import genai
from google.cloud import storage
from google.genai import types
from vertexai.preview.vision_models import Image, ImageGenerationModel

from .base import BaseImageGenerationClient, ImageGenerationResult, ImageGenerationError
from .registry import register_provider
from .constants import ImageGenerationProvider
from .pricing import calculate_vertex_imagen_cost, calculate_vertex_genai_cost


IMAGE_MODEL_NAME = "imagen-4.0-generate-001"
SUPPORTED_VERTEX_ASPECT_RATIOS = Literal[
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
    "1:4",
    "4:1",
    "1:8",
    "8:1",
]


@register_provider(ImageGenerationProvider.VERTEX.value)
class VertexImageGenerationClient(BaseImageGenerationClient):
    """Vertex AI implementation of image generation client."""

    def __init__(
        self,
        project_id: str,
        location: str,
        output_bucket: str,
        model_name: str | None = IMAGE_MODEL_NAME,
        result_expiration_seconds: int = 3600,
        blob_name_prefix: str = "tmp/image_generation",
    ):
        """
        Initialize Vertex AI client.

        Args:
            project_id: GCP project ID
            location: GCP location/region
            output_bucket: GCS bucket to store generated images
            model_name: Name of the model to use for image generation
            result_expiration_seconds: Expiration time for the signed URL of the generated image
            blob_name_prefix: Prefix for the blob name of the generated image
        """

        if not project_id or not location or not output_bucket:
            raise ValueError(
                "project_id, location, and output_bucket are required for Vertex image generation"
            )

        self.project_id = project_id
        self.location = location
        self.output_bucket = output_bucket
        self.model_name = model_name or IMAGE_MODEL_NAME

        # Imagen models use the Vertex vision SDK; others go through genai
        self.model = (
            ImageGenerationModel.from_pretrained(self.model_name)
            if self.model_name.startswith("imagen")
            else None
        )

        self.bucket = storage.Client(project=project_id).bucket(output_bucket)
        self.result_expiration_seconds = result_expiration_seconds
        self.blob_name_prefix = blob_name_prefix

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: SUPPORTED_VERTEX_ASPECT_RATIOS = "1:1",
        **kwargs: Any,
    ) -> ImageGenerationResult:
        # Extract provider-specific parameters from kwargs
        image_urls = kwargs.get("image_urls")
        image_size = kwargs.get("image_size", "1K")
        metadata = kwargs.get("metadata", {})
        session_id = metadata.get("session_id")
        background = kwargs.get("background")

        if background:
            prompt = prompt + "\n Background: " + background

        # Route based on whether reference images are provided
        if image_urls:
            # Image-to-image generation
            if self.model and self.model_name.startswith("imagen"):
                return await self._generate_from_images_with_imagen(
                    prompt=prompt,
                    image_urls=image_urls,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    session_id=session_id,
                )
            return await self._generate_from_images_with_genai(
                prompt=prompt,
                image_urls=image_urls,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                session_id=session_id,
            )
        else:
            # Text-to-image generation
            if self.model and self.model_name.startswith("imagen"):
                return await self._generate_with_imagen(
                    prompt, aspect_ratio, session_id
                )
            return await self._generate_with_genai(
                prompt, aspect_ratio, image_size, session_id
            )

    async def _download_image(self, url: str) -> tuple[bytes, str]:
        if url.startswith("gs://"):
            bucket_name, blob_name = url.replace("gs://", "").split("/", 1)
            blob = (
                storage.Client(project=self.project_id)
                .bucket(bucket_name)
                .blob(blob_name)
            )

            def _download_sync() -> tuple[bytes, str]:
                data = blob.download_as_bytes()
                return data, blob.content_type or "image/png"

            return await anyio.to_thread.run_sync(_download_sync)

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "").split(";")[0].strip()
            if not mime_type:
                mime_type = mimetypes.guess_type(url)[0] or "image/png"
            return response.content, mime_type

    async def _generate_from_images_with_genai(
        self,
        prompt: str,
        image_urls: List[str] | None = None,
        aspect_ratio: SUPPORTED_VERTEX_ASPECT_RATIOS = "1:1",
        image_size: str = "1K",
        session_id: str | None = None,
    ) -> ImageGenerationResult:
        """Generate image using Vertex AI API."""
        if not image_urls:
            raise ImageGenerationError(
                "At least one image URL is required for image-to-image generation"
            )

        client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

        image_parts: list[types.Part] = []
        for image_url in image_urls:
            try:
                image_bytes, mime_type = await self._download_image(image_url)
            except Exception as exc:
                raise ImageGenerationError(
                    f"Failed to download image {image_url}: {exc}"
                ) from exc
            image_parts.append(
                types.Part.from_bytes(mime_type=mime_type, data=image_bytes)
            )

        image_parts.append(types.Part.from_text(text=prompt))

        contents = [types.Content(role="user", parts=image_parts)]

        response = await client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
                tools=[types.Tool(googleSearch=types.GoogleSearch())],
            ),
        )

        cost = self._calculate_genai_usage_cost(response.usage_metadata)

        candidate = response.candidates[0]
        if candidate.finish_reason != types.FinishReason.STOP:
            raise ImageGenerationError(
                f"Image generation failed: {candidate.finish_reason}"
            )

        for part in candidate.content.parts:
            image = part.as_image() if hasattr(part, "as_image") else None
            if image:
                image_bytes = image.image_bytes
                url, storage_path, file_name = await self._upload_bytes(
                    image_bytes, session_id
                )
                return ImageGenerationResult(
                    url=url,
                    mime_type=getattr(image, "mime_type", None) or "image/png",
                    size=len(image_bytes),
                    cost=cost,
                    storage_path=storage_path,
                    file_name=file_name,
                )
            if getattr(part, "inline_data", None) and part.inline_data.data:
                image_bytes = part.inline_data.data
                url, storage_path, file_name = await self._upload_bytes(
                    image_bytes, session_id
                )
                return ImageGenerationResult(
                    url=url,
                    mime_type=part.inline_data.mime_type or "image/png",
                    size=len(image_bytes),
                    cost=cost,
                    storage_path=storage_path,
                    file_name=file_name,
                )

        raise ImageGenerationError("No image data returned from genai model")

    async def _generate_with_imagen(
        self, prompt: str, aspect_ratio: str, session_id: str | None = None
    ) -> ImageGenerationResult:
        """Generate image using the Imagen model."""
        # Generate storage path based on session_id
        if session_id:
            file_id = str(uuid.uuid4())
            file_name = f"generated-{file_id[:8]}.png"
            blob_name = f"sessions/{session_id}/generated/{file_name}"
        else:
            file_id = str(uuid.uuid4())
            file_name = f"{file_id}.png"
            blob_name = f"image_generation/{file_name}"

        # Get the directory path for output_gcs_uri (without filename)
        output_dir = "/".join(blob_name.split("/")[:-1])

        generate_params = {
            "number_of_images": 1,
            "language": "en",
            "aspect_ratio": aspect_ratio,
            "person_generation": "allow_all",
            "output_gcs_uri": f"gs://{self.output_bucket}/{output_dir}",
        }

        result = await asyncio.to_thread(
            self.model.generate_images, prompt=prompt, **generate_params
        )

        image_uri = result.images[0]._gcs_uri
        _, actual_blob_name = image_uri.replace("gs://", "").split("/", 1)

        # Make the blob public
        def _make_public() -> str:
            blob = self.bucket.blob(actual_blob_name)
            blob.cache_control = "public, max-age=31536000"
            try:
                blob.make_public()
            except Exception:
                pass
            return blob.public_url

        url = await anyio.to_thread.run_sync(_make_public)

        return ImageGenerationResult(
            url=url,
            mime_type="image/png",
            size=self._get_image_size(actual_blob_name),
            cost=calculate_vertex_imagen_cost(self.model_name),
            storage_path=actual_blob_name,
            file_name=actual_blob_name.split("/")[-1],
        )

    async def _generate_from_images_with_imagen(
        self,
        prompt: str,
        image_urls: List[str],
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        session_id: str | None = None,
    ) -> ImageGenerationResult:
        """Edit/generate image from reference images using Imagen model."""
        if not image_urls:
            raise ImageGenerationError(
                "At least one image URL is required for image-to-image generation"
            )

        # Download the first image as base image for editing
        base_image_bytes, _ = await self._download_image(image_urls[0])
        base_image = Image(image_bytes=base_image_bytes)

        # Generate storage path based on session_id
        if session_id:
            file_id = str(uuid.uuid4())
            file_name = f"generated-{file_id[:8]}.png"
            blob_name = f"sessions/{session_id}/generated/{file_name}"
        else:
            file_id = str(uuid.uuid4())
            file_name = f"{file_id}.png"
            blob_name = f"image_generation/{file_name}"

        # Get the directory path for output_gcs_uri (without filename)
        output_dir = "/".join(blob_name.split("/")[:-1])

        generate_params = {
            "number_of_images": 1,
            "language": "en",
            "aspect_ratio": aspect_ratio,
            "person_generation": "allow_all",
            "output_gcs_uri": f"gs://{self.output_bucket}/{output_dir}",
        }

        result = await asyncio.to_thread(
            self.model._generate_images,
            prompt=prompt,
            base_image=base_image,
            **generate_params,
        )

        image_uri = result.images[0]._gcs_uri
        _, actual_blob_name = image_uri.replace("gs://", "").split("/", 1)

        # Make the blob public
        def _make_public() -> str:
            blob = self.bucket.blob(actual_blob_name)
            blob.cache_control = "public, max-age=31536000"
            try:
                blob.make_public()
            except Exception:
                pass
            return blob.public_url

        url = await anyio.to_thread.run_sync(_make_public)

        return ImageGenerationResult(
            url=url,
            mime_type="image/png",
            size=self._get_image_size(actual_blob_name),
            cost=calculate_vertex_imagen_cost(self.model_name),
            storage_path=actual_blob_name,
            file_name=actual_blob_name.split("/")[-1],
        )

    async def _generate_with_genai(
        self,
        prompt: str,
        aspect_ratio: str,
        image_size: str,
        session_id: str | None = None,
    ) -> ImageGenerationResult:
        """Generate image using genai client (e.g., nano banana)."""
        client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

        response = await client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=genai.types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            ),
        )
        cost = self._calculate_genai_usage_cost(response.usage_metadata)

        candidate = response.candidates[0]
        if candidate.finish_reason != types.FinishReason.STOP:
            raise ImageGenerationError(
                f"Image generation failed: {candidate.finish_reason}"
            )

        for part in candidate.content.parts:
            image = part.as_image()
            if image:
                image_bytes = image.image_bytes
                url, storage_path, file_name = await self._upload_bytes(
                    image_bytes, session_id
                )
                return ImageGenerationResult(
                    url=url,
                    mime_type="image/png",
                    size=len(image_bytes),
                    cost=cost,
                    storage_path=storage_path,
                    file_name=file_name,
                )

        raise ImageGenerationError("No image data returned from genai model")

    async def _upload_bytes(
        self, image_bytes: bytes, session_id: str | None = None
    ) -> tuple[str, str, str]:
        """Upload image bytes to GCS and return (public_url, storage_path, file_name)."""
        # Use session-based path if session_id is provided, otherwise fallback to image_generation
        if session_id:
            file_id = str(uuid.uuid4())
            file_name = f"generated-{file_id[:8]}.png"
            blob_name = f"sessions/{session_id}/generated/{file_name}"
        else:
            file_id = str(uuid.uuid4())
            file_name = f"{file_id}.png"
            blob_name = f"image_generation/{file_name}"

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

    def _get_signed_url(self, blob_name: str) -> str:
        blob = self.bucket.blob(blob_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=self.result_expiration_seconds),
            method="GET",
        )

    def _get_image_size(self, blob_name: str) -> int:
        blob = self.bucket.get_blob(blob_name)
        return blob.size

    def _get_image_mime_type(self, blob_name: str) -> str:
        blob = self.bucket.get_blob(blob_name)
        return blob.content_type

    def _token_to_cost(
        self, input_tokens_count: int, output_tokens_count: int
    ) -> float:
        """Calculate cost for GenAI models.

        Pricing is now configured in pricing.py - see that file to add new models.
        """
        return calculate_vertex_genai_cost(
            model_name=self.model_name,
            input_tokens=input_tokens_count,
            output_tokens=output_tokens_count,
        )

    @staticmethod
    def _usage_token_counts(
        token_details: list[types.ModalityTokenCount] | None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for detail in token_details or []:
            if detail is None:
                continue

            modality = getattr(detail, "modality", None)
            token_count = getattr(detail, "token_count", None) or 0
            if not modality or token_count <= 0:
                continue

            modality_key = getattr(modality, "value", str(modality))
            counts[modality_key] = counts.get(modality_key, 0) + token_count

        return counts

    def _calculate_genai_usage_cost(
        self,
        usage_metadata: types.GenerateContentResponseUsageMetadata | None,
    ) -> float:
        if usage_metadata is None:
            return 0.0

        prompt_counts = self._usage_token_counts(usage_metadata.prompt_tokens_details)
        candidate_counts = self._usage_token_counts(
            usage_metadata.candidates_tokens_details
        )

        prompt_token_count = usage_metadata.prompt_token_count or 0
        candidate_token_count = usage_metadata.candidates_token_count
        if candidate_token_count is None:
            total_token_count = usage_metadata.total_token_count or 0
            candidate_token_count = max(
                total_token_count
                - prompt_token_count
                - (usage_metadata.tool_use_prompt_token_count or 0)
                - (usage_metadata.thoughts_token_count or 0),
                0,
            )

        return calculate_vertex_genai_cost(
            self.model_name,
            input_text_tokens=prompt_counts.get("TEXT", 0),
            output_text_tokens=candidate_counts.get("TEXT", 0),
            input_image_tokens=prompt_counts.get("IMAGE", 0),
            output_image_tokens=candidate_counts.get("IMAGE", 0),
            fallback_input_tokens=prompt_token_count,
            fallback_output_tokens=candidate_token_count or 0,
        )
