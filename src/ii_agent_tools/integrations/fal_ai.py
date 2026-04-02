from __future__ import annotations

import mimetypes
import uuid
from io import BytesIO
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import anyio
import fal_client
import httpx
from google.cloud import storage

from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)

_SYNC_REQUEST_MODES = {"sync", "subscribe"}
_ASYNC_REQUEST_MODES = {"async", "submit", "submit_async", "queue"}
_MEDIA_URL_KEYS = ("url", "file_url", "image_url", "video_url", "audio_url")
_MIME_KEYS = ("mime_type", "content_type", "contentType", "type")
_SIZE_KEYS = ("size", "file_size", "content_length", "contentLength", "bytes")
_FAL_PROVIDER_VALUES = {"fal", "fal-ai", "fal_ai"}
_FAL_MODEL_PREFIXES = ("fal-ai/", "xai/")
_FLUX_IMAGE_MODELS = {
    "fal-ai/flux-2-max",
}
_FLUX_IMAGE_EDIT_MODELS = {
    "fal-ai/flux-2-max/edit",
}
_SEEDREAM_IMAGE_MODELS = {
    "fal-ai/bytedance/seedream/v4.5/text-to-image",
}
_SEEDREAM_IMAGE_EDIT_MODELS = {
    "fal-ai/bytedance/seedream/v4.5/edit",
}
_QWEN_IMAGE_MODELS = {
    "fal-ai/qwen-image-2/pro/text-to-image",
}
_QWEN_IMAGE_EDIT_MODELS = {
    "fal-ai/qwen-image-2/pro/edit",
}
_GROK_IMAGE_MODELS = {
    "xai/grok-imagine-image",
}
_GROK_IMAGE_EDIT_MODELS = {
    "xai/grok-imagine-image/edit",
}
_IMAGE_TO_EDIT_MODEL_MAP = {
    "fal-ai/flux-2-max": "fal-ai/flux-2-max/edit",
    "fal-ai/bytedance/seedream/v4.5/text-to-image": "fal-ai/bytedance/seedream/v4.5/edit",
    "fal-ai/qwen-image-2/pro/text-to-image": "fal-ai/qwen-image-2/pro/edit",
    "xai/grok-imagine-image": "xai/grok-imagine-image/edit",
}
_KLING_VIDEO_MODELS = {
    "fal-ai/kling-video/o3/pro/text-to-video",
}
_KLING_VIDEO_REFERENCE_MODELS = {
    "fal-ai/kling-video/o3/pro/reference-to-video",
}
_KLING_VIDEO_V2V_REFERENCE_MODELS = {
    "fal-ai/kling-video/o3/pro/video-to-video/reference",
}
_KLING_VIDEO_IMAGE_MODELS = _KLING_VIDEO_REFERENCE_MODELS
_KLING_VIDEO_ALL_MODELS = (
    _KLING_VIDEO_MODELS | _KLING_VIDEO_REFERENCE_MODELS | _KLING_VIDEO_V2V_REFERENCE_MODELS
)
_SEEDANCE_VIDEO_MODELS = {
    "fal-ai/bytedance/seedance/v1.5/pro/text-to-video",
}
_SEEDANCE_VIDEO_IMAGE_MODELS = {
    "fal-ai/bytedance/seedance/v1.5/pro/image-to-video",
}
_GROK_VIDEO_MODELS = {
    "xai/grok-imagine-video/text-to-video",
}
_GROK_VIDEO_IMAGE_MODELS = {
    "xai/grok-imagine-video/image-to-video",
}
_GROK_VIDEO_EDIT_MODELS = {
    "xai/grok-imagine-video/edit-video",
}
_GROK_VIDEO_TEXT_AND_IMAGE_MODELS = _GROK_VIDEO_MODELS | _GROK_VIDEO_IMAGE_MODELS
_SORA_VIDEO_MODELS = {
    "fal-ai/sora-2/text-to-video/pro",
}
_SORA_VIDEO_IMAGE_MODELS = {
    "fal-ai/sora-2/image-to-video/pro",
}
_SORA_VIDEO_ALL_MODELS = _SORA_VIDEO_MODELS | _SORA_VIDEO_IMAGE_MODELS
_SORA_VIDEO_ASPECT_RATIOS = ("16:9", "9:16")
_SORA_VIDEO_RESOLUTIONS = ("720p", "1080p", "true_1080p")
_SORA_VIDEO_DURATIONS = (4, 8, 12, 16, 20)
_GROK_VIDEO_ASPECT_RATIOS = (
    "16:9",
    "4:3",
    "3:2",
    "1:1",
    "2:3",
    "3:4",
    "9:16",
)
_ELEVENLABS_TTS_MODELS = {
    "fal-ai/elevenlabs/tts/eleven-v3",
}
_MINIMAX_SPEECH_MODELS = {
    "fal-ai/minimax/speech-2.8-hd",
}
_ELEVENLABS_MUSIC_MODELS = {
    "fal-ai/elevenlabs/music",
}
_MINIMAX_MUSIC_MODELS = {
    "fal-ai/minimax-music/v2",
}
_MINIMAX_ALLOWED_EMOTIONS = {
    "neutral",
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
}
_MINIMAX_EMOTION_ALIASES = {
    "calm": "neutral",
    "warm": "neutral",
    "warmth": "neutral",
    "dramatic": "neutral",
    "passionate": "neutral",
    "conversational": "neutral",
    "narration": "neutral",
    "natural": "neutral",
    "energetic": "happy",
}
_IMAGE_SIZE_BY_ASPECT_RATIO = {
    "1:1": "square_hd",
    "2:3": "portrait_4_3",
    "3:4": "portrait_4_3",
    "4:5": "portrait_4_3",
    "9:16": "portrait_16_9",
    "1:4": "portrait_16_9",
    "1:8": "portrait_16_9",
    "3:2": "landscape_4_3",
    "4:3": "landscape_4_3",
    "5:4": "landscape_4_3",
    "16:9": "landscape_16_9",
    "21:9": "landscape_16_9",
    "4:1": "landscape_16_9",
    "8:1": "landscape_16_9",
}
_EXTENSION_BY_MIME_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
}


