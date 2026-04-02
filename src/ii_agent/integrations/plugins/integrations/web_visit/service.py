import asyncio
from typing import List

from ii_agent_tools.logger import get_logger
from ii_agent_tools.integrations.web_visit import utils
from ii_agent_tools.llm.client import LLMClient
from ii_agent_tools.integrations.web_visit.factory import create_web_visit_client
from ii_agent_tools.integrations.web_visit.base import (
    WebVisitResult,
    WebVisitError,
    WebVisitServiceType,
)
from ii_agent_tools.integrations.web_visit.config import WebVisitConfig

logger = get_logger(__name__)


class WebVisitService:
    def __init__(self, llm_client: LLMClient | None, web_visit_config: WebVisitConfig):
        self.llm_client = llm_client
        self.web_visit_config = web_visit_config

    async def visit(
        self,
        url: str,
        prompt: str | None = None,
        service_type: WebVisitServiceType | None = None,
    ) -> WebVisitResult:
        client_type = service_type or "firecrawl"
        logger.info(
            "Attempting web visit with client type",
            extra={"client_type": client_type, "url": url},
        )
        try:
            client = create_web_visit_client(self.web_visit_config, client_type)
            raw_content = await client.extract(url)
        except WebVisitError as e:
            logger.warning(
                "Web visit client failed",
                extra={"client_type": client_type, "url": url, "error": str(e)},
            )
            raise
        except Exception as e:
            logger.exception(
                "Web visit client failed with unexpected error",
                extra={"client_type": client_type, "url": url, "error": str(e)},
            )
            raise WebVisitError("Web visit client failed") from e

        cost = raw_content.cost
        final_content = f"URL: {url}\n"
        final_content += f"Content: {raw_content.content}\n"
        final_content += "-----------------------------------\n"
        if not prompt or not self.llm_client:
            return WebVisitResult(
                content=final_content,
                cost=cost,
            )

        # process the content with prompt
        formatted_prompt = utils.get_visit_webpage_prompt(raw_content.content, prompt)
        try:
            llm_processed = await self.llm_client.generate(formatted_prompt)
            llm_processed_content = llm_processed.content
        except Exception as e:
            logger.exception(
                "LLM processing failed during web visit",
                extra={"url": url, "error": str(e)},
            )
            raise WebVisitError("Failed to process visited content with LLM")

        final_content = f"URL: {url}\n"
        final_content += f"Content: {llm_processed_content}\n"
        final_content += "-----------------------------------\n"
        llm_processed_cost = llm_processed.cost
        return WebVisitResult(
            content=final_content,
            cost=cost + llm_processed_cost,
        )

    async def batch_visit(
        self,
        urls: List[str],
        query: str,
        service_type: WebVisitServiceType | None = None,
    ) -> WebVisitResult:
        tasks = [self.visit(url, query, service_type) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=sum(result.cost for result in results),
        )
