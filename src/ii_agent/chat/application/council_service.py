"""Council service - parallel LLM execution engine for Model Council feature."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List

from ii_agent.chat.types import (
    Message,
    TextContent,
    MessageRole,
    CouncilPreferences,
)
from ii_agent.chat.llm import get_client
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.redis import cancel

logger = logging.getLogger(__name__)

COUNCIL_MODEL_TIMEOUT = 180  # seconds per model
MIN_COUNCIL_MODELS = 2
MAX_COUNCIL_MODELS = 10

SYNTHESIS_PROMPT_TEMPLATE = """You are a synthesis assistant. The user asked the following question:

<user_question>
{user_question}
</user_question>

Multiple AI models have provided their responses. Please synthesize these into a single, comprehensive, well-structured answer that combines the best insights from all responses.

{model_outputs}

Instructions:
- Combine the key insights from all model responses into a unified answer
- Resolve any contradictions by using your best judgment
- Maintain accuracy and completeness
- Use clear, well-organized formatting
- Do NOT mention the individual models or say "Model X said..."
- Write the response as if you are directly answering the user's question"""


def _extract_text(content) -> str:
    """Extract plain text from a list of content parts or a raw string."""
    if isinstance(content, str):
        return content
    return "".join(p.text for p in content if isinstance(p, TextContent))


class CouncilService:
    """Parallel execution engine for Model Council feature.

    Runs multiple LLMs in parallel, collects their outputs,
    then produces a synthesized response from a designated synthesis model.
    """

    @classmethod
    def validate_preferences(cls, preferences: CouncilPreferences) -> None:
        """Validate council preferences. Raises ValueError on invalid config."""
        if not preferences.enabled:
            raise ValueError("Council mode is not enabled")

        num_models = len(preferences.council_models)
        if num_models < MIN_COUNCIL_MODELS:
            raise ValueError(
                f"Council requires at least {MIN_COUNCIL_MODELS} models, got {num_models}"
            )
        if num_models > MAX_COUNCIL_MODELS:
            raise ValueError(
                f"Council supports at most {MAX_COUNCIL_MODELS} models, got {num_models}"
            )

        if not preferences.synthesis_model_id:
            raise ValueError("Synthesis model ID is required")

    @classmethod
    async def stream_council_response(
        cls,
        *,
        user_id: str,
        messages: List[Message],
        user_question: str,
        council_preferences: CouncilPreferences,
        llm_configs: Dict[str, LLMConfig],
        model_names: Dict[str, str],
        run_id: str,
        session_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run council models in parallel, then synthesize.

        Yields dict events:
          - council_member_start / council_member_complete / council_member_error
          - council_synthesis_start / council_synthesis_complete
          - council_result with final metadata
        """
        cls.validate_preferences(council_preferences)

        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        tasks: List[asyncio.Task] = []
        council_had_error = False
        member_outputs: Dict[str, str] = {}  # model_id -> collected content

        async def run_single_model(model_id: str, config: LLMConfig) -> None:
            nonlocal council_had_error
            display_name = model_names.get(model_id, model_id)

            try:
                await queue.put(
                    {
                        "type": "council_member_start",
                        "model_id": model_id,
                        "model_name": display_name,
                    }
                )

                client = get_client(config)

                async def _call() -> str:
                    response = await client.send(messages=messages)
                    return _extract_text(response.content)

                content = await asyncio.wait_for(_call(), timeout=COUNCIL_MODEL_TIMEOUT)
                member_outputs[model_id] = content

                await queue.put(
                    {
                        "type": "council_member_complete",
                        "model_id": model_id,
                        "model_name": display_name,
                        "content": content,
                    }
                )

            except asyncio.TimeoutError:
                council_had_error = True
                logger.warning(f"Council model {model_id} timed out after {COUNCIL_MODEL_TIMEOUT}s")
                await queue.put(
                    {
                        "type": "council_member_error",
                        "model_id": model_id,
                        "model_name": display_name,
                        "error": f"Model timed out after {COUNCIL_MODEL_TIMEOUT}s",
                    }
                )
            except Exception as e:
                council_had_error = True
                logger.error(f"Council model {model_id} failed: {e}", exc_info=True)
                await queue.put(
                    {
                        "type": "council_member_error",
                        "model_id": model_id,
                        "model_name": display_name,
                        "error": str(e),
                    }
                )

        try:
            # Phase 1: Launch all council models in parallel
            for model_config in council_preferences.council_models:
                mid = model_config.model_id
                config = llm_configs.get(mid)
                if not config:
                    logger.warning(f"No LLM config for council model {mid}, skipping")
                    continue
                task = asyncio.create_task(run_single_model(mid, config))
                tasks.append(task)

            # Monitor task completion and drain queue
            pending_tasks = set(tasks)

            while pending_tasks:
                await cancel.raise_if_cancelled(run_id)

                _, pending_tasks = await asyncio.wait(
                    pending_tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )

                while not queue.empty():
                    yield queue.get_nowait()

            # Final drain after all tasks complete
            while not queue.empty():
                yield queue.get_nowait()

            await cancel.raise_if_cancelled(run_id)

            # Phase 2: Synthesis
            if not member_outputs:
                yield {
                    "type": "council_synthesis_error",
                    "error": "No council member produced output",
                }
                return

            synthesis_model_id = council_preferences.synthesis_model_id
            synthesis_config = llm_configs.get(synthesis_model_id)
            if not synthesis_config:
                yield {
                    "type": "council_synthesis_error",
                    "error": f"No config for synthesis model: {synthesis_model_id}",
                }
                return

            model_output_sections = []
            for idx, (mid, content) in enumerate(member_outputs.items(), 1):
                name = model_names.get(mid, mid)
                model_output_sections.append(
                    f'<model_response_{idx} model="{name}">\n{content}\n</model_response_{idx}>'
                )

            synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
                user_question=user_question,
                model_outputs="\n\n".join(model_output_sections),
            )

            synthesis_message = Message(
                id=messages[-1].id,
                role=MessageRole.USER,
                parts=[TextContent(text=synthesis_prompt)],
                session_id=messages[-1].session_id,
                created_at=messages[-1].created_at,
                updated_at=messages[-1].updated_at,
            )

            yield {"type": "council_synthesis_start", "model_id": synthesis_model_id}

            synthesis_client = get_client(synthesis_config)
            synthesis_response = await synthesis_client.send(messages=[synthesis_message])
            synthesis_content = _extract_text(synthesis_response.content)

            yield {
                "type": "council_synthesis_complete",
                "model_id": synthesis_model_id,
                "content": synthesis_content,
            }

            yield {
                "type": "council_result",
                "member_outputs": member_outputs,
                "synthesis_content": synthesis_content,
                "synthesis_model_id": synthesis_model_id,
                "model_names": model_names,
                "had_error": council_had_error,
            }

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
