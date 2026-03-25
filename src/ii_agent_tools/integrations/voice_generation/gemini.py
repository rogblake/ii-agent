import base64
import uuid
import wave
from io import BytesIO
from typing import Any

import anyio
from google import genai
from google.cloud import storage
from google.genai import types

from .base import BaseVoiceGenerationClient, VoiceGenerationError, VoiceGenerationResult
from .config import normalize_language
from .constants import VoiceGenerationProvider
from .pricing import calculate_gemini_tts_cost
from .registry import register_provider

DEFAULT_SAMPLE_RATE = 24000
DEFAULT_SAMPLE_WIDTH = 2
DEFAULT_CHANNELS = 1
DEFAULT_BLOB_NAME_PREFIX = "tmp/voice_generation"

MIME_TO_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/pcm": "pcm",
    "audio/x-pcm": "pcm",
}


@register_provider(VoiceGenerationProvider.GEMINI.value)
class GeminiTtsVoiceGenerationClient(BaseVoiceGenerationClient):
    """Gemini TTS implementation of voice generation."""

    def __init__(
        self,
        api_key: str | None = None,
        project_id: str | None = None,
        location: str | None = None,
        output_bucket: str | None = None,
        default_voice_name: str = "Kore",
        voice_name_by_language: dict[str, str] | None = None,
        model_name: str | None = None,
        blob_name_prefix: str = DEFAULT_BLOB_NAME_PREFIX,
    ):
        if project_id and location:
            self.client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Gemini TTS requires an API key or Vertex AI config")

        self.project_id = project_id
        self.output_bucket = output_bucket
        self.default_voice_name = default_voice_name
        self.voice_name_by_language = voice_name_by_language or {}
        self.model_name = model_name
        self.blob_name_prefix = blob_name_prefix

        if output_bucket and project_id:
            self.bucket = storage.Client(project=project_id).bucket(output_bucket)
        else:
            self.bucket = None

    async def generate_voice(self, text: str, **kwargs: Any) -> VoiceGenerationResult:
        voice_settings = kwargs.get("voice_settings") or {}
        voice_name = (
            voice_settings.get("voice_name")
            or voice_settings.get("prebuilt_voice_name")
            or kwargs.get("voice_id")
        )
        if not voice_name:
            language = kwargs.get("language_code") or kwargs.get("language")
            language_key = normalize_language(language)
            if language_key:
                voice_name = self.voice_name_by_language.get(language_key)
        if not voice_name:
            voice_name = self.default_voice_name

        model_name = kwargs.get("model_name") or self.model_name
        if not model_name:
            raise ValueError("model_name is required for Gemini TTS")

        generate_config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        )

        prompt_tokens = 0
        output_tokens = 0

        try:
            response = await self.client.aio.models.generate_content(
                model=model_name,
                contents=text,
                config=generate_config,
            )
        except Exception as e:
            raise VoiceGenerationError(f"Gemini TTS failed: {e}") from e

        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            prompt_tokens = usage_metadata.prompt_token_count or 0
            output_tokens = usage_metadata.candidates_token_count or 0

        audio_data = self._extract_audio_data(response)
        if not audio_data:
            raise VoiceGenerationError("Gemini TTS returned no audio data")

        wav_bytes = self._pcm_to_wav(
            audio_data,
            sample_rate=DEFAULT_SAMPLE_RATE,
            sample_width=DEFAULT_SAMPLE_WIDTH,
            channels=DEFAULT_CHANNELS,
        )
        content_type = "audio/wav"

        session_id = kwargs.get("session_id")
        metadata = kwargs.get("metadata")
        if session_id is None and isinstance(metadata, dict):
            session_id = metadata.get("session_id")

        if not self.bucket:
            raise VoiceGenerationError("No GCS bucket configured for voice output")

        public_url, storage_path, file_name = await self._upload_bytes(
            wav_bytes,
            content_type,
            session_id=session_id,
        )
        cost = calculate_gemini_tts_cost(
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
        )

        return VoiceGenerationResult(
            url=public_url,
            mime_type=content_type,
            size=len(wav_bytes),
            cost=cost,
            storage_path=storage_path,
            file_name=file_name,
        )

    def _extract_audio_data(self, response: Any) -> bytes | None:
        try:
            candidate = response.candidates[0]
            part = candidate.content.parts[0]
            inline_data = part.inline_data
            if inline_data is None or inline_data.data is None:
                return None
            audio_data = inline_data.data
        except Exception:
            return None

        if isinstance(audio_data, (bytes, bytearray, memoryview)):
            return bytes(audio_data)
        if isinstance(audio_data, str):
            try:
                return base64.b64decode(audio_data)
            except Exception:
                return None
        return None

    def _pcm_to_wav(
        self,
        pcm_data: bytes,
        sample_rate: int,
        sample_width: int,
        channels: int,
    ) -> bytes:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wave_file:
            wave_file.setnchannels(channels)
            wave_file.setsampwidth(sample_width)
            wave_file.setframerate(sample_rate)
            wave_file.writeframes(pcm_data)
        return buffer.getvalue()

    async def _upload_bytes(
        self,
        audio_bytes: bytes,
        content_type: str,
        session_id: str | None = None,
    ) -> tuple[str, str, str]:
        extension = MIME_TO_EXT.get(content_type, "wav")
        file_id = uuid.uuid4().hex
        file_name = f"{file_id}.{extension}"
        if session_id:
            blob_name = f"sessions/{session_id}/generated/{file_name}"
        else:
            blob_name = f"{self.blob_name_prefix}/{file_name}"

        def _upload_sync() -> str:
            blob = self.bucket.blob(blob_name)
            blob.cache_control = "public, max-age=31536000"
            blob.upload_from_file(BytesIO(audio_bytes), content_type=content_type)
            try:
                blob.make_public()
            except Exception:
                pass
            return blob.public_url

        url = await anyio.to_thread.run_sync(_upload_sync)
        return url, blob_name, file_name
