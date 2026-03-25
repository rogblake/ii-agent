"""Constants for image generation module."""

from enum import Enum


class ImageGenerationProvider(str, Enum):
    """Enum for image generation providers."""

    GEMINI = "gemini"
    VERTEX = "vertex"
    OPENAI = "openai"
    DUCKDUCKGO = "duckduckgo"
    FAL = "fal"


# Provider aliases - maps user-friendly names to canonical provider names
PROVIDER_ALIASES = {
    "fal-ai": ImageGenerationProvider.FAL,
    "fal_ai": ImageGenerationProvider.FAL,
}
