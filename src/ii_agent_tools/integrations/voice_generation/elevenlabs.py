import uuid
from io import BytesIO
from typing import Any

import anyio
from elevenlabs.client import ElevenLabs
from google.cloud import storage

from ii_agent.core.storage.path_resolver import path_resolver
from .base import BaseVoiceGenerationClient, VoiceGenerationError, VoiceGenerationResult
from .config import normalize_language
from .constants import VoiceGenerationProvider
from .pricing import calculate_elevenlabs_cost
from .registry import register_provider

DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_BASE_URL = "https://api.elevenlabs.io"

MIME_TO_EXT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/pcm": "pcm",
    "audio/x-pcm": "pcm",
    "audio/basic": "ulaw",
    "audio/ulaw": "ulaw",
    "audio/x-ulaw": "ulaw",
}


@register_provider(VoiceGenerationProvider.ELEVENLABS.value)
class ElevenLabsVoiceGenerationClient(BaseVoiceGenerationClient):
    """ElevenLabs implementation of voice generation."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        output_bucket: str | None = None,
        project_id: str | None = None,
        default_voice_id: str | None = None,
        voice_id_by_language: dict[str, str] | None = None,
        model_name: str | None = None,
        blob_name_prefix: str = "tmp/voice_generation",
    ):
        if not api_key:
            raise ValueError("ElevenLabs API key is required")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.output_bucket = output_bucket
        self.project_id = project_id
        self.default_voice_id = default_voice_id
        self.voice_id_by_language = voice_id_by_language or {}
        self.model_name = model_name
        self.blob_name_prefix = blob_name_prefix
        self.client = ElevenLabs(api_key=api_key, base_url=self.base_url)

        if output_bucket and project_id:
            self.bucket = storage.Client(project=project_id).bucket(output_bucket)
        else:
            self.bucket = None

    async def generate_voice(self, text: str, **kwargs: Any) -> VoiceGenerationResult:
        voice_id = kwargs.get("voice_id")
        if not voice_id:
            language = kwargs.get("language_code") or kwargs.get("language")
            language_key = normalize_language(language)
            if language_key:
                voice_id = self.voice_id_by_language.get(language_key)
        if not voice_id:
            voice_id = self.default_voice_id
        if not voice_id:
            raise ValueError("voice_id is required for ElevenLabs voice generation")

        model_name = kwargs.get("model_name") or self.model_name
        output_format = kwargs.get("output_format") or DEFAULT_OUTPUT_FORMAT
        convert_kwargs: dict[str, Any] = {
            "text": text,
            "voice_id": voice_id,
            "output_format": output_format,
        }
        if model_name:
            convert_kwargs["model_id"] = model_name

        try:
            audio_bytes = await anyio.to_thread.run_sync(self._convert_sync, convert_kwargs)
        except Exception as e:
            raise VoiceGenerationError(f"ElevenLabs voice generation failed: {e}") from e
        content_type = "audio/mpeg"

        user_id = kwargs.get("user_id")
        metadata = kwargs.get("metadata")
        if user_id is None and isinstance(metadata, dict):
            user_id = metadata.get("user_id")

        if not self.bucket:
            raise VoiceGenerationError("No GCS bucket configured for voice output")

        public_url, storage_path, file_name = await self._upload_bytes(
            audio_bytes,
            content_type,
            user_id=user_id,
        )

        cost = calculate_elevenlabs_cost(
            audio_size_bytes=len(audio_bytes),
            output_format=output_format,
            model_name=model_name,
        )

        return VoiceGenerationResult(
            url=public_url,
            mime_type=content_type,
            size=len(audio_bytes),
            cost=cost,
            storage_path=storage_path,
            file_name=file_name,
        )

    async def _upload_bytes(
        self,
        audio_bytes: bytes,
        content_type: str,
        user_id: uuid.UUID | None = None,
    ) -> tuple[str, str, str]:
        extension = self._guess_extension(content_type)
        file_id = uuid.uuid4().hex
        file_name = f"{file_id}.{extension}"
        blob_name = path_resolver.user_file(user_id, "audio", file_id, extension)

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

    def _convert_sync(self, convert_kwargs: dict[str, Any]) -> bytes:
        audio_data = self.client.text_to_speech.convert(**convert_kwargs)
        return self._collect_audio_bytes(audio_data)

    def _collect_audio_bytes(self, audio_data: Any) -> bytes:
        if isinstance(audio_data, (bytes, bytearray, memoryview)):
            return bytes(audio_data)

        chunks = bytearray()
        for chunk in audio_data:
            if not chunk:
                continue
            if isinstance(chunk, (bytes, bytearray, memoryview)):
                chunks.extend(chunk)
            else:
                raise VoiceGenerationError(f"Unexpected audio chunk type: {type(chunk)}")
        return bytes(chunks)

    def _guess_extension(self, content_type: str) -> str:
        return MIME_TO_EXT.get(content_type, "mp3")
