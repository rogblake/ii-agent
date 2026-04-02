from typing import List

from ii_agent_tools.logger import get_logger
from ii_agent_tools.integrations.web_search.base import (
    WebSearchResult,
    WebSearchServiceType,
)
from ii_agent_tools.integrations.web_search.config import WebSearchConfig
from ii_agent_tools.integrations.web_search.exception import WebSearchError
from ii_agent_tools.integrations.web_search.factory import create_web_search_client

logger = get_logger(__name__)


class WebSearchService:
    def __init__(self, web_search_config: WebSearchConfig):
        self.web_search_config = web_search_config

    async def search(
        self,
        query: str,
        max_results: int = 10,
        service_type: WebSearchServiceType | None = None,
    ) -> WebSearchResult:
        client_type = service_type or "serpapi"
        logger.info(
            "Attempting web search with client type",
            extra={"client_type": client_type, "query": query},
        )
        try:
            client = create_web_search_client(self.web_search_config, client_type)
            return await client.search(query, max_results)
        except WebSearchError as e:
            logger.warning(
                "Web search failed",
                extra={
                    "client_type": client_type,
                    "query": query,
                    "max_results": max_results,
                    "error": str(e),
                },
            )
            raise
        except Exception as e:
            logger.exception(
                "Unexpected web search error",
                extra={
                    "client_type": client_type,
                    "query": query,
                    "max_results": max_results,
                },
            )
            raise WebSearchError(str(e))

    async def batch_search(
        self,
        queries: List[str],
        max_results: int = 10,
        service_type: WebSearchServiceType | None = None,
    ) -> List[WebSearchResult]:
        client_type = service_type or "serpapi"
        logger.info(
            "Attempting batch web search with client type",
            extra={"client_type": client_type, "queries_count": len(queries)},
        )
        client = create_web_search_client(self.web_search_config, client_type)
        return await client.batch_search(queries, max_results)