@dataclass(slots=True)
class FalMediaAsset:
    url: str
    mime_type: str | None = None
    size: int | None = None
    file_name: str | None = None


def is_fal_provider_or_model(
    provider: str | None,
    model_name: str | None = None,
) -> bool:
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider in _FAL_PROVIDER_VALUES:
        return True

    normalized_model_name = (model_name or "").strip().lower()
    return normalized_model_name.startswith(_FAL_MODEL_PREFIXES)


def build_fal_image_payload(
    application: str,
    *,
    prompt: str,
    aspect_ratio: str,
    image_size: str | None = None,
    background: str | None = None,
    image_urls: Sequence[str] | None = None,
    provider_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_application = application.strip().lower()
    reference_image_urls = _normalize_reference_image_urls(
        image_urls,
        provider_payload=provider_payload,
    )

    if provider_payload:
        payload = dict(provider_payload)
        payload.setdefault("prompt", prompt)
        return payload

    if normalized_application in _FLUX_IMAGE_MODELS:
        return _build_flux_image_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )

    if normalized_application in _FLUX_IMAGE_EDIT_MODELS:
        return _build_flux_image_edit_payload(
            application=application,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            image_urls=reference_image_urls,
        )

    if normalized_application in _SEEDREAM_IMAGE_MODELS:
        return _build_seedream_image_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )

    if normalized_application in _SEEDREAM_IMAGE_EDIT_MODELS:
        return merge_payload(
            _build_seedream_image_payload(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
            {
                "image_urls": _require_reference_image_urls(
                    application,
                    reference_image_urls,
                )
            },
        )

    if normalized_application in _QWEN_IMAGE_MODELS:
        return _build_qwen_image_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )

    if normalized_application in _QWEN_IMAGE_EDIT_MODELS:
        return merge_payload(
            _build_qwen_image_payload(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
            {
                "image_urls": _require_reference_image_urls(
                    application,
                    reference_image_urls,
                )
            },
        )

    if normalized_application in _GROK_IMAGE_MODELS:
        return _build_grok_image_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
        )

    if normalized_application in _GROK_IMAGE_EDIT_MODELS:
        return {
            "prompt": prompt,
            "image_urls": _require_reference_image_urls(
                application,
                reference_image_urls,
            ),
        }

    return merge_payload(
        {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "background": background,
        },
        {"image_urls": image_urls} if image_urls else None,
    )


def build_fal_video_payload(
    application: str,
    *,
    prompt: str,
    aspect_ratio: str,
    duration_seconds: int,
    resolution: str,
    audio_included: bool,
    multishot_mode: bool | None = None,
    start_frame: str | None = None,
    end_frame: str | None = None,
    negative_prompt: str | None = None,
    person_generation: str | None = None,
    seed: int | None = None,
    reference_images: Sequence[Mapping[str, Any]] | None = None,
    provider_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_application = application.strip().lower()
    reference_image_urls = _normalize_video_reference_image_urls(reference_images)
    primary_reference_image_url = reference_image_urls[0] if reference_image_urls else None

    if normalized_application in _GROK_VIDEO_TEXT_AND_IMAGE_MODELS:
        allow_auto_aspect_ratio = normalized_application in _GROK_VIDEO_IMAGE_MODELS
        payload = {
            "prompt": prompt,
            "aspect_ratio": _normalize_grok_video_aspect_ratio(
                aspect_ratio,
                allow_auto=allow_auto_aspect_ratio,
            ),
            "duration": str(max(1, min(15, int(duration_seconds)))),
            "resolution": _normalize_grok_video_resolution(
                resolution,
                default="720p",
                allow_auto=False,
            ),
        }
        if normalized_application in _GROK_VIDEO_IMAGE_MODELS:
            payload["image_url"] = _resolve_grok_input_image_url(
                application,
                start_frame=start_frame,
                primary_reference_image_url=primary_reference_image_url,
                provider_payload=provider_payload,
            )
        return merge_payload(payload, provider_payload)

    if normalized_application in _GROK_VIDEO_EDIT_MODELS:
        resolved_video_url = _require_grok_video_source_url(
            application,
            provider_payload,
        )
        provider_resolution = None
        if provider_payload:
            provider_resolution = provider_payload.get("resolution")
        resolution_input = provider_resolution if provider_resolution is not None else resolution
        return {
            "prompt": prompt,
            "video_url": resolved_video_url,
            "resolution": _normalize_grok_video_resolution(
                resolution_input,
                default="720p",
                allow_auto=True,
            ),
        }

    if provider_payload and normalized_application not in _KLING_VIDEO_ALL_MODELS:
        payload = dict(provider_payload)
        payload.setdefault("prompt", prompt)
        return payload

    if normalized_application in _KLING_VIDEO_ALL_MODELS:
        kling_prompt = _augment_kling_prompt_with_reference_element(
            prompt,
            has_reference_elements=bool(reference_image_urls),
        )
        payload: dict[str, Any] = {
            "prompt": kling_prompt,
            "aspect_ratio": _normalize_fal_video_aspect_ratio(
                aspect_ratio,
                ("16:9", "9:16", "1:1"),
            ),
            "duration": str(max(3, min(15, int(duration_seconds)))),
            "generate_audio": bool(audio_included),
        }

        if normalized_application in _KLING_VIDEO_V2V_REFERENCE_MODELS:
            # video-to-video/reference: requires video_url
            source_video_url = (provider_payload or {}).get("video_url") or ""
            if not source_video_url:
                raise ValueError(f"fal video model '{application}' requires a source video URL")
            payload["video_url"] = source_video_url
            if reference_image_urls:
                payload["image_urls"] = reference_image_urls
            kling_elements = _build_kling_reference_elements(reference_image_urls)
            if kling_elements:
                payload["elements"] = kling_elements
        elif normalized_application in _KLING_VIDEO_REFERENCE_MODELS:
            # reference-to-video: requires start_image_url
            payload["start_image_url"] = _require_video_input_image_url(
                application,
                start_frame=start_frame,
                fallback_reference_image_url=primary_reference_image_url,
            )
            if end_frame:
                payload["end_image_url"] = end_frame
            # Additional reference images beyond the start frame
            extra_ref_urls = [
                u for u in reference_image_urls if u != payload.get("start_image_url")
            ]
            if extra_ref_urls:
                payload["image_urls"] = extra_ref_urls
            kling_elements = _build_kling_reference_elements(reference_image_urls)
            if kling_elements:
                payload["elements"] = kling_elements
        else:
            # text-to-video: no image/video inputs required
            if negative_prompt:
                payload["negative_prompt"] = negative_prompt

        return payload

    if normalized_application in _SEEDANCE_VIDEO_MODELS | _SEEDANCE_VIDEO_IMAGE_MODELS:
        payload = merge_payload(
            {
                "prompt": prompt,
                "aspect_ratio": _normalize_fal_video_aspect_ratio(
                    aspect_ratio,
                    ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
                ),
                "duration": str(max(4, min(12, int(duration_seconds)))),
                "resolution": _normalize_supported_fal_video_resolution(
                    resolution,
                    ("480p", "720p", "1080p"),
                ),
                "generate_audio": bool(audio_included),
            },
            {"seed": seed} if seed is not None else None,
        )
        if normalized_application in _SEEDANCE_VIDEO_IMAGE_MODELS:
            payload["image_url"] = _require_video_input_image_url(
                application,
                start_frame=start_frame,
                fallback_reference_image_url=primary_reference_image_url,
            )
            if end_frame:
                payload["end_image_url"] = end_frame
        return payload

    if normalized_application in _SORA_VIDEO_ALL_MODELS:
        clamped_duration = max(4, min(20, int(duration_seconds)))
        # Snap to nearest allowed duration: 4, 8, 12, 16, 20
        nearest_duration = min(
            _SORA_VIDEO_DURATIONS,
            key=lambda d: abs(d - clamped_duration),
        )
        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": _normalize_fal_video_aspect_ratio(
                aspect_ratio,
                _SORA_VIDEO_ASPECT_RATIOS,
            ),
            "duration": nearest_duration,
            "resolution": _normalize_supported_fal_video_resolution(
                resolution,
                _SORA_VIDEO_RESOLUTIONS,
            ),
        }
        if normalized_application in _SORA_VIDEO_IMAGE_MODELS:
            payload["image_url"] = _require_video_input_image_url(
                application,
                start_frame=start_frame,
                fallback_reference_image_url=primary_reference_image_url,
            )
        return merge_payload(payload, provider_payload)

    return merge_payload(
        {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "audio_included": audio_included,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "negative_prompt": negative_prompt,
            "person_generation": person_generation,
            "seed": seed,
        },
        {"reference_images": list(reference_images)} if reference_images else None,
    )


