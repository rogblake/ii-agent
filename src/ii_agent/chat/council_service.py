"""Council service - parallel LLM execution engine for Model Council feature."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List

from ii_agent.chat.types import (
    EventType,
    Message,
    TextContent,
    MessageRole,
    CouncilPreferences,
)
from ii_agent.chat.llm import LLMProviderFactory
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.redis import cancel

logger = logging.getLogger(__name__)

# Sentinel value to signal the end of council member outputs
_SENTINEL = object()

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
        messages: List[Message],
        user_question: str,
        council_preferences: CouncilPreferences,
        llm_configs: Dict[str, LLMConfig],
        model_names: Dict[str, str],
        run_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run council models in parallel, then synthesize.

        Yields dict events:
          - council_member_start / council_member_delta / council_member_complete / council_member_error
          - council_synthesis_start / council_synthesis_delta / council_synthesis_complete
          - Standard content events for the synthesis phase

        Args:
            messages: Conversation context messages (user + history)
            user_question: The raw user question text
            council_preferences: Council config with model list and synthesis model
            llm_configs: Map of model_id -> LLMConfig for each council model + synthesis
            model_names: Map of model_id -> display name
            run_id: Run ID for cancellation tracking
        """
        cls.validate_preferences(council_preferences)

        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        tasks: List[asyncio.Task] = []
        council_had_error = False
        member_outputs: Dict[str, str] = {}  # model_id -> collected content

        async def run_single_model(model_id: str, config: LLMConfig) -> None:
            """Execute a single council member model with streaming."""
            nonlocal council_had_error
            display_name = model_names.get(model_id, model_id)
            session_id = messages[-1].session_id or "" if messages else ""

            try:
                await queue.put({
                    "type": "council_member_start",
                    "model_id": model_id,
                    "model_name": display_name,
                })

                provider = LLMProviderFactory.create_provider(config)
                collected_content = ""

                async def _stream_model() -> str:
                    nonlocal collected_content
                    async for event in provider.stream(
                        messages=messages,
                        session_id=session_id,
                        tools=[],
                    ):
                        if event.type == EventType.CONTENT_DELTA and event.content:
                            collected_content += event.content
                            await queue.put({
                                "type": "council_member_delta",
                                "model_id": model_id,
                                "model_name": display_name,
                                "delta": event.content,
                            })
                    return collected_content

                content = await asyncio.wait_for(
                    _stream_model(),
                    timeout=COUNCIL_MODEL_TIMEOUT,
                )

                member_outputs[model_id] = content

                await queue.put({
                    "type": "council_member_complete",
                    "model_id": model_id,
                    "model_name": display_name,
                    "content": content,
                })

            except asyncio.TimeoutError:
                council_had_error = True
                # Still save partial content if we got some before timeout
                if collected_content:
                    member_outputs[model_id] = collected_content
                logger.warning(f"Council model {model_id} timed out after {COUNCIL_MODEL_TIMEOUT}s")
                await queue.put({
                    "type": "council_member_error",
                    "model_id": model_id,
                    "model_name": display_name,
                    "error": f"Model timed out after {COUNCIL_MODEL_TIMEOUT}s",
                })
            except Exception as e:
                council_had_error = True
                # Save partial content if we got some before the error
                if collected_content:
                    member_outputs[model_id] = collected_content
                logger.error(f"Council model {model_id} failed: {e}", exc_info=True)
                await queue.put({
                    "type": "council_member_error",
                    "model_id": model_id,
                    "model_name": display_name,
                    "error": str(e),
                })

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
                # Cancellation checkpoint 1: during parallel execution
                await cancel.raise_if_cancelled(run_id)

                # Check for completed tasks
                done, pending_tasks = await asyncio.wait(
                    pending_tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )

                # Drain all queued events
                while not queue.empty():
                    event = queue.get_nowait()
                    yield event

            # Final drain after all tasks complete
            while not queue.empty():
                event = queue.get_nowait()
                yield event

            # Cancellation checkpoint 2: before synthesis
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

            # Build synthesis prompt
            model_output_sections = []
            for idx, (mid, content) in enumerate(member_outputs.items(), 1):
                name = model_names.get(mid, mid)
                model_output_sections.append(
                    f"<model_response_{idx} model=\"{name}\">\n{content}\n</model_response_{idx}>"
                )

            synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
                user_question=user_question,
                model_outputs="\n\n".join(model_output_sections),
            )

            synthesis_message = Message(
                id=messages[-1].id,  # Reuse message ID
                role=MessageRole.USER,
                parts=[TextContent(text=synthesis_prompt)],
                session_id=messages[-1].session_id,
                created_at=messages[-1].created_at,
                updated_at=messages[-1].updated_at,
            )

            yield {"type": "council_synthesis_start", "model_id": synthesis_model_id}

            synthesis_provider = LLMProviderFactory.create_provider(synthesis_config)
            synthesis_content = ""

            session_id = messages[-1].session_id or ""
            async for event in synthesis_provider.stream(
                messages=[synthesis_message],
                session_id=session_id,
                tools=[],
            ):
                # Cancellation checkpoint 3: during synthesis streaming
                await cancel.raise_if_cancelled(run_id)

                if event.type == EventType.CONTENT_DELTA and event.content:
                    synthesis_content += event.content
                    yield {
                        "type": "council_synthesis_delta",
                        "model_id": synthesis_model_id,
                        "delta": event.content,
                    }

            yield {
                "type": "council_synthesis_complete",
                "model_id": synthesis_model_id,
                "content": synthesis_content,
            }

            # Yield final result metadata
            yield {
                "type": "council_result",
                "member_outputs": member_outputs,
                "synthesis_content": synthesis_content,
                "synthesis_model_id": synthesis_model_id,
                "model_names": model_names,
                "had_error": council_had_error,
            }

        finally:
            # Cleanup: cancel any orphaned tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
