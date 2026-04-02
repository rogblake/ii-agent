import asyncio
from typing import Any, List
import aiohttp

from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitResult,
    WebVisitError,
)


class FireCrawlWebVisitClient(BaseWebVisitClient):
    """FireCrawl implementation of web visit client."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev/v1/scrape"

    async def _firecrawl_credit_to_cost(self, firecrawl_credit: int) -> float:
        """Convert FireCrawl credit to cost."""
        return (
            firecrawl_credit * 83 / 100000
        )  # $83 per month ~ 100000 credits with standard price: https://www.firecrawl.dev/pricing

    async def _extract(self, url: str) -> dict[str, Any]:
        """Visit webpage and extract content using FireCrawl."""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "url": url,
            "onlyMainContent": False,
            "formats": ["markdown"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                response_data = await response.json()

        data = response_data.get("data", {})
        return data

    async def extract(self, url: str) -> WebVisitResult:
        """Visit webpage and extract content using FireCrawl."""
        data = await self._extract(url)
        credits_used = data.get("metadata", {}).get("creditsUsed", 0)
        markdown = data.get("markdown", "")
        if markdown is None or (isinstance(markdown, str) and not markdown.strip()):
            raise WebVisitError("No content could be extracted from webpage")
        return WebVisitResult(
            content=markdown,
            cost=await self._firecrawl_credit_to_cost(credits_used),
        )

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Visit webpage and extract content using FireCrawl."""
        tasks = [self.extract(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=sum(result.cost for result in results),
        )
