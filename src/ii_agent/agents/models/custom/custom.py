from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from ii_agent.agents.models.openai.completions import OpenAIChat


@dataclass
class OpenAIChatCustom(OpenAIChat):
    """
    A class for to interact with any provider using the OpenAI API schema.

    Args:
        id (str): The id of the OpenAI model to use. Defaults to "not-provided".
        name (str): The name of the OpenAI model to use. Defaults to "OpenAILike".
        api_key (Optional[str]): The API key to use. Defaults to "not-provided".
    """

    id: str = "not-provided"
    name: str = "CustomOpenAILike"
    api_key: Optional[str] = "not-provided"

    default_role_map = {
        "system": "system",
        "user": "user",
        "assistant": "assistant",
        "tool": "tool",
    }

    # Parameters not supported by most OpenAI-compatible providers (Ollama, vLLM, etc.)
    _UNSUPPORTED_PARAMS = {
        "reasoning_effort",
        "store",
        "verbosity",
        "service_tier",
        "metadata",
    }

    def get_request_params(
        self,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        run_response=None,
    ) -> Dict[str, Any]:
        """Strip parameters unsupported by generic OpenAI-compatible providers."""
        params = super().get_request_params(
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            run_response=run_response,
        )
        for key in self._UNSUPPORTED_PARAMS:
            params.pop(key, None)
        return params
