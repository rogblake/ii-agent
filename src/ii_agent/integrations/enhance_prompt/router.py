"""Enhance prompt API endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.core.config.settings import get_settings
from ii_agent.core.llm.dependencies import LLMExecutionServiceDep
from ii_agent.integrations.enhance_prompt.client import create_enhance_prompt_client

router = APIRouter(prefix="/enhance-prompt", tags=["Enhance Prompt"])


class EnhancePromptRequest(BaseModel):
    """Request payload for prompt enhancement."""

    prompt: str
    context: str | None = None


class EnhancePromptResponse(BaseModel):
    """Response payload for prompt enhancement."""

    original_prompt: str
    enhanced_prompt: str
    reasoning: str | None = None


@router.post("", response_model=EnhancePromptResponse)
async def enhance_prompt(
    request: EnhancePromptRequest,
    db: DBSession,
    llm_execution_service: LLMExecutionServiceDep,
    _current_user: CurrentUser,
) -> EnhancePromptResponse:
    """Enhance a prompt for better AI responses."""
    client = create_enhance_prompt_client(get_settings().enhance_prompt)
    if client is None:
        return EnhancePromptResponse(
            original_prompt=request.prompt,
            enhanced_prompt=request.prompt,
            reasoning="No enhance prompt provider configured",
        )

    if hasattr(client, "bind_execution_context"):
        client = client.bind_execution_context(
            db=db,
            llm_execution_service=llm_execution_service,
            user_id=str(_current_user.id),
        )

    result = await client.enhance(request.prompt, request.context)
    return EnhancePromptResponse(
        original_prompt=result.original_prompt,
        enhanced_prompt=result.enhanced_prompt,
        reasoning=result.reasoning,
    )
