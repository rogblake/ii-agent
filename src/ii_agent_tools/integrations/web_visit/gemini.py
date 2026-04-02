import asyncio
import logging
from typing import List

from google import genai
from google.genai.types import GenerateContentConfig

from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitError,
    WebVisitResult,
)

logger = logging.getLogger(__name__)


class GeminiWebVisitClient(BaseWebVisitClient):
    """Gemini web visit client using Google's genai library."""

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model_id = model_id
        self.tools = [{"url_context": {}}, {"google_search": {}}]

    async def extract(self, url: str) -> WebVisitResult:
        """Extract content from a webpage using Gemini."""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=f"Please extract and provide the main content from this URL: {url}",
                config=GenerateContentConfig(
                    tools=self.tools,
                ),
            )

            content_parts = []
            if (
                not response.candidates
                or not response.candidates[0].content
                or not response.candidates[0].content.parts
            ):
                raise WebVisitError("No candidates found in response")

            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content_parts.append(part.text)

            return WebVisitResult(
                content="\n".join(content_parts),
                cost=0,
            )

        except Exception as e:
            logger.error(f"Gemini web visit error for {url}: {e}")
            raise WebVisitError(f"Failed to extract content from {url}: {str(e)}")

    def _token_to_cost(self, input_tokens_count: int, output_tokens_count: int) -> float:
        return input_tokens_count * 0.3 / 1_000_000 + output_tokens_count * 2.5 / 1_000_000

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Extract content from a webpage and compress it using Gemini with context compression."""
        try:
            tasks = [self.extract(url) for url in urls]
            results = await asyncio.gather(*tasks)
            return WebVisitResult(
                content="\n".join(result.content for result in results),
                cost=0,
            )
        except Exception as e:
            logger.error(f"Gemini web visit error for {urls}: {e}")
            raise WebVisitError(f"Failed to extract content from {urls}: {str(e)}")
