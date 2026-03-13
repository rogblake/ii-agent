"""Agent configuration for different agent types."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from ii_agent.agent.runtime.tools.sandbox import RegisterPortTool
from ii_agent.agent.types import AgentType, Provider
from ii_agent.agent.runtime.tools.agent import SendUserFile
from ii_agent.agent.runtime.tools.decorator import tool as tool_decorator
from ii_agent.agent.runtime.tools.browser import (
    BrowserClickTool,
    BrowserDragTool,
    BrowserEnterMultipleTextsTool,
    BrowserEnterTextTool,
    BrowserGetSelectOptionsTool,
    BrowserNavigationTool,
    BrowserOpenNewTabTool,
    BrowserPressKeyTool,
    BrowserRestartTool,
    BrowserScrollDownTool,
    BrowserScrollUpTool,
    BrowserSelectDropdownOptionTool,
    BrowserSwitchTabTool,
    BrowserViewTool,
    BrowserWaitTool,
)
from ii_agent.agent.runtime.tools.dev import (
    FullStackInitTool,
    GetDatabaseConnection,
    SaveCheckpointTool,
    AddWebDevSecrets,
    AskUserEnvTool,
    RestartServerTool,
    GetServerStatusTool,
    MobileAppInitTool,
    RestartMobileServerTool,
    RevenueCatTool,
    AskUserSelectTool,
)

from ii_agent.agent.runtime.tools.file_system import (
    ApplyPatchTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    StrReplaceEditorTool,
)
from ii_agent.agent.runtime.tools.media import ImageGenerateTool, VideoGenerateTool
from ii_agent.agent.runtime.tools.productivity import TodoReadTool, TodoWriteTool
from ii_agent.agent.runtime.tools.shell import (
    ShellInit,
    ShellList,
    ShellRunCommand,
    ShellView,
    ShellWriteToProcessTool,
)
from ii_agent.agent.runtime.tools.slide_system import (
    SlideApplyPatchTool,
    SlideEditTool,
    SlideGenerationTool,
    SlideWriteTool,
)
from ii_agent.agent.runtime.tools.web import (
    ImageSearchTool,
    WebBatchSearchTool,
    WebSearchTool,
    WebVisitCompressTool,
    WebVisitTool,
)

TOOL_CONFIRM_MAP = {
    AskUserEnvTool.name: True
    # StrReplaceEditorTool.name: True,
    # ApplyPatchTool.name: True,
    # SaveCheckpointTool.name: True,
}

COMMON_TOOLS = {RegisterPortTool, AskUserSelectTool}

# Tool name to class mapping
TOOL_CLASS_MAP = {
    # Shell tools
    ShellInit.name: ShellInit,
    ShellRunCommand.name: ShellRunCommand,
    ShellView.name: ShellView,
    ShellList.name: ShellList,
    ShellWriteToProcessTool.name: ShellWriteToProcessTool,
    # File system tools
    FileReadTool.name: FileReadTool,
    FileWriteTool.name: FileWriteTool,
    FileEditTool.name: FileEditTool,
    ApplyPatchTool.name: ApplyPatchTool,
    StrReplaceEditorTool.name: StrReplaceEditorTool,
    # Web tools
    WebSearchTool.name: WebSearchTool,
    WebVisitTool.name: WebVisitTool,
    WebVisitCompressTool.name: WebVisitCompressTool,
    WebBatchSearchTool.name: WebBatchSearchTool,
    ImageSearchTool.name: ImageSearchTool,
    # Browser tools
    BrowserClickTool.name: BrowserClickTool,
    BrowserWaitTool.name: BrowserWaitTool,
    BrowserViewTool.name: BrowserViewTool,
    BrowserScrollDownTool.name: BrowserScrollDownTool,
    BrowserScrollUpTool.name: BrowserScrollUpTool,
    BrowserSwitchTabTool.name: BrowserSwitchTabTool,
    BrowserOpenNewTabTool.name: BrowserOpenNewTabTool,
    BrowserGetSelectOptionsTool.name: BrowserGetSelectOptionsTool,
    BrowserSelectDropdownOptionTool.name: BrowserSelectDropdownOptionTool,
    BrowserNavigationTool.name: BrowserNavigationTool,
    BrowserRestartTool.name: BrowserRestartTool,
    BrowserEnterTextTool.name: BrowserEnterTextTool,
    BrowserPressKeyTool.name: BrowserPressKeyTool,
    BrowserDragTool.name: BrowserDragTool,
    BrowserEnterMultipleTextsTool.name: BrowserEnterMultipleTextsTool,
    # Media tools
    VideoGenerateTool.name: VideoGenerateTool,
    ImageGenerateTool.name: ImageGenerateTool,
    # Slide tools
    SlideWriteTool.name: SlideWriteTool,
    SlideEditTool.name: SlideEditTool,
    SlideGenerationTool.name: SlideGenerationTool,
    SlideApplyPatchTool.name: SlideApplyPatchTool,
    # Dev tools
    FullStackInitTool.name: FullStackInitTool,
    GetDatabaseConnection.name: GetDatabaseConnection,
    SaveCheckpointTool.name: SaveCheckpointTool,
    RestartServerTool.name: RestartServerTool,
    AddWebDevSecrets.name: AddWebDevSecrets,
    AskUserEnvTool.name: AskUserEnvTool,
    GetServerStatusTool.name: GetServerStatusTool,
    MobileAppInitTool.name: MobileAppInitTool,
    RestartMobileServerTool.name: RestartMobileServerTool,
    RevenueCatTool.name: RevenueCatTool,
    AskUserSelectTool.name: AskUserSelectTool,
    # Productivity tools
    TodoReadTool.name: TodoReadTool,
    TodoWriteTool.name: TodoWriteTool,
    # Agent tools
    SendUserFile.name: SendUserFile,
}



@dataclass
class AgentToolConfig:
    """Tool configuration for an agent type."""

    # Core toolset for this agent type
    core_tools: List[str]
    # Tools to exclude for specific models
    model_exclusions: Optional[Dict[Provider, List[str]]] = None
    # Tools to add for specific models
    model_additions: Optional[Dict[Provider, List[str]]] = None


@dataclass
class AgentConfig:
    """Configuration for a specific agent type."""

    agent_type: AgentType
    description: str
    tool_config: AgentToolConfig
    max_turns: int = 200
    supports_media: bool = False
    supports_browser: bool = False
    supports_design_doc: bool = False


RESEARCH_TOOL_CONFIG = AgentToolConfig(
            core_tools=[
                # Shell tools
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                # File tools
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                # Web tools
                WebSearchTool.name,
                WebVisitTool.name,
                # Productivity
                TodoWriteTool.name,
                # Communicate
                SendUserFile.name,
            ],
            model_exclusions={
                Provider.OPENAI: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                    ShellWriteToProcessTool.name,
                ],
                Provider.ANTHROPIC: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                    ShellWriteToProcessTool.name,
                ],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        )

# Agent configurations
AGENT_CONFIGS: Dict[AgentType, AgentConfig] = {
    AgentType.GENERAL: AgentConfig(
        agent_type=AgentType.GENERAL,
        description="General purpose coding and development agent",
        tool_config=AgentToolConfig(
            core_tools=[
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                # Dev tools
                FullStackInitTool.name,
                RestartServerTool.name,
                AddWebDevSecrets.name,
                AskUserEnvTool.name,
                GetServerStatusTool.name,
                SaveCheckpointTool.name,
                # SaveCheckpointTool.name,
                # Productivity
                TodoWriteTool.name,
                SendUserFile.name,
            ],
            model_exclusions={
                Provider.OPENAI: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                    ShellWriteToProcessTool.name,
                ],
                Provider.ANTHROPIC: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                    ShellWriteToProcessTool.name,
                ],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        supports_media=True,
        supports_browser=True,
        supports_design_doc=True,
    ),
    AgentType.TASK_AGENT: AgentConfig(
        agent_type=AgentType.TASK_AGENT,
        description="Task execution sub-agent for focused tasks",
        tool_config=AgentToolConfig(
            core_tools=[
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                FullStackInitTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
                # MessageUserTool.name,
            ],
            model_exclusions={
                Provider.OPENAI: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                ],
                Provider.ANTHROPIC: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                ],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        max_turns=200,
        supports_media=True,
        supports_browser=True,
    ),
    AgentType.RESEARCHER: AgentConfig(
        agent_type=AgentType.RESEARCHER,
        description="Research and information gathering agent",
        tool_config=AgentToolConfig(
            core_tools=[
                # MessageUserTool.name,
                WebBatchSearchTool.name,
                WebVisitCompressTool.name,
            ],
        ),
        max_turns=200,
    ),
    AgentType.DESIGN_DOCUMENT: AgentConfig(
        agent_type=AgentType.DESIGN_DOCUMENT,
        description="Design document creation agent",
        tool_config=AgentToolConfig(
            core_tools=[
                # MessageUserTool.name,
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
            ],
            model_exclusions={
                Provider.OPENAI: [FileWriteTool.name, FileEditTool.name],
                Provider.ANTHROPIC: [FileWriteTool.name, FileEditTool.name],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        max_turns=200,
    ),
    AgentType.MEDIA: AgentConfig(
        agent_type=AgentType.MEDIA,
        description="Media generation specialist",
        tool_config=AgentToolConfig(
            core_tools=[
                FileReadTool.name,
                VideoGenerateTool.name,
                ImageGenerateTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                TodoWriteTool.name,
                # MessageUserTool.name,
            ],
        ),
    ),
    AgentType.BROWSER: AgentConfig(
        agent_type=AgentType.BROWSER,
        description="Browser automation agent",
        tool_config=AgentToolConfig(
            core_tools=[
                BrowserClickTool.name,
                BrowserWaitTool.name,
                BrowserViewTool.name,
                BrowserScrollDownTool.name,
                BrowserScrollUpTool.name,
                BrowserSwitchTabTool.name,
                BrowserOpenNewTabTool.name,
                BrowserGetSelectOptionsTool.name,
                BrowserSelectDropdownOptionTool.name,
                BrowserNavigationTool.name,
                BrowserRestartTool.name,
                BrowserEnterTextTool.name,
                BrowserPressKeyTool.name,
                BrowserDragTool.name,
                BrowserEnterMultipleTextsTool.name,
                # MessageUserTool.name,
            ],
        ),
    ),
    AgentType.WEBSITE_BUILD: AgentConfig(
        agent_type=AgentType.WEBSITE_BUILD,
        description="Website building specialist",
        tool_config=AgentToolConfig(
            core_tools=[
                # MessageUserTool.name,
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                FullStackInitTool.name,
                SaveCheckpointTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                TodoWriteTool.name,
                GetDatabaseConnection.name,
            ],
        ),
    ),
    AgentType.SLIDE: AgentConfig(
        agent_type=AgentType.SLIDE,
        description="Slide/presentation creation specialist",
        tool_config=AgentToolConfig(
            core_tools=[
                # MessageUserTool.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                ImageGenerateTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
                SlideWriteTool.name,
                SlideEditTool.name,
            ],
        ),
        max_turns=200,
    ),
    AgentType.SLIDE_NANO_BANANA: AgentConfig(
        agent_type=AgentType.SLIDE_NANO_BANANA,
        description="AI-generated slide images using SlideGenerationTool",
        tool_config=AgentToolConfig(
            core_tools=[
                # MessageUserTool.name,
                FileReadTool.name,
                ImageGenerateTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
                SlideGenerationTool.name,
            ],
        ),
        max_turns=200,
    ),
    AgentType.CODEX: AgentConfig(
        agent_type=AgentType.CODEX,
        description="Code analysis and documentation agent",
        tool_config=AgentToolConfig(
            core_tools=[
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                TodoWriteTool.name,
            ],
            model_exclusions={
                Provider.OPENAI: [FileWriteTool.name, FileEditTool.name, ShellList.name],
                Provider.ANTHROPIC: [FileWriteTool.name, FileEditTool.name, ShellList.name],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        max_turns=200,
    ),
    AgentType.CLAUDE_CODE: AgentConfig(
        agent_type=AgentType.CLAUDE_CODE,
        description="Claude Code integration agent for enhanced development workflows",
        tool_config=AgentToolConfig(
            core_tools=[
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
            ],
            model_exclusions={
                Provider.OPENAI: [FileWriteTool.name, FileEditTool.name, ShellList.name],
                Provider.ANTHROPIC: [FileWriteTool.name, FileEditTool.name, ShellList.name],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        max_turns=200,
        supports_media=True,
        supports_browser=True,
    ),
    AgentType.DEEP_RESEARCH: AgentConfig(
        agent_type=AgentType.DEEP_RESEARCH,
        description="Deep research agent for comprehensive investigation and analysis",
        tool_config=RESEARCH_TOOL_CONFIG
    ),
    AgentType.FAST_RESEARCH: AgentConfig(
        agent_type=AgentType.FAST_RESEARCH,
        description="Fast research agent for quick and focused investigation",
        tool_config=RESEARCH_TOOL_CONFIG,
        max_turns=200,
    ),
    # Fork-specific agent configs
    AgentType.RESEARCH_TO_WEBSITE: AgentConfig(
        agent_type=AgentType.RESEARCH_TO_WEBSITE,
        description="Build website from research output (forked session)",
        tool_config=AgentToolConfig(
            core_tools=[
                # Same as WEBSITE_BUILD
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                FullStackInitTool.name,
                SaveCheckpointTool.name,
                WebSearchTool.name,
                WebVisitTool.name,
                TodoWriteTool.name,
                GetDatabaseConnection.name,
                ImageGenerateTool.name,
                ImageSearchTool.name,
            ],
            model_exclusions={
                Provider.OPENAI: [FileWriteTool.name, FileEditTool.name],
                Provider.ANTHROPIC: [FileWriteTool.name, FileEditTool.name],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        supports_media=True,
        supports_browser=True,
    ),
    AgentType.MOBILE_APP: AgentConfig(
        agent_type=AgentType.MOBILE_APP,
        description="Mobile app development specialist using React Native and Expo",
        tool_config=AgentToolConfig(
            core_tools=[
                ShellInit.name,
                ShellRunCommand.name,
                ShellView.name,
                ShellList.name,
                FileReadTool.name,
                FileWriteTool.name,
                FileEditTool.name,
                SaveCheckpointTool.name,
                FullStackInitTool.name,
                MobileAppInitTool.name,
                RestartMobileServerTool.name,
                RevenueCatTool.name,
                GetDatabaseConnection.name,
                WebSearchTool.name,
                WebVisitTool.name,
                ImageGenerateTool.name,
                ImageSearchTool.name,
                TodoWriteTool.name,
                SendUserFile.name,
            ],
            model_exclusions={
                Provider.OPENAI: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                ],
                Provider.ANTHROPIC: [
                    FileWriteTool.name,
                    FileEditTool.name,
                    ShellList.name,
                ],
            },
            model_additions={
                Provider.OPENAI: [ApplyPatchTool.name],
                Provider.ANTHROPIC: [StrReplaceEditorTool.name],
            },
        ),
        max_turns=200,
        supports_media=True,
        supports_browser=False,
    ),
}


class AgentConfigManager:
    """Manager for agent configurations."""

    @staticmethod
    def get_config(agent_type: AgentType) -> AgentConfig:
        """Get configuration for an agent type."""
        if agent_type not in AGENT_CONFIGS:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return AGENT_CONFIGS[agent_type]

    @staticmethod
    def get_tools_for_agent(
        agent_type: AgentType,
        model_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> Set[str]:
        """Get the set of tools for an agent type with model-specific adjustments."""

        tool_args = tool_args or {}
        include_media: bool = tool_args.get("media_generation", False)
        include_browser: bool = tool_args.get("browser", False)

        config = AgentConfigManager.get_config(agent_type)
        tools = set(config.tool_config.core_tools)

        # Apply model-specific exclusions
        if model_name and config.tool_config.model_exclusions:
            model_family = AgentConfigManager._get_model_family(model_name)
            if model_family in config.tool_config.model_exclusions:
                for tool in config.tool_config.model_exclusions[model_family]:
                    tools.discard(tool)

        # Apply model-specific additions
        if model_name and config.tool_config.model_additions:
            model_family = AgentConfigManager._get_model_family(model_name)
            if model_family in config.tool_config.model_additions:
                tools.update(config.tool_config.model_additions[model_family])

        # Add media tools if requested and supported
        if include_media and config.supports_media:
            media_config = AGENT_CONFIGS[AgentType.MEDIA]
            media_tools = [
                t
                for t in media_config.tool_config.core_tools
                if t in [VideoGenerateTool.name, ImageGenerateTool.name]
            ]
            tools.update(media_tools)

        # Add browser tools if requested and supported
        if include_browser and config.supports_browser:
            browser_config = AGENT_CONFIGS[AgentType.BROWSER]
            tools.update(browser_config.tool_config.core_tools)

        return tools

    @staticmethod
    def _get_model_family(model_name: str) -> Optional[Provider]:
        """Determine model family from model name."""
        model_lower = model_name.lower()

        # Check for OpenAI family (GPT-5, o3, etc.)
        if "gpt" in model_lower or "o3" in model_lower or "openai" in model_lower:
            return Provider.OPENAI

        # Check for Anthropic family
        if "claude" in model_lower or "anthropic" in model_lower:
            return Provider.ANTHROPIC

        # Check for Google family
        if "gemini" in model_lower or "google" in model_lower:
            return Provider.GOOGLE

        # Check for Vertex AI
        if "vertex" in model_lower:
            return Provider.VERTEX_AI

        # Check for Azure
        if "azure" in model_lower:
            return Provider.AZURE

        # Check for Cerebras
        if "cerebras" in model_lower:
            return Provider.CEREBRAS

        return None

    @staticmethod
    def is_valid_agent_type(agent_type: str) -> bool:
        """Check if agent type is valid."""
        try:
            AgentType(agent_type)
            return True
        except ValueError:
            return False

    @staticmethod
    def get_all_agent_types() -> List[str]:
        """Get all available agent types."""
        return [t.value for t in AgentType]


# This is for testing, remvoe later
@tool_decorator(requires_confirmation=True)
def get_top_hackernews_stories(num_stories: int) -> str:
    """Fetch top stories from Hacker News.

    Args:
        num_stories (int): Number of stories to retrieve

    Returns:
        str: JSON string containing story details
    """
    import httpx
    import json

    # Fetch top story IDs
    response = httpx.get("https://hacker-news.firebaseio.com/v0/topstories.json")
    story_ids = response.json()

    # Yield story details
    all_stories = []
    for story_id in story_ids[:num_stories]:
        story_response = httpx.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        story = story_response.json()
        if "text" in story:
            story.pop("text", None)
        all_stories.append(story)
    return json.dumps(all_stories)


@tool_decorator(requires_confirmation=True)
def generate_random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random integer within the specified range (inclusive).

    This tool generates a cryptographically non-secure random number
    for general-purpose use cases like testing or simulations.

    Args:
        min_val (int): The minimum value of the range (inclusive). Defaults to 1.
        max_val (int): The maximum value of the range (inclusive). Defaults to 100.

    Returns:
        str: A formatted string containing the generated random number
            and the range used.
    """
    import random

    number = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {number}"


@tool_decorator(requires_confirmation=True)
def echo_message(message: str) -> str:
    """Echo back the provided message with a prefix.

    A simple utility tool that returns the input message prefixed with "Echo:".
    Useful for testing tool execution and confirmation flows.

    Args:
        message (str): The message to echo back.

    Returns:
        str: The input message prefixed with "Echo: ".
    """
    return f"Echo: {message}"
