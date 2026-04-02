from __future__ import annotations

from typing import Any

from ii_agent_tools.integrations.fal_ai import (
    FalRunner,
    build_fal_voice_payload,
    extract_cost,
    extract_first_media_asset,
    infer_file_name,
    infer_mime_type,
)

from .base import BaseVoiceGenerationClient, VoiceGenerationError, VoiceGenerationResult
from .constants import VoiceGenerationProvider
from .registry import register_provider


@register_provider(VoiceGenerationProvider.FAL.value)
class FalVoiceGenerationClient(BaseVoiceGenerationClient):
    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
        request_mode: str = "async",
    ):
        self.model_name = model_name
        self.runner = FalRunner(api_key=api_key, default_request_mode=request_mode)

    async def generate_voice(self, text: str, **kwargs: Any) -> VoiceGenerationResult:
        application = self.model_name
        if not application:
            raise ValueError(
                "fal voice generation requires model_name or voice_generate_config.fal_model_name"
            )

        provider_payload = kwargs.get("provider_payload") or {}
        payload = build_fal_voice_payload(
            application,
            text=text,
            voice_id=kwargs.get("voice_id"),
            language_code=kwargs.get("language_code"),
            output_format=kwargs.get("output_format"),
            voice_settings=kwargs.get("voice_settings"),
            provider_payload=provider_payload,
        )

        try:
            result = await self.runner.execute(
                application,
                payload,
                request_mode=kwargs.get("request_mode"),
            )
        except Exception as exc:
            raise VoiceGenerationError(f"fal voice generation failed: {exc}") from exc

        asset = extract_first_media_asset(
            result,
            preferred_keys=(
                "audio",
                "audio_file",
                "audios",
                "voice",
                "voices",
                "output",
            ),
        )
        if asset is None:
            raise VoiceGenerationError("fal voice generation returned no audio asset")

        mime_type = asset.mime_type or infer_mime_type(asset.url, "audio/mpeg")
        file_name = asset.file_name or infer_file_name(asset.url)
        return VoiceGenerationResult(
            url=asset.url,
            mime_type=mime_type,
            size=asset.size or 0,
            cost=extract_cost(result),
            storage_path=asset.url,
            file_name=file_name,
        )
