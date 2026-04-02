"""
Agent Template - Boilerplate for creating new agents

This template demonstrates best practices for agent development including:
- Proper async patterns
- Tool integration
- Error handling
- Session management
- Streaming support
"""

from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from ii_agent.v1.agents.agent import IIAgent
from ii_agent.v1.models.base import Model
from ii_agent.v1.run.agent import RunOutput, RunOutputEvent
from ii_agent.v1.tools.base import BaseAgentTool, ToolResult
from ii_agent.v1.tools import Toolkit


# ===========================
# Custom Tools (if needed)
# ===========================

class ExampleTool(BaseAgentTool):
    """Example custom tool following best practices."""

    name = "example_tool"
    display_name = "Example Tool"
    description = "Performs example operation"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The input query to process",
            }
        },
        "required": ["query"],
    }
    read_only = True

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """
        Execute the tool.

        Args:
            tool_input: Dictionary containing input parameters matching input_schema

        Returns:
            ToolResult with execution result
        """
        query = tool_input.get("query", "")

        try:
            # Your tool logic here
            result = f"Processed: {query}"

            return ToolResult(
                llm_content=result,
                is_error=False,
            )

        except Exception as e:
            # Always handle errors gracefully
            return ToolResult(
                llm_content=f"Error executing tool: {str(e)}",
                is_error=True,
            )


class ConnectableTool(BaseAgentTool):
    """Example tool that requires connection management."""

    name = "database_tool"
    display_name = "Database Tool"
    description = "Executes database queries"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The database query to execute",
            }
        },
        "required": ["query"],
    }
    read_only = True
    requires_connect = True

    def __init__(self):
        self._connection: Optional[Any] = None

    def connect(self):
        """Initialize connection. Called by agent before use."""
        # Example: self._connection = create_db_connection()
        self._connection = "connected"
        print(f"Tool {self.name} connected")

    def close(self):
        """Close connection. Called by agent in finally block."""
        if self._connection:
            # Example: self._connection.close()
            self._connection = None
            print(f"Tool {self.name} closed")

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute query using connection."""
        query = tool_input.get("query", "")

        if not self._connection:
            return ToolResult(
                llm_content=f"Tool {self.name} not connected",
                is_error=True,
            )

        try:
            # Your database logic here
            result = f"Query result for: {query}"

            return ToolResult(
                llm_content=result,
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                llm_content=f"Database error: {str(e)}",
                is_error=True,
            )


# ===========================
# Hooks (if needed)
# ===========================

async def example_pre_hook(
    run_response: RunOutput,
    run_context: "RunContext",
    run_input: "RunInput",
    session: "AgentSession",
    user_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Pre-hook example: Called before agent processing.

    Use cases:
    - Input validation
    - Context injection
    - Logging
    """
    print(f"Pre-hook: Processing input for run {run_response.run_id}")

    # Example: Add context to session state
    if run_context.session_state is not None:
        run_context.session_state["pre_hook_executed"] = True


