---
name: agent-development
description: Develop AI agents using the II Agent framework. Use this skill when creating new agents, implementing agent features, integrating tools, managing sessions, implementing streaming, or working with sub-agents/teams. Covers async patterns, LLM provider integration, error handling, and best practices for production-ready agents.
---

# Agent Development

## Overview

Develop production-ready AI agents using the II Agent framework. This skill provides comprehensive guidance on agent architecture, async patterns, tool integration, session management, streaming, and team-based agent systems.

## When to Use This Skill

Use this skill when:
- Creating new AI agents or agent-based applications
- Implementing agent features: tools, hooks, streaming, sub-agents
- Integrating with LLM providers (OpenAI, Anthropic, etc.)
- Managing agent sessions and state
- Building multi-agent systems or teams
- Debugging agent lifecycle issues
- Optimizing agent performance
- Working with files in `src/ii_agent/v1/agents/` or creating new agent implementations

## Quick Start

### 1. Basic Agent Creation

Create a simple agent with minimal configuration:

```python
from ii_agent.v1.agents.agent import IIAgent
from ii_agent.v1.models.openai import OpenAIChat

# Create model
model = OpenAIChat(id="gpt-4")

# Create agent
agent = IIAgent(
    user_id="user123",
    session_id="session456",
    model=model,
    name="my_agent",
    description="A helpful assistant",
    instructions=[
        "Be concise and helpful",
        "Use tools when appropriate",
    ],
)

# Run agent
response = await agent.arun(input="What is 2 + 2?")
print(response.content)
```

### 2. Agent with Streaming

Enable streaming for real-time responses:

```python
# Stream response
async for event in agent.arun(
    input="Write a story",
    stream=True,
    stream_events=True,
):
    if isinstance(event, RunOutput):
        print(f"Final: {event.content}")
    else:
        print(f"Event: {event.type}")
```

### 3. Agent with Tools

Add custom tools to extend agent capabilities:

```python
from ii_agent.v1.tools.base import BaseAgentTool, ToolResult

class SearchTool(BaseAgentTool):
    name = "search"
    display_name = "Search"
    description = "Search for information"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"],
    }
    read_only = True

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")
        # Your search logic
        result = f"Results for: {query}"
        return ToolResult(llm_content=result, is_error=False)

agent = IIAgent(
    user_id="user123",
    session_id="session456",
    model=model,
    tools=[SearchTool()],
    tool_call_limit=10,
)
```

## Core Concepts

### Agent Lifecycle

Every agent run follows this lifecycle:

1. **Initialization** - Create run task, load/create session
2. **Pre-hooks** - Execute pre-processing hooks
3. **Tool Preparation** - Determine available tools for model
4. **Message Preparation** - Build message history with context
5. **Model Execution** - Generate response (includes tool calls)
6. **Post-hooks** - Execute post-processing hooks
7. **Session Summary** - Create summary if configured
8. **Cleanup** - Store results, disconnect tools, save metrics

### Key Components

**IIAgent**: Main agent class (dataclass)
- Required: `user_id`, `session_id`, `model`, `name`
- Optional: `tools`, `sub_agents`, `hooks`, `session_store`

**RunOutput**: Complete result of an agent run
- Contains: `run_id`, `content`, `messages`, `tools`, `metrics`, `status`

**RunContext**: Execution context
- Contains: `run_id`, `session_id`, `user_id`, `session_state`, `metadata`

**AgentSession**: Persistent session across runs
- Contains: `session_id`, `runs`, `session_data`, `summary`

## Tool Development

### Basic Tool Pattern

```python
from ii_agent.v1.tools.base import BaseAgentTool, ToolResult

class ExampleTool(BaseAgentTool):
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
        query = tool_input.get("query", "")

        try:
            result = f"Processed: {query}"
            return ToolResult(
                llm_content=result,
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error: {str(e)}",
                is_error=True,
            )
```

### Tool with Connection Management

For tools requiring initialization/cleanup:

```python
class DatabaseTool(BaseAgentTool):
    name = "database"
    display_name = "Database Tool"
    description = "Execute database queries"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL query to execute"}
        },
        "required": ["query"],
    }
    read_only = True
    requires_connect = True

    def __init__(self):
        self._connection: Optional[Any] = None

    def connect(self):
        """Called by agent before use."""
        self._connection = create_db_connection()

    def close(self):
        """Called by agent in finally block."""
        if self._connection:
            self._connection.close()

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")

        if not self._connection:
            return ToolResult(
                llm_content="Tool not connected",
                is_error=True,
            )

        try:
            result = await self._connection.execute(query)
            return ToolResult(
                llm_content=str(result),
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Database error: {str(e)}",
                is_error=True,
            )
```

