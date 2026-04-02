# Agent Development Patterns & Best Practices

## Async/Await Patterns

### ✅ Pattern: Consistent Async Usage

Always use `async`/`await` for I/O-bound operations:

```python
# ✅ GOOD
async def arun(self, input: str) -> RunOutput:
    session = await self._aread_or_create_session(session_id=session_id)
    response = await self.model.aresponse(messages=messages)
    return response

# ❌ BAD - Mixing sync and async
def run(self, input: str) -> RunOutput:
    session = self._read_session_sync(session_id)  # Blocks event loop
    response = asyncio.run(self.model.aresponse(messages=messages))  # Creates new event loop
    return response
```

### ✅ Pattern: AsyncIterator for Streaming

Use `AsyncIterator` for streaming responses:

```python
# ✅ GOOD
async def _arun_stream(
    self, ...
) -> AsyncIterator[Union[RunOutputEvent, RunOutput]]:
    async for event in self.model.astream(messages=messages):
        await raise_if_cancelled(run_id)  # Check cancellation
        yield event

# Usage
async for event in agent.arun(input="...", stream=True):
    if isinstance(event, RunOutput):
        print(f"Final: {event.content}")
    else:
        print(f"Event: {event.type}")
```

### ✅ Pattern: Double-Check Locking for Lazy Initialization

Use async locks for thread-safe lazy initialization:

```python
# ✅ GOOD - Thread-safe lazy initialization
class IIAgent:
    _internal_lock = asyncio.Lock()
    _sandbox: Optional[SandboxManager] = None

    async def init_sandbox(self) -> SandboxManager:
        if self._sandbox is None or await self._sandbox.get_status() == SandboxStatus.NOT_INITIALIZED:
            async with self._internal_lock:  # Acquire lock
                # Double-check after acquiring lock
                if self._sandbox is None or await self._sandbox.get_status() == SandboxStatus.NOT_INITIALIZED:
                    self._sandbox = await E2BSandboxManager.init(session_id=self.session_id)
        return self._sandbox

# ❌ BAD - Race condition
async def init_sandbox_bad(self) -> SandboxManager:
    if self._sandbox is None:
        self._sandbox = await E2BSandboxManager.init(session_id=self.session_id)  # Race!
    return self._sandbox
```

### ✅ Pattern: Async Context Managers

Use async context managers for resource management when appropriate:

```python
# ✅ GOOD - But note: not used in agent.py since cleanup is in finally
async with self._internal_lock:
    # Critical section
    pass

# Agent pattern: Always cleanup in finally
try:
    # Main logic
    pass
finally:
    # Always cleanup
    self._disconnect_connectable_tools()
    await self._disconnect_mcp_tools()
    await cleanup_run(run_id)
```

### ✅ Pattern: Cancellation Support

Check for cancellation at key points:

```python
# ✅ GOOD
try:
    await raise_if_cancelled(run_id)  # Before expensive operation
    model_response = await self.model.aresponse(messages=messages)
    await raise_if_cancelled(run_id)  # After expensive operation

    async for event in self._process_stream():
        await raise_if_cancelled(run_id)  # In loops
        yield event

except RunCancelledException as e:
    run_response.status = RunStatus.ABORTED
    run_response.content = str(e)
```

## Tool Development Patterns

### ✅ Pattern: Tool as Async Generator (Streaming)

For tools that stream results:

```python
# ✅ GOOD - Tool that streams
async def adelegate_task_to_member(
    member_id: str,
    task: str,
) -> AsyncIterator[Union[RunOutputEvent, str]]:
    """Delegate to sub-agent with streaming."""
    sub_agent = self._find_sub_agent_by_id(member_id)
    if sub_agent is None:
        yield f"Sub-agent '{member_id}' not found."
        return

    # Stream sub-agent responses
    async for event in sub_agent.arun(input=task, stream=True):
        if isinstance(event, RunOutput):
            yield event.content or "Sub-agent completed."
        else:
            yield event  # Forward events
```

### ✅ Pattern: Tool Error Handling

Tools should handle errors gracefully:

