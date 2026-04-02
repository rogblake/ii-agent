"""Constants for audio generation module."""

from enum import Enum


class AudioGenerationProvider(str, Enum):
    """Enum for audio generation providers."""

    FAL = "fal"


PROVIDER_ALIASES = {
    "fal-ai": AudioGenerationProvider.FAL,
    "fal_ai": AudioGenerationProvider.FAL,
}
