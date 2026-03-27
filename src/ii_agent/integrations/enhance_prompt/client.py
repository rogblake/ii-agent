"""OpenAI-backed client for prompt enhancement."""

from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.types import BillingContextValue, BillingScope
from ii_agent.chat.types import MessageRole, TextContent
from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.llm.execution_service import LLMBillingContext, LLMExecutionService
from ii_agent.core.logger import logger
from ii_agent.core.request_context import get_or_generate_request_id


class EnhancePromptResult(BaseModel):
    """Normalized result returned by prompt-enhancement clients."""

    original_prompt: str
    enhanced_prompt: str
    reasoning: str | None = None


class EnhancePromptClient(Protocol):
    """Protocol for prompt-enhancement providers."""

    async def enhance(
        self,
        prompt: str,
        context: str | None = None,
    ) -> EnhancePromptResult:
        """Enhance the supplied prompt."""


class OpenAIEnhancePromptClient:
    """Prompt enhancer backed by the OpenAI Responses API."""

    def __init__(self, config: EnhancePromptConfig):
        self._config = config
        self._client = AsyncOpenAI(api_key=config.openai_api_key)
        self._billing_db: AsyncSession | None = None
        self._llm_execution_service: LLMExecutionService | None = None
        self._user_id: str | None = None

    def bind_execution_context(
        self,
        *,
        db: AsyncSession,
        llm_execution_service: LLMExecutionService,
        user_id: str,
    ) -> "OpenAIEnhancePromptClient":
        """Attach billing context for one authenticated enhancement request."""
        self._billing_db = db
        self._llm_execution_service = llm_execution_service
        self._user_id = user_id
        return self

    async def enhance(
        self,
        prompt: str,
        context: str | None = None,
    ) -> EnhancePromptResult:
        """Enhance a prompt while preserving user intent."""
        enhanced_prompt = (await self._run_prompt_enhancement(prompt, context)).strip()
        if not enhanced_prompt:
            logger.warning(
                "Enhance prompt provider returned empty output; falling back to original prompt."
            )
            enhanced_prompt = prompt

        return EnhancePromptResult(
            original_prompt=prompt,
            enhanced_prompt=enhanced_prompt,
        )

    async def _run_prompt_enhancement(self, prompt: str, context: str | None) -> str:
        if (
            self._llm_execution_service is not None
            and self._billing_db is not None
            and self._user_id is not None
        ):
            llm_config = _build_openai_llm_config(
                model=self._config.model,
                api_key=self._config.openai_api_key,
            )
            client = self._llm_execution_service.create_client(llm_config)
            messages = [
                self._llm_execution_service.new_message(
                    role=MessageRole.SYSTEM,
                    session_id=self._user_id,
                    parts=[TextContent(text=_ENHANCE_PROMPT_SYSTEM_PROMPT)],
                ),
                self._llm_execution_service.new_message(
                    role=MessageRole.USER,
                    session_id=self._user_id,
                    parts=[TextContent(text=_build_input_text(prompt, context))],
                ),
            ]
            response = await self._llm_execution_service.send_once(
                client=client,
                messages=messages,
                billing_context=LLMBillingContext(
                    scope=BillingScope.for_user(
                        user_id=self._user_id,
                        app_kind="chat",
                        billing_context=BillingContextValue.ENHANCE_PROMPT,
                    ),
                    llm_config=llm_config,
                    model_id=llm_config.model,
                    requested_output_token_cap=self._config.max_tokens,
                ),
                usage_key=f"enhance_prompt:{self._user_id}:{get_or_generate_request_id()}",
            )
            if isinstance(response.content, list):
                return self._llm_execution_service.extract_text_content(response.content)
            return str(response.content or "")

        response = await self._client.responses.create(
            model=self._config.model,
            instructions=_ENHANCE_PROMPT_SYSTEM_PROMPT,
            input=_build_input_text(prompt, context),
            max_output_tokens=self._config.max_tokens,
        )
        return response.output_text


def create_enhance_prompt_client(
    config: EnhancePromptConfig,
) -> EnhancePromptClient | None:
    """Create the configured prompt-enhancement client, if available."""
    if not config.openai_api_key:
        return None

    return OpenAIEnhancePromptClient(config)


def _build_input_text(prompt: str, context: str | None) -> str:
    """Build the user input sent to the provider."""
    if context:
        return (
            f"Enhance this request into a detailed prompt: {prompt}\n\n"
            f"Additional context - {context}"
        )
    return f"Enhance this request into a detailed prompt: {prompt}"


_ENHANCE_PROMPT_SYSTEM_PROMPT = (
    "Return only the enhanced prompt text. Do not add explanations, labels, or quotes."
)


def _build_openai_llm_config(*, model: str, api_key: str | None) -> LLMConfig:
    return LLMConfig(
        model=model,
        api_key=SecretStr(api_key) if api_key else None,
        api_type=APITypes.OPENAI,
        config_type="system",
    )
