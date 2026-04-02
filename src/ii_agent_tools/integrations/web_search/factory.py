from ii_agent_tools.integrations.web_search.base import (
    BaseWebSearchClient,
    WebSearchServiceType,
)
from ii_agent_tools.integrations.web_search.serpapi import SerpAPIWebSearchClient
from ii_agent_tools.integrations.web_search.duckduckgo import DuckDuckGoWebSearchClient
from ii_agent_tools.integrations.web_search.config import WebSearchConfig
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


def create_web_search_client(
    settings: WebSearchConfig,
    client_type: WebSearchServiceType | None = None,
) -> BaseWebSearchClient:
    """
    Factory function that creates a web search client based on available API keys.
    Priority order: SerpAPI > DuckDuckGo

    Args:
        settings: Settings object containing API keys
        client_type: Specific client type to use (optional)

    Returns:
        BaseWebSearchClient: An instance of a web search client
    """
    serpapi_key = settings.serpapi_api_key

    if client_type == "serpapi":
        if not serpapi_key:
            logger.warning("SerpAPI API key not found. Falling back to DuckDuckGo client")
        else:
            logger.info("Using SerpAPI to search")
            return SerpAPIWebSearchClient(api_key=serpapi_key)

    if client_type == "duckduckgo":
        logger.info("Using DuckDuckGo to search")
        return DuckDuckGoWebSearchClient()

    if serpapi_key:
        logger.info("Using SerpAPI to search")
        return SerpAPIWebSearchClient(api_key=serpapi_key)

    logger.info("Using DuckDuckGo to search")
    return DuckDuckGoWebSearchClient()