async def example_post_hook(
    run_output: RunOutput,
    run_context: "RunContext",
    session: "AgentSession",
    user_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Post-hook example: Called after output generation.

    Use cases:
    - Output validation
    - Logging
    - Metrics collection
    """
    print(f"Post-hook: Generated output for run {run_output.run_id}")

    # Example: Log metrics
    if run_output.metrics:
        print(f"Run duration: {run_output.metrics.time}")


# ===========================
# Agent Factory
# ===========================

def create_simple_agent(
    user_id: str,
    session_id: str,
    model: Model,
    name: str = "simple_agent",
    **kwargs
) -> IIAgent:
    """
    Create a simple agent with basic configuration.

    Args:
        user_id: User identifier
        session_id: Session identifier
        model: LLM model to use
        name: Agent name
        **kwargs: Additional agent configuration

    Returns:
        Configured IIAgent instance
    """
    agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name=name,
        description="A simple agent for demonstration",
        instructions=[
            "Be helpful and concise",
            "Use tools when appropriate",
            "Ask for clarification when needed",
        ],
        # Basic configuration
        stream=True,
        stream_events=False,
        **kwargs
    )

    return agent


def create_agent_with_tools(
    user_id: str,
    session_id: str,
    model: Model,
    name: str = "agent_with_tools",
    **kwargs
) -> IIAgent:
    """
    Create an agent with custom tools.

    Args:
        user_id: User identifier
        session_id: Session identifier
        model: LLM model to use
        name: Agent name
        **kwargs: Additional agent configuration

    Returns:
        Configured IIAgent instance with tools
    """
    # Initialize tools
    example_tool = ExampleTool()
    connectable_tool = ConnectableTool()

    agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name=name,
        description="Agent with custom tools",
        tools=[example_tool, connectable_tool],
        tool_call_limit=10,  # Prevent infinite loops
        tool_choice="auto",  # Let model decide when to use tools
        **kwargs
    )

    return agent


def create_agent_with_hooks(
    user_id: str,
    session_id: str,
    model: Model,
    name: str = "agent_with_hooks",
    **kwargs
) -> IIAgent:
    """
    Create an agent with pre and post hooks.

    Args:
        user_id: User identifier
        session_id: Session identifier
        model: LLM model to use
        name: Agent name
        **kwargs: Additional agent configuration

    Returns:
        Configured IIAgent instance with hooks
    """
    agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name=name,
        description="Agent with lifecycle hooks",
        pre_hooks=[example_pre_hook],
        post_hooks=[example_post_hook],
        **kwargs
    )

    return agent


def create_team_agent(
    user_id: str,
    session_id: str,
    model: Model,
    name: str = "team_leader",
    **kwargs
) -> IIAgent:
    """
    Create a parent agent with sub-agents (team pattern).

    Args:
        user_id: User identifier
        session_id: Session identifier
        model: LLM model to use
        name: Agent name
        **kwargs: Additional agent configuration

    Returns:
        Configured IIAgent instance with sub-agents
    """
    # Create sub-agents
    analyst_agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name="analyst",
        role="Data analyst specialized in metrics and insights",
        description="Analyzes data and provides insights",
    )

    researcher_agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name="researcher",
        role="Researcher specialized in information gathering",
        description="Conducts research and gathers information",
    )

    # Create parent agent with sub-agents
    team_agent = IIAgent(
        user_id=user_id,
        session_id=session_id,
        model=model,
        name=name,
        description="Team leader that delegates to specialists",
        sub_agents=[analyst_agent, researcher_agent],
        delegate_to_all_members=False,  # Delegate to specific members
        stream_member_events=True,  # Stream sub-agent events
        store_member_responses=True,  # Store sub-agent responses
        **kwargs
    )

    return team_agent


# ===========================
# Usage Examples
# ===========================

async def example_basic_usage():
    """Example: Basic agent usage."""
    from ii_agent.v1.models.openai import OpenAIChat

    # Create model
    model = OpenAIChat(id="gpt-4")

    # Create agent
    agent = create_simple_agent(
        user_id="user123",
        session_id="session123",
        model=model,
    )

    # Run agent
    response = await agent.arun(input="What is 2 + 2?")

    print(f"Response: {response.content}")
    print(f"Status: {response.status}")


async def example_streaming_usage():
    """Example: Streaming agent usage."""
    from ii_agent.v1.models.openai import OpenAIChat

    # Create model and agent
    model = OpenAIChat(id="gpt-4")
    agent = create_simple_agent(
        user_id="user123",
        session_id="session123",
        model=model,
    )

    # Stream response
    async for event in agent.arun(
        input="Write a short story",
        stream=True,
        stream_events=True,
    ):
        if isinstance(event, RunOutput):
            print(f"\nFinal result: {event.content}")
        else:
            print(f"Event: {event.type}")


async def example_tools_usage():
    """Example: Agent with tools."""
    from ii_agent.v1.models.openai import OpenAIChat

    # Create model and agent with tools
    model = OpenAIChat(id="gpt-4")
    agent = create_agent_with_tools(
        user_id="user123",
        session_id="session123",
        model=model,
    )

    # Run agent - model can use tools
    response = await agent.arun(input="Use the example tool to process 'hello'")

    print(f"Response: {response.content}")
    if response.tools:
        print(f"Tools used: {[tool.tool_name for tool in response.tools]}")


async def example_team_usage():
    """Example: Team agent with sub-agents."""
    from ii_agent.v1.models.openai import OpenAIChat

    # Create model and team agent
    model = OpenAIChat(id="gpt-4")
    team_agent = create_team_agent(
        user_id="user123",
        session_id="session123",
        model=model,
    )

    # Run team agent - it can delegate to sub-agents
    response = team_agent.arun(
        input="Analyze our Q4 sales data",
        stream=True,
        stream_events=True,
    )

    async for event in response:
        if isinstance(event, RunOutput):
            print(f"\nFinal: {event.content}")
            if event.member_runs:
                print(f"Sub-agent runs: {len(event.member_runs)}")
        elif hasattr(event, "is_sub_agent_event") and event.is_sub_agent_event:
            print(f"Sub-agent event: {event.type}")


async def example_error_handling():
    """Example: Error handling and retries."""
    from ii_agent.v1.models.openai import OpenAIChat

    # Create agent with retry configuration
    model = OpenAIChat(id="gpt-4")
    agent = IIAgent(
        user_id="user123",
        session_id="session123",
        model=model,
        name="resilient_agent",
        retries=3,  # Retry up to 3 times
        delay_between_retries=2,  # 2 seconds between retries
        exponential_backoff=True,  # Double delay each retry
    )

    try:
        response = await agent.arun(input="Process this")
        print(f"Success: {response.content}")

    except Exception as e:
        print(f"Failed after retries: {e}")


# ===========================
# Main
# ===========================

if __name__ == "__main__":
    import asyncio

    # Run examples
    print("=== Basic Usage ===")
    asyncio.run(example_basic_usage())

    print("\n=== Streaming Usage ===")
    asyncio.run(example_streaming_usage())

    print("\n=== Tools Usage ===")
    asyncio.run(example_tools_usage())

    print("\n=== Team Usage ===")
    asyncio.run(example_team_usage())

    print("\n=== Error Handling ===")
    asyncio.run(example_error_handling())
