from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.engine.v1.models.anthropic.claude import Claude
from ii_agent.engine.v1.models.base import Model
from ii_agent.engine.v1.models.custom import OpenAIChatCustom
from ii_agent.engine.v1.models.google import Gemini, GeminiInteractions
from ii_agent.engine.v1.models.openai import OpenAIResponses
from ii_agent.engine.types import Provider
from ii_agent.engine.v1.models.vertexai.claude import Claude as VertexAIClaude


def get_model(model_provider: Provider, llm_config: LLMConfig, **kwargs) -> Model:
    # Extended thinking requires minimum 1024 tokens (matching chat system)
    api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None
    if model_provider == Provider.ANTHROPIC and llm_config.vertex_project_id is None:
        betas = []
        thinking_config = {
            "type": "enabled",
            "budget_tokens": 16_000,
        }
        # Add interleaved thinking beta for extended thinking with tools
        betas.append("interleaved-thinking-2025-05-14")

        # Prepare client_params for custom base_url if provided
        client_params = {}
        if llm_config.base_url:
            client_params["base_url"] = llm_config.base_url

        return Claude(
            id=llm_config.model,
            api_key=api_key,
            temperature=llm_config.temperature,
            thinking=thinking_config,
            max_tokens=32_000,
            betas=betas if betas else None,
            cache_conversation=True,
            cache_system_prompt=True,
            retries=llm_config.max_retries,
            extended_cache_time=False,
            timeout=600.0,
            client_params=client_params if client_params else None,
        )

    elif model_provider == Provider.GOOGLE:
        is_vertex = bool(llm_config.vertex_project_id)
        if is_vertex:
            return Gemini(
                api_key=api_key,
                id=llm_config.model,
                temperature=llm_config.temperature,
                retries=llm_config.max_retries,
                include_thoughts=True,
                thinking_level="high",
                vertexai=True,
                max_output_tokens=llm_config.max_message_chars,
                project_id=llm_config.vertex_project_id,
                location=llm_config.vertex_region,
            )
        else:
            return GeminiInteractions(
                api_key=api_key,
                id=llm_config.model,
                temperature=llm_config.temperature,
                retries=llm_config.max_retries,
                thinking_summaries="auto",
                thinking_level="high",
                vertexai=is_vertex,
                timeout=600.0,
                max_output_tokens=llm_config.max_message_chars,
                project_id=llm_config.vertex_project_id,
                location=llm_config.vertex_region,
            )

    elif model_provider == Provider.OPENAI:
        return OpenAIResponses(
            api_key=api_key,
            id=llm_config.model,
            parallel_tool_calls=True,
            max_retries=llm_config.max_retries,
            base_url=llm_config.base_url,
            max_output_tokens=64_000,
            timeout=600.0,
            reasoning={"effort": "medium", "summary": "auto"},
        )

    elif (
        model_provider == Provider.ANTHROPIC and llm_config.vertex_project_id is not None
    ) or model_provider == Provider.VERTEX_AI:
        thinking_config = {
            "type": "enabled",
            "budget_tokens": 16_000,
        }
        betas = []
        betas.append("interleaved-thinking-2025-05-14")

        # Prepare client_params for custom base_url if provided
        client_params = {}
        if llm_config.base_url:
            client_params["base_url"] = llm_config.base_url

        return VertexAIClaude(
            id=llm_config.model,
            api_key=api_key,
            project_id=llm_config.vertex_project_id,
            region=llm_config.vertex_region,
            temperature=llm_config.temperature,
            betas=betas,
            timeout=600.0,
            thinking=thinking_config,
            cache_conversation=True,
            retries=llm_config.max_retries,
            base_url=llm_config.base_url,
            max_tokens=32_000,
            cache_system_prompt=True,
            extended_cache_time=False,
            client_params=client_params if client_params else None,
        )

    else:
        return OpenAIChatCustom(
            api_key=api_key,
            provider=Provider.CUSTOM,
            id=llm_config.model,
            max_retries=llm_config.max_retries,
            base_url=llm_config.base_url,
            max_completion_tokens=64_000,
            timeout=600.0,
            reasoning_effort="high",
        )
