import asyncio
from typing import List

from tavily import TavilyClient

from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitError,
    WebVisitResult,
)


class TavilyWebVisitClient(BaseWebVisitClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.tavily_client = TavilyClient(api_key=self.api_key)

    async def extract(self, url: str) -> WebVisitResult:
        """Extract content from a webpage using Tavily."""
        try:
            response = await asyncio.to_thread(self.tavily_client.extract, urls=[url])
            if response["failed_results"]:
                raise WebVisitError(f"Tavily failed to extract content from {url}")

            # Since only a single link is provided to tavily_client, the results will contain only one entry.
            content = response["results"][0]["raw_content"]
            title = response["results"][0].get("title", "")

            formatted_content = f"Title: {title}\n\nContent: {content}"

            return WebVisitResult(
                content=formatted_content,
                cost=0.0,  # Tavily cost calculation can be added here if needed
            )

        except Exception as e:
            raise WebVisitError(f"Tavily extraction error: {str(e)}")

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Extract content from multiple webpages."""
        tasks = [self.extract(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=sum(result.cost for result in results),
        )
