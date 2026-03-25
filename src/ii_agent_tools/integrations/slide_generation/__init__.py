"""Slide generation integration module."""

from .factory import create_slide_generation_client
from .config import SlideGenerationConfig
from .base import BaseSlideGenerationClient, SlideGenerationResult, SlideGenerationError
from .gemini_slide_generator import GeminiSlideGenerationClient
from .service import SlideGenerationService

__all__ = [
    "create_slide_generation_client",
    "SlideGenerationConfig",
    "BaseSlideGenerationClient",
    "SlideGenerationResult",
    "SlideGenerationError",
    "GeminiSlideGenerationClient",
    "SlideGenerationService",
]
