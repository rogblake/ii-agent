"""Factory function for creating slide generation clients."""

from ii_agent_tools.integrations.slide_generation.config import SlideGenerationConfig
from ii_agent_tools.integrations.slide_generation.base import BaseSlideGenerationClient
from ii_agent_tools.integrations.slide_generation.gemini_slide_generator import (
    GeminiSlideGenerationClient,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


def create_slide_generation_client(
    settings: SlideGenerationConfig,
) -> BaseSlideGenerationClient:
    """Factory function that creates a slide generation client based on available configuration.

    Args:
        settings: SlideGenerationConfig with API keys and storage settings

    Returns:
        A slide generation client instance

    Raises:
        ValueError: If no valid configuration is provided
    """
    if settings.gemini_api_key or (settings.gcp_project_id and settings.gcp_location):
        logger.info("Using Gemini for slide generation")
        return GeminiSlideGenerationClient(config=settings)

    raise ValueError(
        "No slide generation provider configured. "
        "Please set GEMINI_API_KEY environment variable."
    )
