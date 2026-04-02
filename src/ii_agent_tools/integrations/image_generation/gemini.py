import datetime
import mimetypes
import uuid
from io import BytesIO
from typing import Any, Literal, List

import anyio
import httpx
from google import genai
from google.cloud import storage
from google.genai import types

from ii_agent.core.storage.path_resolver import path_resolver
from .base import BaseImageGenerationClient, ImageGenerationError, ImageGenerationResult
from .constants import ImageGenerationProvider
from .pricing import calculate_vertex_genai_cost
from .registry import register_provider

IMAGE_MODEL_NAME = "gemini-3.1-flash-image-preview"
SUPPORTED_GEMINI_ASPECT_RATIOS = Literal[
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


@register_provider(ImageGenerationProvider.GEMINI.value)
class GeminiImageGenerationClient(BaseImageGenerationClient):
    """Gemini API implementation of image generation client."""

    def __init__(
        self,
        api_key: str | None,
        output_bucket: str | None,
        project_id: str | None = None,
        model_name: str | None = IMAGE_MODEL_NAME,
        result_expiration_seconds: int = 3600,
        blob_name_prefix: str = "tmp/image_generation",
    ):
        if not api_key:
            raise ValueError("Gemini image generation requires GEMINI_API_KEY")
        if not output_bucket:
            raise ValueError("output_bucket is required for Gemini image generation")

        self.api_key = api_key
        self.project_id = project_id
        self.output_bucket = output_bucket
        self.model_name = model_name or IMAGE_MODEL_NAME
        self.client = genai.Client(api_key=api_key)
        self.bucket = self._create_storage_client().bucket(output_bucket)
        self.result_expiration_seconds = result_expiration_seconds
        self.blob_name_prefix = blob_name_prefix

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: SUPPORTED_GEMINI_ASPECT_RATIOS = "1:1",
        **kwargs: Any,
    ) -> ImageGenerationResult:
        image_urls = kwargs.get("image_urls")
        image_size = kwargs.get("image_size", "1K")
        metadata = kwargs.get("metadata", {})
        user_id = kwargs.get("user_id") or metadata.get("user_id")
        background = kwargs.get("background")

        if background:
            prompt = prompt + "\n Background: " + background

        if image_urls:
            return await self._generate_from_images(
                prompt=prompt,
                image_urls=image_urls,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                user_id=user_id,
            )

        return await self._generate_without_images(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            user_id=user_id,
        )

    async def _download_image(self, url: str) -> tuple[bytes, str]:
        if url.startswith("gs://"):
            bucket_name, blob_name = url.replace("gs://", "").split("/", 1)
            blob = self._create_storage_client().bucket(bucket_name).blob(blob_name)

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

    async def _generate_from_images(
        self,
        prompt: str,
        image_urls: List[str],
        aspect_ratio: SUPPORTED_GEMINI_ASPECT_RATIOS = "1:1",
        image_size: str = "1K",
        user_id: uuid.UUID | None = None,
    ) -> ImageGenerationResult:
        if not image_urls:
            raise ImageGenerationError(
                "At least one image URL is required for image-to-image generation"
            )

        image_parts: list[types.Part] = []
        for image_url in image_urls:
            try:
                image_bytes, mime_type = await self._download_image(image_url)
            except Exception as exc:
                raise ImageGenerationError(f"Failed to download image {image_url}: {exc}") from exc
            image_parts.append(types.Part.from_bytes(mime_type=mime_type, data=image_bytes))

        image_parts.append(types.Part.from_text(text=prompt))
        contents = [types.Content(role="user", parts=image_parts)]

        response = await self.client.aio.models.generate_content(
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
        return await self._response_to_result(response, user_id)

    async def _generate_without_images(
        self,
        prompt: str,
        aspect_ratio: str,
        image_size: str,
        user_id: uuid.UUID | None = None,
    ) -> ImageGenerationResult:
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            ),
        )
        return await self._response_to_result(response, user_id)

    async def _response_to_result(
        self,
        response: types.GenerateContentResponse,
        user_id: uuid.UUID | None = None,
    ) -> ImageGenerationResult:
        cost = self._calculate_genai_usage_cost(response.usage_metadata)

        candidate = response.candidates[0]
        if candidate.finish_reason != types.FinishReason.STOP:
            raise ImageGenerationError(f"Image generation failed: {candidate.finish_reason}")

        for part in candidate.content.parts:
            image = part.as_image() if hasattr(part, "as_image") else None
            if image:
                image_bytes = image.image_bytes
                url, storage_path, file_name = await self._upload_bytes(image_bytes, user_id)
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
                url, storage_path, file_name = await self._upload_bytes(image_bytes, user_id)
                return ImageGenerationResult(
                    url=url,
                    mime_type=part.inline_data.mime_type or "image/png",
                    size=len(image_bytes),
                    cost=cost,
                    storage_path=storage_path,
                    file_name=file_name,
                )

        raise ImageGenerationError("No image data returned from Gemini model")

    async def _upload_bytes(self, image_bytes: bytes, user_id: uuid.UUID) -> tuple[str, str, str]:
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
        candidate_counts = self._usage_token_counts(usage_metadata.candidates_tokens_details)

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

    def _create_storage_client(self) -> storage.Client:
        if self.project_id:
            return storage.Client(project=self.project_id)
        return storage.Client()
