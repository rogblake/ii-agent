from typing import Any, Literal, Optional
from ii_agent.agent.runtime.agents.agent import IIAgent
from ii_agent.agent.runtime.tools.function import FunctionCall
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool
from ii_agent.agent.runtime.tools.base import ImageContent, TextContent, ToolResult
from ii_agent.core.config.settings import get_settings
from fastmcp.exceptions import ToolError
from fastmcp import Client

DEFAULT_TIMEOUT = 1800


class ComposioMCPTool(BaseSandboxTool):
    # Regular class attributes (not ClassVar)
    name: str
    description: str
    input_schema: dict[str, Any]
    display_name: str
    read_only: bool = False
    type: Literal["function", "openai_custom"] = "function"
    requires_confirmation: bool = False
    tool_logo: Optional[str] = None

    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool,
        requires_confirmation: bool = False,
        type: Literal[
            "function", "openai_custom"
        ] = "function",  # check https://platform.openai.com/docs/guides/function-calling#context-free-grammars,
        mcp_server_id: str = None,
        tool_logo: Optional[str] = None,
    ):
        # Tool information
        self.name = name
        self.display_name = display_name
        self.description = description
        self.read_only = read_only
        if type == "function":
            self.input_schema = input_schema
        else:
            self.format = input_schema
        self.mcp_client: Client = None
        self.requires_confirmation = requires_confirmation
        self.mcp_server_id = mcp_server_id
        self.tool_logo = tool_logo

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall):
        await super().on_tool_start(agent, fc)
        sandbox = agent.sandbox
        sandbox_url = await sandbox.expose_port(get_settings().mcp.port)
        self.mcp_client = sandbox.get_mcp_client(sandbox_url)

    def _strip_optional_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Keep only required parameters, dropping all optional ones.

        Composio tool schemas expose many optional fields with defaults.
        LLMs auto-fill these (e.g. plan='free', template_url='placeholder',
        desired_instance_size='micro') which causes upstream API errors.
        Since optional params have server-side defaults, it is safe to omit
        them entirely and let the API apply its own defaults.
        """
        schema = getattr(self, "input_schema", None)
        if not isinstance(schema, dict):
            return params

        required = set(schema.get("required", []))
        if not required:
            # No required list in schema — pass everything through
            return params

        return {k: v for k, v in params.items() if k in required}

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            tool_input = self._strip_optional_params(tool_input)
            async with self.mcp_client:
                composio_tool_name = f"mcp_composio_{self.name}"
                mcp_results = await self.mcp_client.call_tool(
                    composio_tool_name,
                    tool_input,
                    timeout=DEFAULT_TIMEOUT,
                )

                llm_content : list[ImageContent | TextContent]= []
                has_image_content = False
                for mcp_result in mcp_results.content:
                    if mcp_result.type == "text":
                        llm_content.append(TextContent(type="text", text=mcp_result.text))
                    elif mcp_result.type == "image":
                        llm_content.append(
                            ImageContent(
                                type="image",
                                data=mcp_result.data,
                                mime_type=mcp_result.mimeType,
                            )
                        )
                        has_image_content = True
                    else:
                        raise ValueError(f"Unknown result type: {mcp_result.type}")

                user_display_content = None
                is_error = False
                # Logic for our internal tools
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error")
                # For external tools (like MCP) or internal tools that don't have a user_display_content
                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join([content.text for content in llm_content])
                    else:
                        user_display_content = [content.model_dump() for content in llm_content]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