### Streaming Tool Pattern

Tools can stream results:

```python
async def streaming_tool(
    query: str
) -> AsyncIterator[Union[str, RunOutputEvent]]:
    """Tool that yields results progressively."""
    for chunk in process_query(query):
        yield chunk
    yield "Processing complete"
```

### MCP Tool Integration

Integrate Model Context Protocol servers:

```python
from ii_agent.v1.tools.mcp import MCPTools

# MCP tool with auto-connect
mcp_tool = MCPTools(
    server_config={
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-server-example"]
    }
)

agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    tools=[mcp_tool],  # Auto-connects and disconnects
)
```

## Hooks System

### Pre-Hooks

Execute before agent processing:

```python
async def validation_hook(
    run_response: RunOutput,
    run_context: RunContext,
    run_input: RunInput,
    session: AgentSession,
    **kwargs
) -> None:
    """Validate and enrich input."""
    # Add context
    if run_context.session_state:
        run_context.session_state["validated"] = True

    # Log
    print(f"Processing run {run_response.run_id}")

agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    pre_hooks=[validation_hook],
)
```

### Post-Hooks

Execute after output generation:

```python
async def logging_hook(
    run_output: RunOutput,
    run_context: RunContext,
    session: AgentSession,
    **kwargs
) -> None:
    """Log metrics and results."""
    if run_output.metrics:
        print(f"Duration: {run_output.metrics.time}s")

    # Custom processing
    if run_output.tools:
        print(f"Tools used: {len(run_output.tools)}")

agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    post_hooks=[logging_hook],
)
```

### Tool Hooks

Middleware for tool execution:

```python
async def tool_middleware(
    tool_name: str,
    tool_args: Dict[str, Any],
    **kwargs
) -> Optional[str]:
    """Middleware for tool authorization."""
    # Authorization check
    if not is_authorized(tool_name):
        return "Unauthorized tool access"

    # Rate limiting
    if is_rate_limited(tool_name):
        return "Rate limit exceeded"

    # Allow execution
    return None

agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    tool_hooks=[tool_middleware],
)
```

## Session Management

### Session State

Mutable state persisted across runs:

```python
# Initialize with default state
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    session_state={
        "user_preferences": {},
        "conversation_count": 0,
    },
)

# State is automatically persisted
response = await agent.arun(input="Hello")

# Access state in next run
response2 = await agent.arun(input="Continue")
# State from previous run is available
```

### Session Store

Persist sessions to database:

```python
from ii_agent.v1.sessions import SessionStore

# Custom session store
session_store = DatabaseSessionStore(
    connection_string="postgresql://..."
)

agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    session_store=session_store,  # Enable persistence
)
```

### Session Summary

Automatic session summarization:

```python
from ii_agent.v1.sessions import SessionSummaryManager

# Enable session summaries
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    session_summary_manager=SessionSummaryManager(model=model),
)

# Summary is automatically created after each run
response = await agent.arun(input="Hello")
# session.summary contains generated summary
```

## Streaming

### Content Streaming

Stream response content:

```python
# Enable content streaming
async for event in agent.arun(
    input="Write a long story",
    stream=True,
):
    if isinstance(event, RunOutput):
        print(f"Final: {event.content}")
    else:
        # Content deltas
        print(event.content, end="")
```

### Event Streaming

Stream detailed lifecycle events:

```python
# Enable event streaming
async for event in agent.arun(
    input="Process this",
    stream=True,
    stream_events=True,
):
    if isinstance(event, RunOutput):
        print(f"Final result")
    elif event.type == RunEvent.tool_call_started:
        print(f"Tool: {event.data['tool_name']}")
    elif event.type == RunEvent.run_content_delta:
        print(event.content, end="")
```

### Event Types

Available event types:
- `RunStarted` - Run begins
- `RunCompleted` - Run completes
- `RunCancelled` - Run cancelled
- `RunError` - Run error
- `RunContentDelta` - Content chunk
- `RunContentCompleted` - Content finished
- `ToolCallStarted` - Tool execution begins
- `ToolCallCompleted` - Tool execution ends
- `ReasoningStarted/Delta/Completed` - Reasoning events
- `PreHookStarted/Completed` - Pre-hook events
- `PostHookStarted/Completed` - Post-hook events
- `SessionSummaryStarted/Completed` - Summary events

### Event Filtering

Control event verbosity:

```python
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    events_to_skip=[
        RunEvent.run_content_delta,  # Too verbose
        RunEvent.reasoning_delta,
    ],
)
```

