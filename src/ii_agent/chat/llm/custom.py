from datetime import datetime
import json
import logging
from copy import deepcopy
from typing import Any, AsyncIterator, Dict, List, Optional

from litellm import acompletion

from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.types import (
    ImageUrlContentPart,
    MessageRole,
    ToolCall,
    FinishReason,
    TextContent,
    BinaryContent,
    ImageURLContent,
    TextResultContent,
    JsonResultContent,
    ExecutionDeniedContent,
    ErrorTextContent,
    ErrorJsonContent,
    ArrayResultContent,
    StorybookProgressContent,
    StorybookResultContent,
    TextContentPart,
    ImageDataContentPart,
    FileDataContentPart,
    RunResponseEvent,
    RunResponseOutput,
    EventType,
)
from ii_agent.chat.base import (
    LLMClient,
)
from ii_agent.chat.types import Message
from ii_agent.chat.prompts.custom_system_prompt import template

logger = logging.getLogger(__name__)


class CustomProvider(LLMClient):
    """Provider for other models that use openai compatible API. Use litellm"""

    def __init__(self, llm_config: ModelConfig):
        dummy_llm_config = deepcopy(llm_config)
        if llm_config.provider == Provider.GOOGLE:
            dummy_llm_config.model_id = f"gemini/{dummy_llm_config.model_id}"
            dummy_llm_config.provider = Provider.CUSTOM
        self.llm_config = dummy_llm_config
        self.model_name = dummy_llm_config.model_id
        self.base_url = dummy_llm_config.base_url

        self.api_key = (
            dummy_llm_config.api_key.get_secret_value() if dummy_llm_config.api_key else None
        )

        if "/" in self.model_name:
            self.provider_prefix = self.model_name.split("/")[0]
        else:
            self.provider_prefix = "custom"

        logger.info(
            f"Initialized CustomProvider for model: {self.model_name} "
            f"(provider: {self.provider_prefix})"
        )

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert Message objects to OpenAI-compatible format for litellm."""
        converted_messages = []
        for message in messages:
            role = message.role.value

            if role == MessageRole.TOOL.value:
                for tool_result in message.tool_results():
                    output = tool_result.output
                    content_value = None

                    # Handle different output types using isinstance
                    if isinstance(output, (TextResultContent, ErrorTextContent)):
                        content_value = output.value
                    elif isinstance(output, ExecutionDeniedContent):
                        content_value = output.reason or "Tool execution denied."
                    elif isinstance(output, (JsonResultContent, ErrorJsonContent)):
                        content_value = json.dumps(output.value)
                    elif isinstance(output, ArrayResultContent):
                        # For OpenAI-compatible APIs, convert array content to string
                        parts = []
                        for item in output.value:
                            if isinstance(item, TextContentPart):
                                parts.append(item.text)
                            elif isinstance(item, ImageDataContentPart):
                                parts.append(f"[Image: {item.media_type}]")
                            elif isinstance(item, FileDataContentPart):
                                parts.append(f"[File: {item.filename or 'data'}]")
                            elif isinstance(item, ImageUrlContentPart):
                                parts.append(f"[Image URL: {item.url}]")
                            else:
                                logger.warning(f"Unsupported tool content part type: {item.type}")
                        content_value = "\n".join(parts)
                    elif isinstance(output, StorybookProgressContent):
                        progress_info = {
                            "type": "storybook_progress",
                            "storybook_id": output.storybook_id,
                            "storybook_name": output.storybook_name,
                            "total_pages": output.total_pages,
                            "completed_pages": output.completed_pages,
                            "current_page": output.current_page,
                            "status": output.status,
                            "generating_pages": output.generating_pages,
                            "error_message": output.error_message,
                        }
                        content_value = json.dumps(progress_info)
                    elif isinstance(output, StorybookResultContent):
                        # Handle storybook result - convert to structured text for LLM
                        storybook_info = {
                            "type": "storybook",
                            "storybook_id": output.storybook_id,
                            "storybook_name": output.storybook_name,
                            "page_count": len(output.pages),
                            "pages": [
                                {
                                    "page_number": p.page_number,
                                    "image_url": p.image_url,
                                    "text_content": p.text_content,
                                }
                                for p in output.pages
                            ],
                        }
                        content_value = json.dumps(storybook_info)
                    else:
                        # Fallback for unknown types
                        logger.warning(f"Unknown tool result output type: {type(output)}")
                        content_value = str(output)

                    converted_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_result.tool_call_id,
                            "content": content_value,
                        }
                    )
            else:
                content_parts = []
                text_content = None

                for part in message.parts:
                    if isinstance(part, TextContent):
                        text_content = part.text
                    elif isinstance(part, BinaryContent):
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": part.to_base64("openai")},
                            }
                        )
                    elif isinstance(part, ImageURLContent):
                        content_parts.append({"type": "image_url", "image_url": {"url": part.url}})
                    elif isinstance(part, ToolCall):
                        pass

                if text_content:
                    if content_parts:
                        content_parts.insert(0, {"type": "text", "text": text_content})
                    else:
                        content_parts = text_content

                tool_calls_in_message = message.tool_calls()
                msg_dict = {"role": role, "content": content_parts or ""}

                if tool_calls_in_message and role == MessageRole.ASSISTANT.value:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.input},
                        }
                        for tc in tool_calls_in_message
                    ]

                converted_messages.append(msg_dict)

        return converted_messages

    def _convert_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Convert tools to OpenAI-compatible format if needed."""
        if not tools:
            return None

        converted_tools = []
        for tool in tools:
            if "function" in tool:
                converted_tools.append(tool)
            elif "name" in tool:
                converted_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name"),
                            "description": tool.get("description"),
                            "parameters": tool.get("parameters"),
                        },
                    }
                )
            else:
                converted_tools.append(tool)

        return converted_tools

    async def send(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> RunResponseOutput:
        """Send messages and get complete response using litellm."""
        litellm_messages = self._convert_messages(messages)
        litellm_tools = self._convert_tools(tools)
        custom_opts = (provider_options or {}).get("custom", {})

        # Prepend system prompt if not already present
        if not litellm_messages or litellm_messages[0].get("role") != "system":
            litellm_messages.insert(
                0,
                {
                    "role": "system",
                    "content": template.substitute(
                        current_date=datetime.now().strftime("%Y-%m-%d")
                    ),
                },
            )

        params = {
            "model": self.model_name,
            "messages": litellm_messages,
            "stream": False,
        }

        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["base_url"] = self.base_url
            params["custom_llm_provider"] = "openai"
        if litellm_tools:
            params["tools"] = litellm_tools
        if self.llm_config.temperature is not None:
            params["temperature"] = self.llm_config.temperature
        if custom_opts.get("max_tokens") is not None:
            params["max_tokens"] = custom_opts["max_tokens"]

        try:
            response = await acompletion(**params)

            choice = response.choices[0]
            message = choice.message

            content_parts = []

            # Add text content if present
            if hasattr(message, "content") and message.content:
                content_parts.append(TextContent(text=message.content))

            # Add tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    content_parts.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            input=tc.function.arguments,
                            finished=True,
                        )
                    )

            usage = TokenUsage()
            if hasattr(response, "usage") and response.usage:
                usage = TokenUsage(
                    input_tokens=getattr(
                        response.usage,
                        "input_tokens",
                        getattr(response.usage, "prompt_tokens", 0),
                    ),
                    output_tokens=getattr(
                        response.usage,
                        "output_tokens",
                        getattr(response.usage, "completion_tokens", 0),
                    ),
                    model_name=self.llm_config.model,
                )

            finish_reason_map = {
                "stop": FinishReason.END_TURN,
                "length": FinishReason.MAX_TOKENS,
                "tool_calls": FinishReason.TOOL_USE,
                "function_call": FinishReason.TOOL_USE,
                "content_filter": FinishReason.ERROR,
            }

            finish_reason = finish_reason_map.get(choice.finish_reason, FinishReason.UNKNOWN)

            # Determine finish reason from content parts
            has_tool_calls = any(isinstance(part, ToolCall) for part in content_parts)
            if has_tool_calls and finish_reason == FinishReason.END_TURN:
                finish_reason = FinishReason.TOOL_USE

            return RunResponseOutput(
                content=content_parts,
                usage=usage,
                finish_reason=finish_reason,
            )

        except Exception as e:
            logger.error(f"Error in CustomProvider.send: {e}")
            raise

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
        session_id: Optional[str] = None,
        provider_options: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response events using litellm."""
        litellm_messages = self._convert_messages(messages)
        litellm_tools = self._convert_tools(tools)
        custom_opts = (provider_options or {}).get("custom", {})

        # Prepend system prompt if not already present
        if not litellm_messages or litellm_messages[0].get("role") != "system":
            litellm_messages.insert(
                0,
                {
                    "role": "system",
                    "content": template.substitute(
                        current_date=datetime.now().strftime("%Y-%m-%d")
                    ),
                },
            )

        params = {
            "model": self.model_name,
            "messages": litellm_messages,
            "stream": True,
        }

        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["base_url"] = self.base_url
            params["custom_llm_provider"] = "openai"
        if litellm_tools:
            params["tools"] = litellm_tools
        if self.llm_config.temperature is not None:
            params["temperature"] = self.llm_config.temperature
        if custom_opts.get("max_tokens") is not None:
            params["max_tokens"] = custom_opts["max_tokens"]

        try:
            stream = await acompletion(**params)

            content_started = False
            tool_call_tracking = {}
            content_parts = []
            accumulated_text = ""

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if hasattr(delta, "content") and delta.content:
                    if not content_started:
                        yield RunResponseEvent(type=EventType.CONTENT_START)
                        content_started = True
                    accumulated_text += delta.content
                    yield RunResponseEvent(type=EventType.CONTENT_DELTA, content=delta.content)

                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        tc_index = tc_delta.index

                        if tc_index not in tool_call_tracking:
                            tool_call_id = (
                                tc_delta.id if hasattr(tc_delta, "id") else f"call_{tc_index}"
                            )
                            tool_call_name = ""
                            if hasattr(tc_delta, "function") and hasattr(tc_delta.function, "name"):
                                tool_call_name = tc_delta.function.name or ""

                            tool_call_tracking[tc_index] = {
                                "id": tool_call_id,
                                "name": tool_call_name,
                                "arguments": "",
                            }

                            yield RunResponseEvent(
                                type=EventType.TOOL_USE_START,
                                tool_call=ToolCall(
                                    id=tool_call_id,
                                    name=tool_call_name,
                                    input="",
                                    finished=False,
                                ),
                            )

                        if (
                            hasattr(tc_delta, "function")
                            and hasattr(tc_delta.function, "name")
                            and tc_delta.function.name
                        ):
                            tool_call_tracking[tc_index]["name"] = tc_delta.function.name

                        if (
                            hasattr(tc_delta, "function")
                            and hasattr(tc_delta.function, "arguments")
                            and tc_delta.function.arguments
                        ):
                            args_delta = tc_delta.function.arguments
                            tool_call_tracking[tc_index]["arguments"] += args_delta

                            yield RunResponseEvent(
                                type=EventType.TOOL_USE_DELTA,
                                tool_call=ToolCall(
                                    id=tool_call_tracking[tc_index]["id"],
                                    name=tool_call_tracking[tc_index]["name"],
                                    input=args_delta,
                                    finished=False,
                                ),
                            )

                finish_reason = getattr(chunk.choices[0], "finish_reason", None)
                if finish_reason:
                    logger.debug(f"Chunk finish_reason: {finish_reason}")

                    if content_started:
                        yield RunResponseEvent(type=EventType.CONTENT_STOP)

                    # Build content_parts from accumulated data
                    if accumulated_text:
                        content_parts.append(TextContent(text=accumulated_text))

                    for tc_data in tool_call_tracking.values():
                        tool_call = ToolCall(
                            id=tc_data["id"],
                            name=tc_data["name"],
                            input=tc_data["arguments"],
                            finished=True,
                        )
                        content_parts.append(tool_call)
                        yield RunResponseEvent(
                            type=EventType.TOOL_USE_STOP,
                            tool_call=tool_call,
                        )

                    usage = TokenUsage()
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = TokenUsage(
                            input_tokens=getattr(
                                chunk.usage,
                                "input_tokens",
                                getattr(chunk.usage, "prompt_tokens", 0),
                            ),
                            output_tokens=getattr(
                                chunk.usage,
                                "output_tokens",
                                getattr(chunk.usage, "completion_tokens", 0),
                            ),
                            model_name=self.llm_config.model,
                        )

                    finish_reason_map = {
                        "stop": FinishReason.END_TURN,
                        "length": FinishReason.MAX_TOKENS,
                        "tool_calls": FinishReason.TOOL_USE,
                        "function_call": FinishReason.TOOL_USE,
                        "content_filter": FinishReason.ERROR,
                    }

                    final_finish_reason = finish_reason_map.get(finish_reason, FinishReason.UNKNOWN)

                    # Determine finish reason from content parts
                    has_tool_calls = any(isinstance(part, ToolCall) for part in content_parts)
                    if has_tool_calls and final_finish_reason == FinishReason.END_TURN:
                        final_finish_reason = FinishReason.TOOL_USE

                    yield RunResponseEvent(
                        type=EventType.COMPLETE,
                        response=RunResponseOutput(
                            content=content_parts,
                            usage=usage,
                            finish_reason=final_finish_reason,
                        ),
                    )

        except Exception as e:
            logger.error(f"Error in CustomProvider.stream: {e}")
            yield RunResponseEvent(
                type=EventType.ERROR,
                error=e,
            )

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "id": self.model_name,
            "name": self.model_name,
            "provider": self.provider_prefix,
        }
