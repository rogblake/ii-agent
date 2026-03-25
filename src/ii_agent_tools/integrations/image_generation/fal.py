from __future__ import annotations

from typing import Any, Literal

from ii_agent_tools.integrations.fal_ai import (
    FalRunner,
    build_fal_image_payload,
    extract_cost,
    extract_first_media_asset,
    infer_file_name,
    infer_mime_type,
    persist_fal_media_asset,
    resolve_fal_image_application,
)

from .base import BaseImageGenerationClient, ImageGenerationError, ImageGenerationResult
from .constants import ImageGenerationProvider
from .registry import register_provider


@register_provider(ImageGenerationProvider.FAL.value)
class FalImageGenerationClient(BaseImageGenerationClient):
    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
        request_mode: str = "async",
        output_bucket: str | None = None,
        project_id: str | None = None,
    ):
        self.model_name = model_name
        self.runner = FalRunner(api_key=api_key, default_request_mode=request_mode)
        self.output_bucket = output_bucket
        self.project_id = project_id

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal[
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
        ] = "1:1",
        **kwargs: Any,
    ) -> ImageGenerationResult:
        application = self.model_name
        if not application:
            raise ValueError(
                "fal image generation requires model_name or image_generate_config.fal_model_name"
            )
        application = resolve_fal_image_application(
            application,
            image_urls=kwargs.get("image_urls"),
            provider_payload=kwargs.get("provider_payload"),
        )

        payload = build_fal_image_payload(
            application,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=kwargs.get("image_size"),
            background=kwargs.get("background"),
            image_urls=kwargs.get("image_urls"),
            provider_payload=kwargs.get("provider_payload"),
        )

        try:
            result = await self.runner.execute(
                application,
                payload,
                request_mode=kwargs.get("request_mode"),
            )
        except Exception as exc:
            raise ImageGenerationError(f"fal image generation failed: {exc}") from exc

        asset = extract_first_media_asset(result, preferred_keys=("images", "image"))
        if asset is None:
            raise ImageGenerationError("fal image generation returned no image asset")

        mime_type = asset.mime_type or infer_mime_type(asset.url, "image/png")
        session_id = kwargs.get("session_id")
        metadata = kwargs.get("metadata") or {}
        if session_id is None and isinstance(metadata, dict):
            session_id = metadata.get("session_id")
        public_url, storage_path, file_name, size = await persist_fal_media_asset(
            asset,
            media_kind="image",
            output_bucket=self.output_bucket,
            project_id=self.project_id,
            session_id=session_id,
            default_mime_type=mime_type,
        )
        return ImageGenerationResult(
            url=public_url,
            mime_type=mime_type,
            size=size,
            cost=extract_cost(result),
            storage_path=storage_path,
            file_name=file_name,
        )