```python
# ✅ GOOD
class DatabaseTool(BaseAgentTool):
    name = "database"
    display_name = "Database"
    description = "Execute database queries"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    read_only = True

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")

        try:
            result = await self.db.execute(query)
            return ToolResult(
                llm_content=f"Query successful: {result}",
                is_error=False,
            )
        except DatabaseError as e:
            logger.error(f"Database query failed: {e}")
            return ToolResult(
                llm_content=f"Error executing query: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return ToolResult(
                llm_content=f"Unexpected error: {str(e)}",
                is_error=True,
            )

# ❌ BAD - Unhandled exceptions break agent flow
class BadDatabaseTool(BaseAgentTool):
    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")
        result = await self.db.execute(query)  # May raise exception!
        return ToolResult(llm_content=result, is_error=False)
```

### ✅ Pattern: Tool Connection Management

Tools requiring connections should use connect/close pattern:

```python
# ✅ GOOD
class DatabaseTool(BaseAgentTool):
    name = "database"
    display_name = "Database"
    description = "Execute database queries"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    read_only = True
    requires_connect = True

    def __init__(self):
        self._connection = None

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
                llm_content="Tool not connected. Call connect() first.",
                is_error=True,
            )

        result = await self._connection.execute(query)
        return ToolResult(llm_content=str(result), is_error=False)
```

### ✅ Pattern: MCP Tool Integration

MCP tools follow a specific pattern:

```python
# ✅ GOOD - MCP tool usage
from ii_agent.v1.tools.mcp import MCPTools

# Tool with auto-connect
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
    tools=[mcp_tool],  # Agent will auto-connect and disconnect
)
```

## Error Handling Patterns

### ✅ Pattern: Try-Finally for Cleanup

Always use try-finally to ensure cleanup:

```python
# ✅ GOOD
async def _arun(self, ...) -> RunOutput:
    try:
        # Register run for tracking
        await register_run(run_id)

        # Main logic
        model_response = await self.model.aresponse(...)

        return run_response

    except RunCancelledException as e:
        # Handle cancellation
        run_response.status = RunStatus.ABORTED
        return run_response

    except Exception as e:
        # Handle errors
        run_response.status = RunStatus.ERROR
        raise

    finally:
        # ALWAYS cleanup - even if exception or return
        self._disconnect_connectable_tools()
        await self._disconnect_mcp_tools()
        await cleanup_run(run_id)
```

### ✅ Pattern: Retry with Exponential Backoff

Implement robust retry logic:

```python
# ✅ GOOD
num_attempts = self.retries + 1

for attempt in range(num_attempts):
    try:
        return await self._arun(...)

    except Exception as e:
        if attempt < num_attempts - 1:
            # Calculate delay with exponential backoff
            if self.exponential_backoff:
                delay = self.delay_between_retries * (2 ** attempt)
            else:
                delay = self.delay_between_retries

            logger.warning(f"Attempt {attempt + 1}/{num_attempts} failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)  # Use asyncio.sleep, not time.sleep
            continue
        else:
            logger.error(f"All {num_attempts} attempts failed")
            raise
```

### ✅ Pattern: Error Status Management

Properly track run status:

```python
# ✅ GOOD
try:
    run_response.status = RunStatus.RUNNING
    # ... logic ...
    run_response.status = RunStatus.COMPLETED

except RunCancelledException as e:
    run_response.status = RunStatus.ABORTED
    run_response.content = str(e)

except Exception as e:
    run_response.status = RunStatus.ERROR
    run_response.error_message = str(e)
    if not run_response.content:
        run_response.content = str(e)
    raise

finally:
    # Save run with status
    await self._save_run(run_response)
```

## Session Management Patterns

### ✅ Pattern: Session State Immutability

Treat session state carefully to avoid mutation bugs:

```python
# ✅ GOOD - Deep copy when passing to sub-agents
from copy import deepcopy

member_session_state = deepcopy(run_context.session_state or {})
sub_agent_response = await sub_agent.arun(
    input=task,
    session_state=member_session_state,
)

# ❌ BAD - Direct reference causes mutation
sub_agent_response = await sub_agent.arun(
    input=task,
    session_state=run_context.session_state,  # Shared reference!
)
```