## Sub-Agents & Teams

### Basic Sub-Agent Pattern

Create agents with specialized sub-agents:

```python
# Create sub-agents
analyst = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    name="analyst",
    role="Data analyst specialized in metrics",
    description="Analyzes data and provides insights",
)

researcher = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    name="researcher",
    role="Information researcher",
    description="Gathers and synthesizes information",
)

# Create parent agent
team_leader = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    name="team_leader",
    description="Coordinates specialists",
    sub_agents=[analyst, researcher],
)

# Model can delegate to sub-agents
response = await team_leader.arun(
    input="Analyze Q4 sales and research competitors"
)
```

### Delegation Tool

Sub-agent delegation is automatic via generated tool:

```python
# Auto-generated tool signature:
async def sub_agent_task(
    member_id: str,  # ID or name of sub-agent
    task: str,       # Task description
) -> str:
    """Delegate task to specific sub-agent."""
    pass

# Model calls: sub_agent_task(member_id="analyst", task="...")
```

### Team Configuration

Configure delegation behavior:

```python
team_agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    sub_agents=[agent1, agent2],
    delegate_to_all_members=False,  # Delegate to specific member
    stream_member_events=True,      # Stream sub-agent events
    store_member_responses=True,    # Store sub-agent responses
)
```

### Sub-Agent Session Sharing

Sub-agents share session context:

```python
# Session store is automatically shared
team_agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    session_store=database_store,
    sub_agents=[analyst, researcher],  # Inherit session_store
)

# Session state changes are merged back
```

## Error Handling

### Retry Configuration

Configure automatic retries:

```python
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    retries=3,                    # Retry up to 3 times
    delay_between_retries=2,      # 2 seconds between retries
    exponential_backoff=True,     # 2s, 4s, 8s delays
)
```

### Exception Handling

Handle agent errors:

```python
from ii_agent.v1.exceptions import InputCheckError, OutputCheckError
from ii_agent.core.cancel import RunCancelledException

try:
    response = await agent.arun(input="Process this")

except InputCheckError as e:
    # Input validation failed
    print(f"Invalid input: {e}")

except OutputCheckError as e:
    # Output validation failed
    print(f"Invalid output: {e}")

except RunCancelledException as e:
    # Run was cancelled
    print(f"Cancelled: {e}")

except Exception as e:
    # General error
    print(f"Error: {e}")
```

### Run Status

Check run status:

```python
response = await agent.arun(input="Process this")

if response.status == RunStatus.COMPLETED:
    print("Success")
elif response.status == RunStatus.ERROR:
    print(f"Error: {response.error_message}")
elif response.status == RunStatus.ABORTED:
    print("Cancelled")
elif response.status == RunStatus.PAUSED:
    print("Paused for user input")
```

### Cancellation Support

Cancel long-running operations:

```python
from ii_agent.core.cancel import cancel_run

# Start run
run_id = "run123"
task = asyncio.create_task(agent.arun(input="Long task", run_id=run_id))

# Cancel if needed
await cancel_run(run_id)

try:
    response = await task
except RunCancelledException:
    print("Run was cancelled")
```

## Human-in-the-Loop (HITL)

### Paused Runs

Runs can pause for user input:

```python
# Run agent
response = await agent.arun(input="Process this")

# Check if paused
if response.status == RunStatus.PAUSED:
    # Get paused tool calls
    paused_tools = [t for t in response.tools if t.is_paused]

    # Get requirements
    for req in response.requirements:
        print(f"Requirement: {req.message}")
        print(f"Type: {req.type}")

# Continue with user input
updated_tools = [...]  # Updated tool executions
continued_response = await agent.acontinue_run(
    run_response=response,
    updated_tools=updated_tools,
    stream=True,
)
```

### Continue Run

Resume paused runs:

```python
# Continue from run_id
response = await agent.acontinue_run(
    run_id="run123",
    updated_tools=updated_tools,
    stream=True,
    stream_events=True,
)
```

## Advanced Patterns

### Sandbox Integration

Use E2B sandbox for code execution:

```python
# Initialize sandbox (lazy)
sandbox = await agent.init_sandbox()

# Sandbox is reused across runs
response = await agent.arun(input="Run Python code")
```

### Media Support

Pass media to agents:

```python
from ii_agent.v1.media import Image, Audio, Video, File

# Create media objects
image = Image(object_id="img123", format="png")
audio = Audio(object_id="aud123", format="mp3")

# Pass to agent
response = await agent.arun(
    input="Analyze this image and audio",
    images=[image],
    audio=[audio],
)
```

### Metadata & Context

Add custom metadata:

