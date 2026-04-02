from __future__ import annotations

from typing import Any

from ii_agent_tools.integrations.fal_ai import (
    FalRunner,
    build_fal_audio_payload,
    extract_cost,
    extract_first_media_asset,
    infer_file_name,
    infer_mime_type,
)

from .base import AudioGenerationError, AudioGenerationResult, BaseAudioGenerationClient
from .constants import AudioGenerationProvider
from .registry import register_provider


@register_provider(AudioGenerationProvider.FAL.value)
class FalAudioGenerationClient(BaseAudioGenerationClient):
    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
        request_mode: str = "async",
    ):
        self.model_name = model_name
        self.runner = FalRunner(api_key=api_key, default_request_mode=request_mode)

    async def generate_audio(self, prompt: str, **kwargs: Any) -> AudioGenerationResult:
        application = self.model_name
        if not application:
            raise ValueError(
                "fal audio generation requires model_name or audio_generate_config.fal_model_name"
            )

        provider_payload = kwargs.get("provider_payload") or {}
        payload = build_fal_audio_payload(
            application,
            prompt=prompt,
            music_length_ms=kwargs.get("music_length_ms"),
            force_instrumental=kwargs.get("force_instrumental"),
            output_format=kwargs.get("output_format"),
            provider_payload=provider_payload,
            lyrics_prompt=kwargs.get("lyrics_prompt"),
            composition_plan=kwargs.get("composition_plan"),
        )

        try:
            result = await self.runner.execute(
                application,
                payload,
                request_mode=kwargs.get("request_mode"),
            )
        except Exception as exc:
            raise AudioGenerationError(f"fal audio generation failed: {exc}") from exc

        asset = extract_first_media_asset(
            result,
            preferred_keys=(
                "audio",
                "audio_file",
                "audios",
                "music",
                "tracks",
                "output",
            ),
        )
        if asset is None:
            raise AudioGenerationError("fal audio generation returned no audio asset")

        mime_type = asset.mime_type or infer_mime_type(asset.url, "audio/mpeg")
        file_name = asset.file_name or infer_file_name(asset.url)
        return AudioGenerationResult(
            url=asset.url,
            mime_type=mime_type,
            size=asset.size or 0,
            cost=extract_cost(result),
            storage_path=asset.url,
            file_name=file_name,
        )
