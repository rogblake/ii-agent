from __future__ import annotations

from typing import Any, Literal

from ii_agent_tools.integrations.fal_ai import (
    FalRunner,
    build_fal_video_payload,
    extract_cost,
    extract_first_media_asset,
    infer_file_name,
    infer_mime_type,
    persist_fal_media_asset,
    resolve_fal_video_application,
)

from .base import BaseVideoGenerationClient, VideoGenerationResult, VideoReferenceImage


class FalVideoGenerationClient(BaseVideoGenerationClient):
    supports_long_generation: bool = True
    supports_extension_api: bool = False

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

    async def generate_video(
        self,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9",
        duration_seconds: int = 5,
        resolution: str = "720p",
        audio_included: bool = False,
        start_frame: str | None = None,
        end_frame: str | None = None,
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        **kwargs: Any,
    ) -> VideoGenerationResult:
        application = model_name or self.model_name
        if not application:
            raise ValueError(
                "fal video generation requires model_name or video_generate_config.fal_model_name"
            )
        provider_payload = kwargs.get("provider_payload")
        source_video_url = (
            (provider_payload or {}).get("video_url")
            if isinstance(provider_payload, dict)
            else None
        )
        application = resolve_fal_video_application(
            application,
            start_frame=start_frame,
            end_frame=end_frame,
            reference_images=[
                image.model_dump(exclude_none=True) for image in reference_images
            ]
            if reference_images
            else None,
            source_video=source_video_url,
        )

        payload = build_fal_video_payload(
            application,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            audio_included=audio_included,
            multishot_mode=kwargs.get("multishot_mode"),
            start_frame=start_frame,
            end_frame=end_frame,
            negative_prompt=negative_prompt,
            person_generation=person_generation,
            seed=seed,
            reference_images=[
                image.model_dump(exclude_none=True) for image in reference_images
            ]
            if reference_images
            else None,
            provider_payload=provider_payload,
        )

        try:
            result = await self.runner.execute(
                application,
                payload,
                request_mode=kwargs.get("request_mode"),
            )
        except Exception as exc:
            raise RuntimeError(f"fal video generation failed: {exc}") from exc

        asset = extract_first_media_asset(
            result,
            preferred_keys=("video", "videos", "output", "outputs"),
        )
        if asset is None:
            return VideoGenerationResult(
                error="fal video generation returned no video asset",
                cost=extract_cost(result),
            )

        mime_type = asset.mime_type or infer_mime_type(asset.url, "video/mp4")
        user_id = kwargs.get("user_id")
        metadata = kwargs.get("metadata") or {}
        if user_id is None and isinstance(metadata, dict):
            user_id = metadata.get("user_id")
        public_url, storage_path, file_name, size = await persist_fal_media_asset(
            asset,
            media_kind="video",
            output_bucket=self.output_bucket,
            project_id=self.project_id,
            user_id=user_id,
            default_mime_type=mime_type,
        )
        return VideoGenerationResult(
            url=public_url,
            mime_type=mime_type,
            size=size,
            cost=extract_cost(result),
            storage_path=storage_path,
            file_name=file_name,
        )
