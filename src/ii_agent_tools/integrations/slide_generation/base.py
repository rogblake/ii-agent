"""Base classes and models for slide generation."""

from abc import ABC, abstractmethod
from pydantic import BaseModel


class SlideGenerationResult(BaseModel):
    """Result of slide image generation."""

    url: str
    mime_type: str
    size: int
    storage_path: str
    width: int = 1920
    height: int = 1080
    cost: float = 0.0


class SlideGenerationError(Exception):
    """Custom exception for slide generation errors."""

    pass


class BaseSlideGenerationClient(ABC):
    """Base interface for slide generation clients."""

    @abstractmethod
    async def generate_slide(
        self,
        full_prompt: str,
        **kwargs,
    ) -> SlideGenerationResult:
        """Generate a slide image based on the provided prompt.

        Args:
            full_prompt: Complete prompt describing the slide to generate

        Returns:
            SlideGenerationResult with the generated image URL and metadata
        """
        pass