def build_fal_voice_payload(
    application: str,
    *,
    text: str,
    voice_id: str | None = None,
    language_code: str | None = None,
    output_format: str | None = None,
    voice_settings: Mapping[str, Any] | None = None,
    provider_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_application = application.strip().lower()
    settings = dict(voice_settings or {})

    if provider_payload:
        payload = dict(provider_payload)
        if normalized_application in _MINIMAX_SPEECH_MODELS:
            payload.setdefault("prompt", text)
            payload.setdefault("output_format", "url")
            voice_setting = payload.get("voice_setting")
            if isinstance(voice_setting, Mapping):
                normalized_voice_setting = dict(voice_setting)
                normalized_emotion = _normalize_minimax_emotion(voice_setting.get("emotion"))
                if normalized_emotion:
                    normalized_voice_setting["emotion"] = normalized_emotion
                else:
                    normalized_voice_setting.pop("emotion", None)
                payload["voice_setting"] = normalized_voice_setting
            if "audio_setting" not in payload:
                audio_setting = _build_minimax_audio_setting(output_format)
                if audio_setting:
                    payload["audio_setting"] = audio_setting
        else:
            payload.setdefault("text", text)
        return payload

    if normalized_application in _ELEVENLABS_TTS_MODELS:
        return _build_elevenlabs_tts_payload(
            text=text,
            voice_id=voice_id,
            language_code=language_code,
            voice_settings=settings,
        )

    if normalized_application in _MINIMAX_SPEECH_MODELS:
        return _build_minimax_speech_payload(
            text=text,
            voice_id=voice_id,
            language_code=language_code,
            output_format=output_format,
            voice_settings=settings,
        )

    return merge_payload(
        {
            "text": text,
            "voice_id": voice_id,
            "language_code": language_code,
        },
        {"voice_settings": settings} if settings else None,
    )


def build_fal_audio_payload(
    application: str,
    *,
    prompt: str,
    music_length_ms: int | None = None,
    force_instrumental: bool | None = None,
    output_format: str | None = None,
    provider_payload: Mapping[str, Any] | None = None,
    lyrics_prompt: str | None = None,
    composition_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_application = application.strip().lower()

    if provider_payload:
        payload = dict(provider_payload)
        payload.setdefault("prompt", prompt)
        if normalized_application in _MINIMAX_MUSIC_MODELS:
            payload.pop("music_length_ms", None)
            payload.pop("force_instrumental", None)
            payload.pop("output_format", None)
            payload.pop("composition_plan", None)
            payload.setdefault("lyrics_prompt", lyrics_prompt or prompt)
            if "audio_setting" not in payload:
                audio_setting = _build_minimax_audio_setting(output_format)
                if audio_setting:
                    payload["audio_setting"] = audio_setting
        return payload

    if normalized_application in _ELEVENLABS_MUSIC_MODELS:
        return merge_payload(
            {
                "prompt": prompt,
                "music_length_ms": music_length_ms,
                "force_instrumental": force_instrumental,
                "output_format": output_format,
            },
            {"composition_plan": composition_plan} if composition_plan else None,
        )

    if normalized_application in _MINIMAX_MUSIC_MODELS:
        audio_setting = _build_minimax_audio_setting(output_format)
        return merge_payload(
            {
                "prompt": prompt,
                "lyrics_prompt": lyrics_prompt or prompt,
            },
            {"audio_setting": audio_setting} if audio_setting else None,
        )

    return merge_payload(
        {
            "prompt": prompt,
            "music_length_ms": music_length_ms,
            "force_instrumental": force_instrumental,
            "output_format": output_format,
        },
        {"composition_plan": composition_plan} if composition_plan else None,
    )


def _build_elevenlabs_tts_payload(
    *,
    text: str,
    voice_id: str | None,
    language_code: str | None,
    voice_settings: Mapping[str, Any],
) -> dict[str, Any]:
    return merge_payload(
        {
            "text": text,
            "voice": voice_id or _coerce_non_empty_string(voice_settings.get("voice")),
            "stability": _coerce_float(voice_settings.get("stability")),
            "language_code": _normalize_language_code(language_code),
            "apply_text_normalization": _coerce_non_empty_string(
                voice_settings.get("apply_text_normalization")
            ),
        }
    )


def _build_minimax_speech_payload(
    *,
    text: str,
    voice_id: str | None,
    language_code: str | None,
    output_format: str | None,
    voice_settings: Mapping[str, Any],
) -> dict[str, Any]:
    voice_setting = merge_payload(
        {
            "voice_id": voice_id or _coerce_non_empty_string(voice_settings.get("voice_id")),
            "speed": _coerce_float(voice_settings.get("speed")),
            "vol": _coerce_float(voice_settings.get("vol")),
            "pitch": _coerce_int(voice_settings.get("pitch")),
            "emotion": _normalize_minimax_emotion(voice_settings.get("emotion")),
        }
    )
    voice_modify = voice_settings.get("voice_modify")
    pronunciation_dict = voice_settings.get("pronunciation_dict")
    timber_weights = voice_settings.get("timber_weights")
    audio_setting = voice_settings.get("audio_setting")
    if not isinstance(audio_setting, Mapping):
        audio_setting = _build_minimax_audio_setting(output_format)

    return merge_payload(
        {
            "prompt": text,
            "output_format": _coerce_non_empty_string(voice_settings.get("result_output_format"))
            or "url",
            "language_boost": _resolve_minimax_language_boost(language_code),
            "english_normalization": voice_settings.get("english_normalization"),
        },
        {"voice_setting": voice_setting} if voice_setting else None,
        {"voice_modify": voice_modify} if isinstance(voice_modify, Mapping) else None,
        {"pronunciation_dict": pronunciation_dict}
        if isinstance(pronunciation_dict, list)
        else None,
        {"timber_weights": timber_weights} if isinstance(timber_weights, list) else None,
        {"audio_setting": dict(audio_setting)}
        if isinstance(audio_setting, Mapping) and audio_setting
        else None,
    )


def _build_minimax_audio_setting(output_format: str | None) -> dict[str, Any] | None:
    if not output_format:
        return None

    normalized = output_format.strip().lower()
    if not normalized or normalized in {"url", "hex"}:
        return None

    parts = normalized.split("_")
    fmt = parts[0] if parts else None
    sample_rate = _coerce_int(parts[1]) if len(parts) > 1 else None
    bitrate = _coerce_int(parts[2]) if len(parts) > 2 else None
    if bitrate is not None and bitrate < 1000:
        bitrate *= 1000

    return merge_payload(
        {
            "format": fmt,
            "sample_rate": sample_rate,
            "bitrate": bitrate,
        }
    )


def _normalize_language_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    aliases = {
        "english": "en",
        "en": "en",
        "vietnamese": "vi",
        "vi": "vi",
        "vn": "vi",
        "japanese": "ja",
        "ja": "ja",
        "jp": "ja",
        "hindi": "hi",
        "hi": "hi",
        "korean": "ko",
        "ko": "ko",
        "kr": "ko",
    }
    base = normalized.split("-", 1)[0].split("_", 1)[0]
    return aliases.get(base) or aliases.get(normalized) or base


def _resolve_minimax_language_boost(value: str | None) -> str | None:
    normalized = _normalize_language_code(value)
    if normalized is None:
        return None
    mapping = {
        "en": "English",
        "vi": "Vietnamese",
        "ja": "Japanese",
        "hi": "Hindi",
        "ko": "Korean",
    }
    return mapping.get(normalized)


def _coerce_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_minimax_emotion(value: Any) -> str | None:
    normalized = _coerce_non_empty_string(value)
    if normalized is None:
        return None

    normalized_key = normalized.lower()
    if normalized_key in _MINIMAX_ALLOWED_EMOTIONS:
        return normalized_key

    return _MINIMAX_EMOTION_ALIASES.get(normalized_key)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


async def persist_fal_media_asset(
    asset: FalMediaAsset,
    *,
    media_kind: str,
    output_bucket: str | None,
    project_id: str | None = None,
    user_id: uuid.UUID | None = None,
    default_mime_type: str,
) -> tuple[str, str, str, int]:
    if not output_bucket:
        raise RuntimeError("gcs_output_bucket is required for fal media outputs")

    media_bytes = await _download_remote_bytes(asset.url)
    mime_type = asset.mime_type or infer_mime_type(asset.url, default_mime_type)
    file_name = _resolve_file_name(
        asset.file_name or infer_file_name(asset.url),
        mime_type,
        media_kind,
    )
    file_path = PurePosixPath(file_name)
    unique_suffix = uuid.uuid4().hex[:12]
    file_id = f"{file_path.stem}-{unique_suffix}"
    ext = file_path.suffix.lstrip(".")
    file_name = f"{file_id}.{ext}"

    blob_name = path_resolver.user_file(user_id, media_kind, file_id, ext)

    client = storage.Client(project=project_id) if project_id else storage.Client()
    bucket = client.bucket(output_bucket)

    def _upload_sync() -> str:
        blob = bucket.blob(blob_name)
        blob.cache_control = "public, max-age=31536000"
        blob.upload_from_file(BytesIO(media_bytes), content_type=mime_type)
        return blob.public_url

    public_url = await anyio.to_thread.run_sync(_upload_sync)
    return public_url, blob_name, file_name, len(media_bytes)


def normalize_request_mode(
    request_mode: str | None,
    default: str = "async",
) -> str:
    candidate = (request_mode or default or "async").strip().lower()
    if candidate in _SYNC_REQUEST_MODES:
        return "sync"
    if candidate in _ASYNC_REQUEST_MODES:
        return "async"
    raise ValueError(
        "Unsupported fal request_mode. Expected one of: sync, subscribe, async, submit, submit_async, queue"
    )


def merge_payload(*payloads: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not payload:
            continue
        for key, value in payload.items():
            if value is not None:
                merged[key] = value
    return merged


class FalRunner:
    def __init__(
        self,
        api_key: str,
        default_request_mode: str = "async",
        default_client_timeout: float = 3600.0,
    ):
        if not api_key:
            raise ValueError("fal_api_key is required")

        self.default_request_mode = normalize_request_mode(default_request_mode)
        self.sync_client = fal_client.SyncClient(
            key=api_key,
            default_timeout=default_client_timeout,
        )
        self.async_client = fal_client.AsyncClient(
            key=api_key,
            default_timeout=default_client_timeout,
        )

    async def execute(
        self,
        application: str,
        arguments: Mapping[str, Any],
        *,
        request_mode: str | None = None,
        with_logs: bool = False,
        path: str = "",
        hint: str | None = None,
        start_timeout: float | None = None,
        client_timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        mode = normalize_request_mode(request_mode, self.default_request_mode)
        payload = dict(arguments)
        header_map = dict(headers or {})

        if mode == "sync":
            return await anyio.to_thread.run_sync(
                self._subscribe_sync,
                application,
                payload,
                with_logs,
                path,
                hint,
                start_timeout,
                client_timeout,
                header_map,
            )

        handle = await self.async_client.submit(
            application,
            payload,
            path=path,
            hint=hint,
            headers=header_map,
            start_timeout=start_timeout,
        )
        if with_logs:
            async for update in handle.iter_events(with_logs=True):
                self._log_queue_update(application, update)
        return await handle.get()

    def _subscribe_sync(
        self,
        application: str,
        arguments: dict[str, Any],
        with_logs: bool,
        path: str,
        hint: str | None,
        start_timeout: float | None,
        client_timeout: float | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return self.sync_client.subscribe(
            application,
            arguments,
            path=path,
            hint=hint,
            with_logs=with_logs,
            on_enqueue=self._log_enqueue if with_logs else None,
            headers=headers,
            start_timeout=start_timeout,
            client_timeout=client_timeout,
        )

    def _log_enqueue(self, request_id: str) -> None:
        logger.info("fal request enqueued", extra={"request_id": request_id})

    def _log_queue_update(self, application: str, update: Any) -> None:
        status = _coerce_status(update)
        log_lines = []
        for entry in _coerce_logs(update):
            if isinstance(entry, Mapping):
                message = entry.get("message") or entry.get("msg") or entry.get("log")
                if message is not None:
                    log_lines.append(str(message))
                    continue
            log_lines.append(str(entry))

        extra: dict[str, Any] = {
            "application": application,
            "status": status,
        }

        request_id = None
        if isinstance(update, Mapping):
            request_id = update.get("request_id") or update.get("requestId")
        else:
            request_id = getattr(update, "request_id", None) or getattr(
                update,
                "requestId",
                None,
            )
        if request_id is not None:
            extra["request_id"] = str(request_id)

        if log_lines:
            logger.info(
                "fal request update: %s",
                " | ".join(log_lines),
                extra=extra,
            )
            return

        logger.info("fal request update", extra=extra)


def unwrap_result_data(result: Any) -> Any:
    if isinstance(result, Mapping):
        data = result.get("data")
        if data is not None:
            return data
    return result


def extract_first_media_asset(
    result: Mapping[str, Any] | Any,
    *,
    preferred_keys: Sequence[str],
) -> FalMediaAsset | None:
    payload = unwrap_result_data(result)
    if isinstance(payload, Mapping):
        for key in preferred_keys:
            asset = _coerce_media_asset(payload.get(key))
            if asset is not None:
                return asset
    return _coerce_media_asset(payload)


def extract_cost(result: Mapping[str, Any] | Any) -> float:
    for payload in (result, unwrap_result_data(result)):
        if isinstance(payload, Mapping):
            for key in ("cost", "estimated_cost", "estimatedCost", "price"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
    return 0.0


def infer_mime_type(url: str, fallback: str) -> str:
    guessed, _ = mimetypes.guess_type(url)
    return guessed or fallback


def infer_file_name(url: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return None
    name = PurePosixPath(path).name
    return name or None


def _resolve_fal_named_image_size(aspect_ratio: str | None) -> str:
    normalized_ratio = (aspect_ratio or "1:1").strip()
    if normalized_ratio in _IMAGE_SIZE_BY_ASPECT_RATIO:
        return _IMAGE_SIZE_BY_ASPECT_RATIO[normalized_ratio]

    ratio_value = _ratio_to_float(normalized_ratio)
    if ratio_value is None:
        return "square_hd"
    if ratio_value < 1:
        return "portrait_4_3"
    if ratio_value > 1:
        return "landscape_4_3"
    return "square_hd"


def _build_flux_image_payload(
    *,
    prompt: str,
    aspect_ratio: str,
    image_size: str | None,
) -> dict[str, Any]:
    normalized_resolution = _normalize_ui_image_resolution(image_size)
    if normalized_resolution in {"2K", "4K"}:
        return {
            "prompt": prompt,
            "image_size": _build_flux_custom_size(aspect_ratio, normalized_resolution),
        }
    return {
        "prompt": prompt,
        "image_size": _resolve_fal_named_image_size(aspect_ratio),
    }


def _build_flux_image_edit_payload(
    *,
    application: str,
    prompt: str,
    aspect_ratio: str,
    image_size: str | None,
    image_urls: Sequence[str] | None,
) -> dict[str, Any]:
    payload = _build_flux_image_payload(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
    )
    payload["image_urls"] = _require_reference_image_urls(application, image_urls)
    return payload


def _build_seedream_image_payload(
    *,
    prompt: str,
    aspect_ratio: str,
    image_size: str | None,
) -> dict[str, Any]:
    normalized_resolution = _normalize_ui_image_resolution(image_size)
    if normalized_resolution == "4K":
        return {
            "prompt": prompt,
            "image_size": _build_seedream_custom_size(aspect_ratio, "4K"),
        }
    if normalized_resolution == "2K":
        return {
            "prompt": prompt,
            "image_size": _build_seedream_custom_size(aspect_ratio, "2K"),
        }
    return {
        "prompt": prompt,
        "image_size": _resolve_fal_named_image_size(aspect_ratio),
    }


def _build_qwen_image_payload(
    *,
    prompt: str,
    aspect_ratio: str,
    image_size: str | None,
) -> dict[str, Any]:
    normalized_resolution = _normalize_ui_image_resolution(image_size)
    if normalized_resolution in {"2K", "4K"}:
        return {
            "prompt": prompt,
            "image_size": _build_qwen_custom_size(aspect_ratio),
        }
    return {
        "prompt": prompt,
        "image_size": _resolve_fal_named_image_size(aspect_ratio),
    }


def _normalize_ui_image_resolution(image_size: str | None) -> str:
    normalized = (image_size or "1K").strip().upper()
    if normalized in {"512PX", "512"}:
        return "1K"
    if normalized in {"2K", "4K", "8K"}:
        return normalized
    return "1K"


def _build_seedream_custom_size(
    aspect_ratio: str,
    resolution: str,
) -> dict[str, int]:
    size_map = {
        "2K": {
            "1:1": {"width": 2048, "height": 2048},
            "4:3": {"width": 2560, "height": 1920},
            "3:4": {"width": 1920, "height": 2560},
            "16:9": {"width": 2560, "height": 1440},
            "9:16": {"width": 1440, "height": 2560},
            "3:2": {"width": 2432, "height": 1600},
            "2:3": {"width": 1600, "height": 2432},
        },
        "4K": {
            "1:1": {"width": 4096, "height": 4096},
            "4:3": {"width": 4096, "height": 3072},
            "3:4": {"width": 3072, "height": 4096},
            "16:9": {"width": 4096, "height": 2304},
            "9:16": {"width": 2304, "height": 4096},
            "3:2": {"width": 3840, "height": 2560},
            "2:3": {"width": 2560, "height": 3840},
        },
    }
    normalized_ratio = (aspect_ratio or "1:1").strip()
    selected = size_map.get(resolution, {}).get(normalized_ratio)
    if selected is not None:
        return selected

    if _ratio_to_float(normalized_ratio) and _ratio_to_float(normalized_ratio) < 1:
        return size_map[resolution]["9:16"]
    return size_map[resolution]["16:9"]


def _build_flux_custom_size(
    aspect_ratio: str,
    resolution: str,
) -> dict[str, int]:
    size_map = {
        "2K": {
            "1:1": {"width": 2048, "height": 2048},
            "4:3": {"width": 2048, "height": 1536},
            "3:4": {"width": 1536, "height": 2048},
            "16:9": {"width": 2048, "height": 1152},
            "9:16": {"width": 1152, "height": 2048},
            "3:2": {"width": 1920, "height": 1280},
            "2:3": {"width": 1280, "height": 1920},
        },
        "4K": {
            "1:1": {"width": 4096, "height": 4096},
            "4:3": {"width": 4096, "height": 3072},
            "3:4": {"width": 3072, "height": 4096},
            "16:9": {"width": 4096, "height": 2304},
            "9:16": {"width": 2304, "height": 4096},
            "3:2": {"width": 3840, "height": 2560},
            "2:3": {"width": 2560, "height": 3840},
        },
    }
    normalized_ratio = (aspect_ratio or "1:1").strip()
    selected = size_map.get(resolution, {}).get(normalized_ratio)
    if selected is not None:
        return selected

    ratio_value = _ratio_to_float(normalized_ratio)
    if ratio_value is not None and ratio_value < 1:
        return size_map[resolution]["9:16"]
    return size_map[resolution]["16:9"]


def _build_qwen_custom_size(aspect_ratio: str) -> dict[str, int]:
    size_map = {
        "1:1": {"width": 2048, "height": 2048},
        "4:3": {"width": 2048, "height": 1536},
        "3:4": {"width": 1536, "height": 2048},
        "16:9": {"width": 2048, "height": 1152},
        "9:16": {"width": 1152, "height": 2048},
        "3:2": {"width": 1920, "height": 1280},
        "2:3": {"width": 1280, "height": 1920},
    }
    normalized_ratio = (aspect_ratio or "1:1").strip()
    selected = size_map.get(normalized_ratio)
    if selected is not None:
        return selected

    if _ratio_to_float(normalized_ratio) and _ratio_to_float(normalized_ratio) < 1:
        return size_map["9:16"]
    return size_map["16:9"]


def _normalize_grok_aspect_ratio(aspect_ratio: str | None) -> str:
    supported = (
        "2:1",
        "20:9",
        "19.5:9",
        "16:9",
        "4:3",
        "3:2",
        "1:1",
        "2:3",
        "3:4",
        "9:16",
        "9:19.5",
        "9:20",
        "1:2",
    )
    normalized = (aspect_ratio or "1:1").strip()
    if normalized in supported:
        return normalized
    return _nearest_supported_aspect_ratio(normalized, supported, default="1:1")


def _build_grok_image_payload(
    *,
    prompt: str,
    aspect_ratio: str,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "aspect_ratio": _normalize_grok_aspect_ratio(aspect_ratio),
    }


def _normalize_grok_video_aspect_ratio(
    aspect_ratio: str | None,
    *,
    allow_auto: bool,
) -> str:
    normalized = (aspect_ratio or "").strip()
    if allow_auto and normalized.lower() == "auto":
        return "auto"
    if normalized in _GROK_VIDEO_ASPECT_RATIOS:
        return normalized
    if not normalized:
        return "auto" if allow_auto else "16:9"
    return _nearest_supported_aspect_ratio(
        normalized,
        _GROK_VIDEO_ASPECT_RATIOS,
        default="auto" if allow_auto else "16:9",
    )


def _normalize_fal_video_aspect_ratio(
    aspect_ratio: str | None,
    supported: Sequence[str],
) -> str:
    supported_values = tuple(supported)
    normalized = (aspect_ratio or "").strip()
    if normalized in supported_values:
        return normalized
    if normalized.lower() == "auto" and "auto" in supported_values:
        return "auto"

    ratio_value = _ratio_to_float(normalized)
    if ratio_value is None:
        return supported_values[0]

    if abs(ratio_value - 1.0) < 0.08 and "1:1" in supported_values:
        return "1:1"
    if ratio_value < 1:
        for candidate in ("3:4", "9:16", "1:1"):
            if candidate in supported_values:
                return candidate
    for candidate in ("4:3", "16:9", "21:9", "1:1"):
        if candidate in supported_values:
            return candidate
    return supported_values[0]


def _normalize_fal_video_resolution(resolution: str | None) -> str:
    normalized = (resolution or "720p").strip().lower()
    if normalized == "480p":
        return "480p"
    if normalized in {"1080p", "4k", "2160p", "2460p"}:
        return "1080p"
    return "720p"


def _normalize_supported_fal_video_resolution(
    resolution: str | None,
    supported: Sequence[str],
) -> str:
    normalized = _normalize_fal_video_resolution(resolution)
    if normalized in supported:
        return normalized
    if normalized == "480p":
        return supported[0]
    return supported[-1]


def _normalize_grok_video_resolution(
    resolution: Any,
    *,
    default: str,
    allow_auto: bool,
) -> str:
    normalized = str(resolution or "").strip().lower()
    if allow_auto and normalized == "auto":
        return "auto"
    if normalized == "480p":
        return "480p"
    if normalized == "720p":
        return "720p"
    return default


def _nearest_supported_value(value: int, supported: Sequence[int]) -> int:
    return min(supported, key=lambda candidate: (abs(candidate - value), candidate))


def _nearest_supported_aspect_ratio(
    aspect_ratio: str,
    supported: Sequence[str],
    *,
    default: str,
) -> str:
    ratio_value = _ratio_to_float(aspect_ratio)
    if ratio_value is None:
        return default

    candidates: list[tuple[float, str]] = []
    for candidate in supported:
        candidate_ratio = _ratio_to_float(candidate)
        if candidate_ratio is None:
            continue
        candidates.append((candidate_ratio, candidate))
    if not candidates:
        return default

    return min(
        candidates,
        key=lambda candidate: (abs(candidate[0] - ratio_value), candidate[0]),
    )[1]


def _ratio_to_float(aspect_ratio: str) -> float | None:
    try:
        width, height = aspect_ratio.split(":", 1)
        width_value = float(width)
        height_value = float(height)
    except Exception:
        return None
    if height_value == 0:
        return None
    return width_value / height_value


def resolve_fal_image_application(
    application: str,
    *,
    image_urls: Sequence[str] | None = None,
    provider_payload: Mapping[str, Any] | None = None,
) -> str:
    normalized = application.strip().lower()
    if not _normalize_reference_image_urls(
        image_urls,
        provider_payload=provider_payload,
    ):
        return application
    return _IMAGE_TO_EDIT_MODEL_MAP.get(normalized, application)


def _normalize_reference_image_urls(
    image_urls: Sequence[str] | None,
    *,
    provider_payload: Mapping[str, Any] | None = None,
) -> list[str]:
    normalized_urls: list[str] = []
    for url in image_urls or ():
        if isinstance(url, str) and url.strip():
            normalized_urls.append(url.strip())

    if normalized_urls or not provider_payload:
        return normalized_urls

    payload_image_urls = provider_payload.get("image_urls")
    if isinstance(payload_image_urls, Sequence) and not isinstance(
        payload_image_urls,
        (str, bytes),
    ):
        for url in payload_image_urls:
            if isinstance(url, str) and url.strip():
                normalized_urls.append(url.strip())

    payload_image_url = provider_payload.get("image_url")
    if isinstance(payload_image_url, str) and payload_image_url.strip():
        normalized_urls.append(payload_image_url.strip())

    return normalized_urls


def _require_reference_image_urls(
    application: str,
    image_urls: Sequence[str] | None,
) -> list[str]:
    normalized_application = application.strip().lower()
    normalized_urls = list(image_urls or [])
    if normalized_application in _QWEN_IMAGE_EDIT_MODELS | _GROK_IMAGE_EDIT_MODELS:
        normalized_urls = normalized_urls[:3]
    elif normalized_application in _SEEDREAM_IMAGE_EDIT_MODELS:
        normalized_urls = normalized_urls[-10:]

    if not normalized_urls:
        raise ValueError(
            f"fal image edit model '{application}' requires at least one reference image URL"
        )
    return normalized_urls


async def _download_remote_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _resolve_file_name(
    candidate: str | None,
    mime_type: str,
    media_kind: str,
) -> str:
    extension = _extension_for_mime_type(mime_type)
    if candidate:
        file_name = PurePosixPath(candidate).name
        if "." in file_name:
            return file_name
        return f"{file_name}{extension}"
    return f"{media_kind}-{uuid.uuid4().hex[:8]}{extension}"


def _extension_for_mime_type(mime_type: str) -> str:
    normalized_mime = mime_type.lower()
    extension = _EXTENSION_BY_MIME_TYPE.get(normalized_mime)
    if extension:
        return extension

    guessed = mimetypes.guess_extension(normalized_mime) or ""
    if guessed == ".jpe":
        return ".jpg"
    return guessed or ".bin"


def resolve_fal_video_application(
    application: str,
    *,
    start_frame: str | None = None,
    end_frame: str | None = None,
    reference_images: Sequence[Mapping[str, Any]] | None = None,
    source_video: str | None = None,
) -> str:
    normalized = application.strip().lower()
    if normalized in _GROK_VIDEO_MODELS and (
        start_frame or _normalize_video_reference_image_urls(reference_images)
    ):
        return "xai/grok-imagine-video/image-to-video"
    if normalized in _KLING_VIDEO_MODELS:
        has_source_video = bool(source_video and source_video.strip())
        has_images = bool(start_frame or _normalize_video_reference_image_urls(reference_images))
        if has_source_video:
            return "fal-ai/kling-video/o3/pro/video-to-video/reference"
        if has_images:
            return "fal-ai/kling-video/o3/pro/reference-to-video"
        return application
    if normalized in _SEEDANCE_VIDEO_MODELS and (
        start_frame or _normalize_video_reference_image_urls(reference_images)
    ):
        return "fal-ai/bytedance/seedance/v1.5/pro/image-to-video"
    if normalized in _SORA_VIDEO_MODELS and start_frame:
        return "fal-ai/sora-2/image-to-video/pro"
    return application


def _normalize_video_reference_image_urls(
    reference_images: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    normalized_urls: list[str] = []
    for image in reference_images or ():
        if not isinstance(image, Mapping):
            continue
        url = image.get("url")
        if isinstance(url, str) and url.strip():
            normalized_urls.append(url.strip())
    return normalized_urls


def _require_video_input_image_url(
    application: str,
    *,
    start_frame: str | None,
    fallback_reference_image_url: str | None,
) -> str:
    candidate = (start_frame or fallback_reference_image_url or "").strip()
    if candidate:
        return candidate
    raise ValueError(
        f"fal video model '{application}' requires a start frame or reference image URL"
    )


def _resolve_grok_input_image_url(
    application: str,
    *,
    start_frame: str | None,
    primary_reference_image_url: str | None,
    provider_payload: Mapping[str, Any] | None,
) -> str:
    provider_image_url = None
    if provider_payload:
        raw_provider_image_url = provider_payload.get("image_url")
        if isinstance(raw_provider_image_url, str) and raw_provider_image_url.strip():
            provider_image_url = raw_provider_image_url.strip()

    return _require_video_input_image_url(
        application,
        start_frame=start_frame or provider_image_url,
        fallback_reference_image_url=primary_reference_image_url,
    )


def _require_grok_video_source_url(
    application: str,
    provider_payload: Mapping[str, Any] | None,
) -> str:
    if provider_payload:
        raw_video_url = provider_payload.get("video_url")
        if isinstance(raw_video_url, str) and raw_video_url.strip():
            return raw_video_url.strip()

    raise ValueError(
        f"fal video model '{application}' requires a source video URL via provider_payload.video_url"
    )


def _build_kling_reference_elements(
    reference_image_urls: Sequence[str],
) -> list[dict[str, Any]] | None:
    normalized_urls = list(reference_image_urls)
    if not normalized_urls:
        return None

    element: dict[str, Any] = {
        "frontal_image_url": normalized_urls[0],
    }
    if len(normalized_urls) > 1:
        element["reference_image_urls"] = normalized_urls[1:]
    return [element]


def _augment_kling_prompt_with_reference_element(
    prompt: str,
    *,
    has_reference_elements: bool,
) -> str:
    if not has_reference_elements or "@Element" in prompt:
        return prompt
    return f"{prompt.rstrip()} Use @Element1 as the primary visual reference."


def _coerce_status(update: Any) -> str:
    if isinstance(update, dict):
        status = update.get("status")
    else:
        status = getattr(update, "status", None)
    return str(status).upper() if status is not None else update.__class__.__name__.upper()


def _coerce_logs(update: Any) -> list[Any]:
    if isinstance(update, dict):
        logs = update.get("logs")
    else:
        logs = getattr(update, "logs", None)

    if not logs:
        return []
    if isinstance(logs, list):
        return logs
    return [logs]


def _coerce_media_asset(value: Any, depth: int = 0) -> FalMediaAsset | None:
    if value is None or depth > 4:
        return None

    if isinstance(value, str):
        if value.startswith(("http://", "https://", "gs://", "data:")):
            return FalMediaAsset(
                url=value,
                mime_type=infer_mime_type(value, "application/octet-stream"),
                file_name=infer_file_name(value),
            )
        return None

    if isinstance(value, Mapping):
        for key in _MEDIA_URL_KEYS:
            url = value.get(key)
            if isinstance(url, str) and url:
                mime_type = _first_string(value, _MIME_KEYS)
                size = _first_int(value, _SIZE_KEYS)
                file_name = _first_string(value, ("file_name", "filename", "name"))
                return FalMediaAsset(
                    url=url,
                    mime_type=mime_type,
                    size=size,
                    file_name=file_name or infer_file_name(url),
                )

        for nested_key in ("file", "asset", "image", "video", "audio", "data"):
            asset = _coerce_media_asset(value.get(nested_key), depth + 1)
            if asset is not None:
                return asset

        for nested_value in value.values():
            asset = _coerce_media_asset(nested_value, depth + 1)
            if asset is not None:
                return asset
        return None

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            asset = _coerce_media_asset(item, depth + 1)
            if asset is not None:
                return asset

    return None


def _first_string(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _first_int(payload: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return None
