"""Pricing configuration for voice generation providers.

Centralizes pricing and basic duration estimation for voice generation models.
"""

# Docs: https://elevenlabs.io/text-to-speech-api
ELEVENLABS_PRICE_PER_MINUTE: dict[str, float] = {
    "eleven_v3": 0.12,
    "eleven-v3": 0.12,
}

# Prices per 1M tokens for Gemini TTS models.
# Input price is for text tokens; output price is for audio tokens.
GEMINI_TTS_PRICE_PER_MILLION: dict[str, dict[str, float]] = {
    "gemini-2.5-pro-preview-tts": {"input": 1.0, "output": 20.0},
}


def _normalize_model_name(model_name: str | None) -> str | None:
    if not model_name:
        return None
    normalized = model_name.strip().lower()
    if not normalized:
        return None
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def get_elevenlabs_price_per_minute(model_name: str | None) -> float:
    """Return the price per minute for an ElevenLabs model."""
    normalized = _normalize_model_name(model_name)
    if not normalized:
        return 0.0
    return ELEVENLABS_PRICE_PER_MINUTE.get(normalized, 0.0)


def _parse_output_format(
    output_format: str | None,
) -> tuple[str | None, int | None, int | None]:
    if not output_format:
        return None, None, None
    parts = output_format.strip().lower().split("_")
    if not parts:
        return None, None, None

    codec = parts[0] or None
    sample_rate = None
    bitrate_kbps = None

    if len(parts) >= 2 and parts[1].isdigit():
        sample_rate = int(parts[1])
    if len(parts) >= 3 and parts[2].isdigit():
        bitrate_kbps = int(parts[2])

    return codec, sample_rate, bitrate_kbps


def estimate_audio_duration_seconds(audio_size_bytes: int, output_format: str | None) -> float:
    """Estimate duration from byte size and output format.

    - If bitrate is provided (e.g. mp3_44100_128), use it.
    - Otherwise, assume mono PCM/ulaw when a sample rate is provided.
    """
    if audio_size_bytes <= 0:
        return 0.0

    codec, sample_rate, bitrate_kbps = _parse_output_format(output_format)
    if bitrate_kbps:
        return (audio_size_bytes * 8) / (bitrate_kbps * 1000)

    if sample_rate:
        bytes_per_sample = 2
        if codec in ("ulaw", "mulaw"):
            bytes_per_sample = 1
        bytes_per_second = sample_rate * bytes_per_sample
        return audio_size_bytes / bytes_per_second

    return 0.0


def calculate_elevenlabs_cost(
    audio_size_bytes: int,
    output_format: str | None,
    model_name: str | None,
) -> float:
    """Calculate ElevenLabs voice generation cost in USD."""
    price_per_minute = get_elevenlabs_price_per_minute(model_name)
    if price_per_minute <= 0:
        return 0.0

    duration_seconds = estimate_audio_duration_seconds(audio_size_bytes, output_format)
    if duration_seconds <= 0:
        return 0.0

    return price_per_minute * (duration_seconds / 60.0)


def get_gemini_tts_price_per_million(
    model_name: str | None,
) -> tuple[float, float]:
    """Return Gemini TTS pricing per 1M tokens (input, output)."""
    normalized = _normalize_model_name(model_name)
    if not normalized:
        return 0.0, 0.0

    pricing = GEMINI_TTS_PRICE_PER_MILLION.get(normalized)
    if not pricing:
        return 0.0, 0.0

    return pricing.get("input", 0.0), pricing.get("output", 0.0)


def calculate_gemini_tts_cost(
    input_tokens: int,
    output_tokens: int,
    model_name: str | None,
) -> float:
    """Calculate Gemini TTS cost in USD using token counts."""
    input_price, output_price = get_gemini_tts_price_per_million(model_name)
    if input_price <= 0 and output_price <= 0:
        return 0.0

    return input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000
