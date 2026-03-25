import asyncio
from typing import List

import requests

from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitError,
    WebVisitResult,
)


class JinaWebVisitClient(BaseWebVisitClient):
    def __init__(self, api_key):
        """
        Initialize the Jina web visit client.
        """
        self.api_key = api_key

    async def extract(self, url: str) -> WebVisitResult:
        """Extract content from a webpage using Jina."""
        if not self.api_key:
            raise WebVisitError("JINA_API_KEY environment variable not set")

        jina_url = f"https://r.jina.ai/{url}"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Engine": "browser",
            "X-Return-Format": "markdown",
        }

        try:
            response = await asyncio.to_thread(requests.get, jina_url, headers=headers)
            if response.status_code == 200:
                json_response = response.json()
                content = json_response["data"]["content"]
                title = json_response["data"].get("title", "")

                formatted_content = f"Title: {title}\n\nContent: {content}"

                return WebVisitResult(
                    content=formatted_content,
                    cost=0.0,  # Jina cost calculation can be added here if needed
                )
            else:
                raise WebVisitError(
                    f"Jina API returned status code {response.status_code}"
                )
        except Exception as e:
            raise WebVisitError(f"Jina extraction error: {str(e)}")

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Extract content from multiple webpages."""
        tasks = [self.extract(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=0,
        )
