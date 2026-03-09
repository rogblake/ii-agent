"""OpenAI-backed client for prompt enhancement."""

from __future__ import annotations

import json
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


class _EnhancePromptPayload(BaseModel):
    """Structured model output expected from the LLM."""

    enhanced_prompt: str
    reasoning: str | None = None


class OpenAIEnhancePromptClient:
    """Prompt enhancer backed by the OpenAI Responses API."""

    def __init__(self, config: EnhancePromptConfig):
        self._config = config
        self._client = AsyncOpenAI(api_key=config.openai_api_key)

    async def enhance(
        self,
        prompt: str,
        context: str | None = None,
    ) -> EnhancePromptResult:
        """Enhance a prompt while preserving user intent."""
        response = await self._client.responses.create(
            model=self._config.model,
            instructions=(
                "You improve prompts for downstream AI assistants. "
                "Preserve the user's intent, add useful specificity, and use supplied "
                "context when present. Return JSON with keys "
                "`enhanced_prompt` and `reasoning`. "
                "`reasoning` must be a short explanation, not chain-of-thought."
            ),
            input=_build_input_text(prompt, context),
            max_output_tokens=self._config.max_tokens,
        )

        payload = _EnhancePromptPayload.model_validate(
            _extract_json_payload(response.output_text)
        )

        return EnhancePromptResult(
            original_prompt=prompt,
            enhanced_prompt=payload.enhanced_prompt,
            reasoning=payload.reasoning,
        )


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
        return f"Prompt:\n{prompt}\n\nContext:\n{context}"
    return f"Prompt:\n{prompt}"


def _extract_json_payload(output_text: str) -> dict[str, object]:
    """Parse the first JSON object from the model output."""
    raw = output_text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end < start:
            logger.error("Enhance prompt response did not contain valid JSON")
            raise
        return json.loads(raw[start : end + 1])
