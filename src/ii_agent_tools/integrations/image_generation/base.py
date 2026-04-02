from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal
from pydantic import BaseModel


class ImageGenerationResult(BaseModel):
    url: str
    mime_type: str
    size: int
    cost: float
    search_results: List[Dict[str, Any]] | None = None
    storage_path: str | None = None
    file_name: str | None = None


class ImageGenerationError(Exception):
    """Custom exception for image generation errors."""

    pass


class BaseImageGenerationClient(ABC):
    """Base interface for image generation clients."""

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal[
            "1:1",
            "2:3",
            "3:2",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "9:16",
            "16:9",
            "21:9",
            "1:4",
            "4:1",
            "1:8",
            "8:1",
        ] = "1:1",
        **kwargs,
    ) -> ImageGenerationResult:
        """Generate an image based on the provided text prompt.

        Args:
            prompt: Text description of the image to generate
            aspect_ratio: Desired aspect ratio of the generated image
            **kwargs: Provider-specific arguments such as:
                - image_urls (List[str] | None): Optional reference images for image-to-image generation
                - image_size (str): Size of the image (e.g., "1K", "2K")
                - Other provider-specific parameters

        Returns:
            ImageGenerationResult with the generated image details
        """
        pass

    async def generate_from_images(
        self,
        prompt: str,
        image_urls: List[str],
        aspect_ratio: Literal[
            "1:1",
            "2:3",
            "3:2",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "9:16",
            "16:9",
            "21:9",
            "1:4",
            "4:1",
            "1:8",
            "8:1",
        ] = "1:1",
        **kwargs,
    ) -> ImageGenerationResult:
        raise ImageGenerationError("Image-to-image generation is not supported by this provider")
