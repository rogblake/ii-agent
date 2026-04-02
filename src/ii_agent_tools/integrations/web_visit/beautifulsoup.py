import asyncio
from typing import List
import aiohttp
import anyio

from bs4 import BeautifulSoup

from ii_agent_tools.integrations.web_visit.utils import (
    clean_soup,
    extract_title,
    get_text_from_soup,
)
from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitResult,
    WebVisitError,
)


class BeautifulSoupWebVisitClient(BaseWebVisitClient):
    async def extract(self, url: str) -> WebVisitResult:
        """Extract content from a webpage using BeautifulSoup."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response.raise_for_status()
                    html_content = await response.text()
                    encoding = response.charset or "utf-8"

            def _parse_html() -> tuple[str, str]:
                soup = BeautifulSoup(html_content, "lxml", from_encoding=encoding)
                soup = clean_soup(soup)
                return get_text_from_soup(soup), extract_title(soup)

            content, title = await anyio.to_thread.run_sync(_parse_html)

            formatted_content = f"Title: {title}\n\nContent: {content}"

            return WebVisitResult(
                content=formatted_content,
                cost=0.0,  # BeautifulSoup has no API cost
            )

        except Exception as e:
            raise WebVisitError(f"BeautifulSoup extraction error: {str(e)}")

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Extract content from multiple webpages."""
        tasks = [self.extract(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=sum(result.cost for result in results),
        )
