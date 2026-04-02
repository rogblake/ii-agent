"""Constants for voice generation module."""

from enum import Enum


class VoiceGenerationProvider(str, Enum):
    """Enum for voice generation providers."""

    ELEVENLABS = "elevenlabs"
    GEMINI = "gemini"
    FAL = "fal"


PROVIDER_ALIASES = {
    "11labs": VoiceGenerationProvider.ELEVENLABS,
    "eleven-labs": VoiceGenerationProvider.ELEVENLABS,
    "google": VoiceGenerationProvider.GEMINI,
    "google-tts": VoiceGenerationProvider.GEMINI,
    "gemini-tts": VoiceGenerationProvider.GEMINI,
    "fal-ai": VoiceGenerationProvider.FAL,
    "fal_ai": VoiceGenerationProvider.FAL,
}
