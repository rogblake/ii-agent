from ii_agent_tools.integrations.image_search.base import BaseImageSearchClient
from ii_agent_tools.integrations.image_search.serpapi import SerpAPIImageSearchClient
from ii_agent_tools.integrations.image_search.duckduckgo import (
    DuckDuckGoImageSearchClient,
)
from ii_agent_tools.integrations.image_search.config import ImageSearchConfig
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


def create_image_search_client(settings: ImageSearchConfig) -> BaseImageSearchClient:
    """
    Factory function that creates an image search client based on available API keys.

    Args:
        settings: Settings object containing API keys

    Returns:
        BaseImageSearchClient: An instance of an image search client, or None if no API key is available
    """
    serpapi_key = settings.serpapi_api_key

    if serpapi_key:
        logger.info("Using SerpAPI to search for images")
        return SerpAPIImageSearchClient(api_key=serpapi_key)

    logger.info("Using DuckDuckGo to search for images")
    return DuckDuckGoImageSearchClient()