```python
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    metadata={
        "environment": "production",
        "version": "1.0",
    },
)

# Per-run metadata
response = await agent.arun(
    input="Process this",
    metadata={
        "request_id": "req123",
    },
)
```

### Run Context Access

Access run context in hooks:

```python
async def context_hook(
    run_response: RunOutput,
    run_context: RunContext,
    **kwargs
) -> None:
    # Access context
    run_id = run_context.run_id
    session_id = run_context.session_id
    user_id = run_context.user_id
    session_state = run_context.session_state
    metadata = run_context.metadata
```

## Best Practices

### 1. Always Use Async/Await

```python
# ✅ GOOD
async def create_agent():
    response = await agent.arun(input="...")

# ❌ BAD - Blocks event loop
def create_agent():
    response = asyncio.run(agent.arun(input="..."))
```

### 2. Proper Resource Cleanup

Tools are automatically cleaned up, but custom resources need manual handling:

```python
# ✅ GOOD - Use try/finally
async def process():
    resource = await initialize_resource()
    try:
        response = await agent.arun(input="...")
    finally:
        await resource.cleanup()
```

### 3. Handle Errors Gracefully

```python
# ✅ GOOD - Tools return ToolResult with error flag
async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
    try:
        result = await self.process(tool_input)
        return ToolResult(llm_content=result, is_error=False)
    except Exception as e:
        return ToolResult(llm_content=f"Error: {str(e)}", is_error=True)
```

### 4. Use Session State for Persistence

```python
# ✅ GOOD - Use session state
run_context.session_state["user_data"] = data

# ❌ BAD - Instance variables don't persist
self.user_data = data  # Lost between runs
```

### 5. Stream for Long Operations

```python
# ✅ GOOD - Stream for better UX
async for event in agent.arun(input="Long task", stream=True):
    print(event.content, end="")

# ❌ BAD - Wait for entire response
response = await agent.arun(input="Long task")
print(response.content)  # User waits
```

### 6. Limit Tool Calls

```python
# ✅ GOOD - Prevent infinite loops
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    tool_call_limit=10,  # Max 10 tool calls
)
```

### 7. Use Retry for Reliability

```python
# ✅ GOOD - Handle transient failures
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    retries=3,
    exponential_backoff=True,
)
```

## Resources

### References

Detailed documentation in [references/](references/) directory:

- **[architecture.md](references/architecture.md)** - Complete agent architecture reference including components, lifecycle, data structures, session management, tool system, streaming, hooks, error handling, media handling, sandbox integration, and metrics

- **[patterns.md](references/patterns.md)** - Best practices and patterns for async/await, tool development, error handling, session management, streaming, model integration, sub-agents, performance optimization, and anti-patterns to avoid

### Assets

Template code in [assets/](assets/) directory:

- **[agent_template.py](assets/agent_template.py)** - Production-ready boilerplate for creating agents with examples of tools, hooks, streaming, teams, and error handling

### Quick Reference

Common agent configurations:

```python
# Simple agent
IIAgent(user_id, session_id, model, name, description, instructions)

# Agent with tools
IIAgent(..., tools=[tool1, tool2], tool_call_limit=10)

# Agent with hooks
IIAgent(..., pre_hooks=[hook1], post_hooks=[hook2])

# Team agent
IIAgent(..., sub_agents=[agent1, agent2])

# Persistent agent
IIAgent(..., session_store=store, session_state={...})

# Resilient agent
IIAgent(..., retries=3, exponential_backoff=True)
```

## Troubleshooting

### Common Issues

**Issue: Tools not executing**
- Check `tool_call_limit` is not exceeded
- Ensure tool `name` and `description` are clear
- Verify tool is in agent's `tools` list

**Issue: Session state not persisting**
- Ensure `session_store` is configured (not NoOpSessionStore)
- Verify database connection is working
- Check `should_persist` property returns True

**Issue: Run hangs indefinitely**
- Check for blocking operations (use async/await)
- Verify no `time.sleep()` in async code (use `asyncio.sleep()`)
- Check MCP tools are properly connected/disconnected

**Issue: Memory leaks**
- Ensure tools implement proper cleanup in `close()`
- Verify MCP tools are disconnected in finally block
- Check for circular references in session state

**Issue: Sub-agent events not streaming**
- Enable `stream_member_events=True` on parent agent
- Ensure sub-agent runs with `stream=True`
- Check event filtering with `events_to_skip`

## Example Implementations

See [assets/agent_template.py](assets/agent_template.py) for complete working examples of:
- Basic agent usage
- Streaming responses
- Custom tools
- Team agents with delegation
- Error handling and retries
- Hooks integration
