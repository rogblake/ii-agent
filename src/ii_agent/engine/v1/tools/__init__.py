from ii_agent.engine.v1.tools.base import (
    BaseAgentTool,
    TextContent,
    ImageContent,
    ToolResult,
    ToolParam,
    ToolConfirmationDetails,
)
from ii_agent.engine.v1.tools.decorator import tool
from ii_agent.engine.v1.tools.function import Function, FunctionCall
from ii_agent.engine.v1.tools.toolkit import Toolkit

# BaseTool implementations
# from ii_agent.engine.v1.tools.web_search import WebSearchTool
# from ii_agent.engine.v1.tools.web_visit import WebVisitTool
# from ii_agent.engine.v1.tools.image_search import ImageSearchTool
# from ii_agent.engine.v1.tools.image_generate import ImageGenerateTool


# Function-based web tools (for backward compatibility with Toolkit pattern)
# from ii_agent.engine.v1.tools.web import WebToolkit, web_search, web_visit, image_search

__all__ = [
    # Base classes
    "BaseAgentTool",
    "TextContent",
    "ImageContent",
    "ToolResult",
    "ToolParam",
    "ToolConfirmationDetails",
    "tool",
    "Function",
    "FunctionCall",
    "Toolkit",
    # BaseTool implementations
    # "WebSearchTool",
    # "WebVisitTool",
    # "ImageSearchTool",
    # "ImageGenerateTool",
    # # Function-based tools (Toolkit pattern)
    # "WebToolkit",
    # "web_search",
    # "web_visit",
    # "image_search",
]
