# Agent Architecture Reference

## Core Components

### 1. IIAgent Class

The main agent class is a dataclass with the following key components:

```python
@dataclass
class IIAgent:
    user_id: str
    session_id: str
    model: Model
    name: str = None

    # Tools and capabilities
    tools: Optional[List[Union[BaseAgentTool, Toolkit, Callable, Function, Dict]]] = None

    # Sub-agents for delegation
    sub_agents: Optional[List["IIAgent"]] = None

    # Hooks for customization
    pre_hooks: Optional[List[Callable]] = None
    post_hooks: Optional[List[Callable]] = None
    tool_hooks: Optional[List[Callable]] = None

    # Session management
    session_store: Optional[SessionStore] = None
    session_state: Optional[Dict[str, Any]] = None
    session_summary_manager: Optional[SessionSummaryManager] = None

    # Streaming configuration
    stream: Optional[bool] = None
    stream_events: Optional[bool] = None
```

### 2. Run Lifecycle

Every agent run goes through these phases:

**Initial Run (arun):**
1. Create run task in database (if persistence enabled)
2. Read or create session
3. Initialize session state
4. Execute pre-hooks
5. Determine tools for model
6. Prepare run messages
7. Generate response from model (includes tool execution)
8. Update RunOutput with model response
9. Store media if enabled
10. Execute post-hooks
11. Create session summary
12. Cleanup and store (scrub, calculate metrics, save session)

**Continue Run (acontinue_run):**
- Used for Human-in-the-Loop (HITL) scenarios
- Resumes paused runs with updated tool responses
- Follows similar lifecycle but handles existing messages

### 3. Key Data Structures

**RunOutput:**
- Contains the complete result of an agent run
- Includes: run_id, session_id, content, messages, tools, metrics, status
- Status values: RUNNING, COMPLETED, PAUSED, ABORTED, ERROR

**RunContext:**
- Execution context for a run
- Contains: run_id, session_id, user_id, session_state, metadata

**RunInput:**
- Captures original user input
- Supports: text, images, videos, audio, files

**ModelResponse:**
- Response from the LLM provider
- Contains: content, messages, tool_calls, metrics

### 4. Session Management

**AgentSession:**
- Persistent session across multiple runs
- Contains: session_id, user_id, agent_id, session_data, runs history
- Stored via SessionStore (database or NoOpSessionStore)

**Session State:**
- Mutable state dictionary persisted across runs
- Automatically includes: current_user_id, current_session_id, current_run_id
- Can be modified by tools and hooks

### 5. Tool System

**Tool Types:**
- `BaseAgentTool` - Base class for custom tools
- `Toolkit` - Collection of related tools
- `Callable` - Plain functions as tools
- `Function` - Wrapped function with metadata
- `Dict` - Tool definition as dictionary

**Tool Lifecycle:**
1. Tools are processed and validated
2. MCP tools are connected (if applicable)
3. Connectable tools are initialized
4. Tools are passed to model
5. Model generates tool calls
6. Tools are executed
7. Results are added to messages
8. Tools are disconnected in finally block

**Special Tools:**
- MCP (Model Context Protocol) tools - External tool servers
- Connectable tools - Tools requiring connection management
- Sub-agent delegation tools - Auto-generated for team functionality

### 6. Sub-Agent/Team Pattern

**Delegation Flow:**
1. Parent agent has `sub_agents` list
2. Delegation function is auto-generated as a tool
3. Model calls delegation tool with member_id and task
4. Sub-agent runs with shared session context
5. Sub-agent events can stream to parent
6. Results returned to parent agent
7. Session state changes are merged

**Configuration:**
- `delegate_to_all_members` - Delegate to all sub-agents
- `stream_member_events` - Stream sub-agent events to parent
- `store_member_responses` - Store sub-agent responses in parent

### 7. Streaming Architecture

**Two Streaming Modes:**
- `stream=True` - Stream response content
- `stream_events=True` - Stream detailed events

**Event Types:**
- RunStarted, RunCompleted, RunCancelled, RunError
- RunContentDelta, RunContentCompleted
- ToolCallStarted, ToolCallCompleted
- ReasoningStarted, ReasoningDelta, ReasoningCompleted
- PreHookStarted, PreHookCompleted
- PostHookStarted, PostHookCompleted
- SessionSummaryStarted, SessionSummaryCompleted
- SandboxInitialized
- RunPaused, RunContinued

**Streaming Implementation:**
```python
async for event in agent.arun(input="...", stream=True, stream_events=True):
    if isinstance(event, RunOutput):
        # Final result
        pass
    else:
        # RunOutputEvent - process event
        pass
```

### 8. Hooks System

**Hook Types:**

**Pre-hooks:**
- Called after session is loaded, before processing
- Can modify run input
- Use case: Input validation, context injection

**Post-hooks:**
- Called after output generation, before response returned
- Can modify run output
- Use case: Output validation, logging, formatting

**Tool-hooks:**
- Called around tool execution
- Middleware for tool calls
- Use case: Tool authorization, rate limiting, logging

**Hook Signature:**
```python
async def pre_hook(
    run_response: RunOutput,
    run_context: RunContext,
    run_input: RunInput,
    session: AgentSession,
    user_id: Optional[str] = None,
    **kwargs
) -> None:
    # Modify run_input or run_context as needed
    pass
```

### 9. Error Handling & Cancellation

**Retry Logic:**
- Configurable retries with exponential backoff
- `retries` - Number of retry attempts
- `delay_between_retries` - Base delay in seconds
- `exponential_backoff` - Double delay each retry

**Cancellation:**
- Runs can be cancelled via `cancel_run(run_id)`
- Raises `RunCancelledException`
- Cleanup always happens in finally block
- Run status set to ABORTED

**Resource Cleanup:**
- Always in finally block
- Disconnect connectable tools
- Disconnect MCP tools
- Cleanup run tracking
- Save session and metrics

### 10. Media Handling

**Supported Media Types:**
- `Image` - Image files with object_id and format
- `Video` - Video files with object_id and format
- `Audio` - Audio files with object_id and format
- `File` - Generic files with object_id and name

**Media Validation:**
- Media objects validated for proper IDs
- Stored separately for efficient handling
- Can be passed to model as part of messages

### 11. Sandbox Integration

**E2BSandboxManager:**
- Lazy initialization via `init_sandbox()`
- Double-check locking pattern for thread safety
- Configured per session
- Auto-configured MCP tools
- Status tracking: NOT_INITIALIZED, INITIALIZING, INITIALIZED, ERROR

### 12. Database Integration

**SessionStore:**
- Abstract interface for persistence
- Implementations: Database store, NoOpSessionStore
- Methods:
  - `get_session()` - Load session
  - `save_session()` - Persist session
  - `get_by_run_id()` - Load run by ID
  - `save_run()` - Persist run
  - `update_run_status()` - Update run status
  - `get_or_create_run_task()` - Run lifecycle tracking

### 13. Metrics & Monitoring

**Metrics Tracked:**
- Run duration (start/stop timer)
- Token usage (input/output tokens)
- Tool call counts
- Model response times
- Error counts

**Metrics Object:**
```python
run_response.metrics = Metrics()
run_response.metrics.start_timer()
# ... execution ...
run_response.metrics.stop_timer()
```