### ✅ Pattern: Session State Initialization

Initialize session state with standard fields:

```python
# ✅ GOOD
def _initialize_session_state(
    self,
    session_state: Dict[str, Any],
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Initialize session state with standard fields."""
    if user_id:
        session_state["current_user_id"] = user_id
    if session_id is not None:
        session_state["current_session_id"] = session_id
    if run_id is not None:
        session_state["current_run_id"] = run_id
    return session_state
```

### ✅ Pattern: Session Persistence

Check persistence capability before database calls:

```python
# ✅ GOOD
@property
def should_persist(self) -> bool:
    """Check if session store is available for persistence."""
    return self.session_store is not None and not isinstance(
        self.session_store, NoOpSessionStore
    )

# Usage
if self.should_persist:
    await self.session_store.save_session(session)
```

## Streaming Patterns

### ✅ Pattern: Event Filtering

Filter events to control verbosity:

```python
# ✅ GOOD
def handle_event(
    event: RunOutputEvent,
    run_response: RunOutput,
    events_to_skip: Optional[List[RunEvent]] = None,
    store_events: bool = False,
) -> Optional[RunOutputEvent]:
    """Handle event with filtering and storage."""
    if events_to_skip and event.type in events_to_skip:
        # Skip verbose events like run_content_delta
        if store_events:
            run_response.add_event(event)
        return None  # Don't yield

    if store_events:
        run_response.add_event(event)

    return event  # Yield

# Default filtering
self.events_to_skip = [
    RunEvent.run_content_delta,  # Too verbose
    RunEvent.reasoning_delta,     # Too verbose
]
```

### ✅ Pattern: Dual Streaming Modes

Support both content and event streaming:

```python
# ✅ GOOD
if stream:
    if stream_events:
        # Detailed event streaming
        async for event in self._arun_stream(stream_events=True):
            if isinstance(event, RunOutput):
                print(f"Final: {event.content}")
            elif event.type == RunEvent.tool_call_started:
                print(f"Tool: {event.data.get('tool_name')}")
            else:
                print(f"Event: {event.type}")
    else:
        # Content-only streaming
        async for event in self._arun_stream(stream_events=False):
            if isinstance(event, RunOutput):
                print(f"Final: {event.content}")
```

### ✅ Pattern: Sub-Agent Event Forwarding

Forward sub-agent events with context:

```python
# ✅ GOOD
async for event in sub_agent.arun(input=task, stream=True, stream_events=True):
    if isinstance(event, RunOutput):
        sub_agent_response = event
        continue

    # Add parent context to event
    event.parent_run_id = parent_run_id
    event.delegated_from = parent_agent.name
    event.is_sub_agent_event = True

    # Forward to parent stream
    yield event
```

## Model Integration Patterns

### ✅ Pattern: Model Abstraction

Use model abstraction for provider independence:

```python
# ✅ GOOD - Provider-agnostic
from ii_agent.v1.models.openai import OpenAIChat
from ii_agent.v1.models.anthropic import Claude

# Works with any model
def create_agent(model: Model, **kwargs) -> IIAgent:
    return IIAgent(
        user_id="user",
        session_id="session",
        model=model,  # Any Model implementation
        **kwargs
    )

# Use OpenAI
gpt_agent = create_agent(model=OpenAIChat(id="gpt-4"))

# Use Claude
claude_agent = create_agent(model=Claude(id="claude-3-5-sonnet-20241022"))
```

### ✅ Pattern: Tool Choice Configuration

Configure model tool selection:

```python
# ✅ GOOD - Explicit tool choice
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    tools=[search_tool, calculator_tool],
    tool_choice="auto",  # Let model decide
    # tool_choice="required",  # Force tool use
    # tool_choice={"type": "tool", "name": "search"},  # Specific tool
)
```

### ✅ Pattern: Tool Call Limits

Prevent infinite tool call loops:

```python
# ✅ GOOD
agent = IIAgent(
    user_id="user",
    session_id="session",
    model=model,
    tools=[...],
    tool_call_limit=10,  # Max tool calls per run
)
```

## Sub-Agent/Team Patterns

### ✅ Pattern: Sub-Agent Initialization

