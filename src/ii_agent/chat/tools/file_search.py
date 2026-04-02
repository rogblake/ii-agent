import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from openai import AsyncOpenAI
from openai.types.shared_params.comparison_filter import ComparisonFilter
from openai.types.shared_params.compound_filter import CompoundFilter
from ii_agent.chat.types import ErrorTextContent, JsonResultContent
from ii_agent.core.db import get_db_session_local
from ii_agent.settings.llm.repository import ModelSettingRepository
from ii_agent.settings.llm.schemas import ModelConfig

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse

logger = logging.getLogger(__name__)


_FILE_SEARCH_COST_PER_CALL = 0.0025  # OpenAI vector search: ~$2.50 per 1000 searches


class FileSearchTool(BaseTool):
    """Search uploaded documents using OpenAI's Vector Store API."""

    max_cost_usd = 0.01

    def __init__(
        self,
        session_id: uuid.UUID,
        vector_store_id: str,
        user_id: uuid.UUID,
    ):
        self._llm_config: ModelConfig | None = None
        self._client: AsyncOpenAI | None = None
        self.vector_store_id = vector_store_id
        self.session_id = session_id
        self.user_id = user_id
        self._name = "file_search"

    async def _get_client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client from the DB system config."""
        if self._client is None:
            model_setting_repo = ModelSettingRepository()
            async with get_db_session_local() as db:
                self._llm_config = await model_setting_repo.find_system_model_by_provider(
                    db, provider="openai"
                )
            self._client = AsyncOpenAI(
                api_key=self._llm_config.api_key.get_secret_value()
                if self._llm_config.api_key
                else "",
                base_url=self._llm_config.base_url or None,
            )
        return self._client

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description=(
                "Search through uploaded documents and files to find relevant information, "
                "extract specific details, or answer questions based on file contents. "
                "Uses semantic search to understand context and meaning.\n\n"
                "Supported file formats:\n"
                "- Documents: .pdf, .docx, .txt, .md, .rtf\n"
                "- Other: .tex, .pptx\n\n"
                "Use this for:\n"
                "- Finding specific information within documents\n"
                "- Answering questions about uploaded file contents\n"
                "- Extracting relevant passages or data points\n"
                "- Summarizing sections of documents\n"
                "- Comparing information across multiple files\n"
                "- Locating code snippets or functions\n"
                "- Cross-referencing details from different documents"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A clear search query or question about the uploaded files. "
                            "Be specific about what information you're looking for. "
                            "Examples:\n"
                            "- 'What is the total revenue mentioned in the Q3 report?'\n"
                            "- 'Find all references to the authentication system'\n"
                            "- 'What are the key findings in the research paper?'\n"
                            "- 'List all API endpoints defined in the documentation'\n"
                            "- 'What does the contract say about termination clauses?'\n"
                            "- 'Find the implementation of the login function'\n"
                            "- 'Compare the pricing models mentioned in both documents'"
                        ),
                    },
                    "file_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of specific file names to search within. "
                            "Use this to narrow the search scope to particular files when you know "
                            "which documents contain the relevant information. "
                            "Examples:\n"
                            "- ['contract.pdf', 'amendment.pdf'] - Search in contract and its amendment\n"
                            "- ['api_docs.md'] - Search only in API documentation"
                        ),
                    },
                },
            },
            required=["query"],
        )

    def _build_filters(self, file_names: List[str] | None = None) -> CompoundFilter:
        """Build compound filters for the file search request."""
        time_cutoff = datetime.now(timezone.utc).timestamp() - 24 * 60 * 60  # last 24 hours

        logger.debug(
            f"Building filters with time_cutoff: {time_cutoff} (24h ago from {datetime.now(timezone.utc).timestamp()})"
        )

        filters: list[ComparisonFilter] = [
            {
                "type": "eq",
                "key": "session_id",
                "value": self.session_id,
            },
            {
                "type": "eq",
                "key": "user_id",
                "value": self.user_id,
            },
        ]
        # if file_names:
        #     filters.append(
        #         {
        #             "type": "in",
        #             "key": "file_name",
        #             "value": file_names,
        #         }
        #     )

        logger.debug(f"Filters built: {filters}")
        return {
            "type": "and",
            "filters": filters,
        }

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        """Execute code using OpenAI Responses API with code interpreter."""
        try:
            params = json.loads(tool_call.input)
            query = params["query"]
            file_names = params.get("file_names")  # Optional parameter
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            # Get files from parent message
            filters = self._build_filters(file_names=file_names)
            client = await self._get_client()
            response = await client.vector_stores.search(
                vector_store_id=self.vector_store_id,
                query=query,
                filters=filters,
                max_num_results=10,
                ranking_options={"ranker": "auto"},
            )
            search_results = response.data
            if isinstance(search_results, list):
                results = [m.model_dump() for m in search_results]
            else:
                results = search_results.model_dump()

            return ToolResponse(
                output=JsonResultContent(value=results),
                cost_usd=_FILE_SEARCH_COST_PER_CALL,
            )

        except Exception as e:
            logger.error(f"File search error: {e}", exc_info=True)
            return ToolResponse(output=ErrorTextContent(value=f"File search failed: {str(e)}"))
