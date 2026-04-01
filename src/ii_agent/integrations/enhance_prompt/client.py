"""OpenAI-backed client for prompt enhancement."""

from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig
from ii_agent.core.logger import logger


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

    def __init__(self, config: EnhancePromptConfig) -> None:
        self._config = config
        self._client = AsyncOpenAI(api_key=config.openai_api_key)

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