Initialize sub-agents with shared context:

```python
# ✅ GOOD
def _initialize_sub_agent(self, sub_agent: "IIAgent") -> None:
    """Initialize sub-agent with shared context from parent."""
    # Share session store
    if sub_agent.session_store is None or isinstance(
        sub_agent.session_store, NoOpSessionStore
    ):
        sub_agent.session_store = self.session_store

# Called automatically in __post_init__
if self.sub_agents:
    for sub_agent in self.sub_agents:
        self._initialize_sub_agent(sub_agent)
```

### ✅ Pattern: Delegation Tool Auto-Generation

Auto-generate delegation tools:

```python
# ✅ GOOD - Auto-generated in _determine_tools_for_model
if self.sub_agents:
    delegate_func = self._get_delegate_task_function(
        run_response=run_response,
        run_context=run_context,
        session=session,
        stream=stream,
        stream_events=stream_events,
    )
    _tools.append(delegate_func)

# Model can now call: sub_agent_task(member_id="analyst", task="...")
```

### ✅ Pattern: Session State Merging

Merge sub-agent state changes back to parent:

```python
# ✅ GOOD
sub_agent_response = await sub_agent.arun(
    input=task,
    session_state=member_session_state,
)

# Merge changes back to parent
if sub_agent_response.session_state:
    merge_dictionaries(
        run_context.session_state or {},
        sub_agent_response.session_state,
    )
```

## Performance & Optimization

### ✅ Pattern: Lazy Resource Initialization

Initialize expensive resources only when needed:

```python
# ✅ GOOD
async def init_sandbox(self) -> SandboxManager:
    """Lazy initialization of sandbox."""
    if self._sandbox is None:
        async with self._internal_lock:
            if self._sandbox is None:
                self._sandbox = await E2BSandboxManager.init(
                    session_id=self.session_id
                )
    return self._sandbox

# ❌ BAD - Eager initialization
def __post_init__(self):
    self._sandbox = asyncio.run(E2BSandboxManager.init())  # Always created!
```

### ✅ Pattern: Efficient Media Handling

Validate and handle media separately:

```python
# ✅ GOOD
image_artifacts, video_artifacts, audio_artifacts, file_artifacts = (
    validate_media_object_id(
        images=images,
        videos=videos,
        audios=audio,
        files=files
    )
)

# Media stored separately, not in context
run_input = RunInput(
    input_content=validated_input,
    images=image_artifacts,
    videos=video_artifacts,
    audios=audio_artifacts,
    files=file_artifacts,
)
```

## Anti-Patterns to Avoid

### ❌ Anti-Pattern: Blocking Event Loop

```python
# ❌ BAD - Blocks event loop
def sync_operation():
    time.sleep(5)  # Blocks!
    return result

async def agent_method(self):
    result = sync_operation()  # Blocks entire event loop!

# ✅ GOOD - Use async
async def async_operation():
    await asyncio.sleep(5)  # Yields control
    return result

async def agent_method(self):
    result = await async_operation()  # Non-blocking
```

### ❌ Anti-Pattern: Creating New Event Loops

```python
# ❌ BAD - Creates new event loop
async def agent_method(self):
    result = asyncio.run(self.model.aresponse(...))  # New event loop!

# ✅ GOOD - Use existing event loop
async def agent_method(self):
    result = await self.model.aresponse(...)  # Uses current event loop
```

### ❌ Anti-Pattern: Ignoring Cleanup

```python
# ❌ BAD - No cleanup on error
async def agent_run(self):
    await tool.connect()
    result = await self.process()  # If this fails, tool not cleaned!
    await tool.close()

# ✅ GOOD - Always cleanup
async def agent_run(self):
    try:
        await tool.connect()
        result = await self.process()
    finally:
        await tool.close()  # Always runs
```

### ❌ Anti-Pattern: Mutable Default Arguments

```python
# ❌ BAD - Mutable default
def __init__(self, tools: List[Tool] = []):
    self.tools = tools  # Shared across instances!

# ✅ GOOD - None with post-init
def __init__(self, tools: Optional[List[Tool]] = None):
    self.tools = list(tools) if tools else []
```
