from abc import ABC, abstractmethod
from typing import Dict, List, Literal

from pydantic import BaseModel


class WebSearchResult(BaseModel):
    result: List[Dict[str, str]]
    cost: float


WebSearchServiceType = Literal["serpapi", "duckduckgo"]
WEB_SEARCH_SERVICE_TYPES: tuple[str, ...] = ("serpapi", "duckduckgo")


class BaseWebSearchClient(ABC):
    """Base interface for web search clients."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> WebSearchResult:
        pass

    @abstractmethod
    async def batch_search(
        self, queries: List[str], max_results: int = 10
    ) -> List[WebSearchResult]:
        pass
