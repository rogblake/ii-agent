# LLM Refactor Plan

Related docs:

- [Chat and Agent Migration Plan](./chat-agent-migration-plan.md)
- [God Service Split Design](./god-service-split.md)

## Goal

Unify the duplicated provider logic currently split across:

- `src/ii_agent/chat/llm/*`
- `src/ii_agent/engine/v1/models/*`

into a shared provider client layer under:

- `src/ii_agent/core/llm/*`

without collapsing chat runtime concerns and agent runtime concerns into the
same package.

This plan is specifically about provider transport, request shaping, response
parsing, provider metadata continuity, and provider resource handling. It is
not a plan to merge the full chat runtime and full agent runtime into one
execution stack in a single step.

## Problem

Today the codebase has two parallel LLM implementations:

- chat-specific provider clients created by
  [chat/llm/factory.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/factory.py#L16)
- agent/runtime model providers created by
  [engine/v1/models/utils.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/utils.py#L11)

The duplication is real at the provider level:

- OpenAI Responses request shaping, reasoning handling, and response continuity
  appear in both
  [chat/llm/openai.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/openai.py#L798)
  and
  [engine/v1/models/openai/responses.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/openai/responses.py#L206)
- Gemini tool conversion, thought signatures, and thinking handling appear in
  both
  [chat/llm/gemini.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/gemini.py#L182)
  and
  [engine/v1/models/google/gemini.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/google/gemini.py#L266)
- Anthropic thinking blocks, tool formatting, and provider metadata appear in
  both
  [chat/llm/anthropic/provider.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/anthropic/provider.py#L367)
  and
  [engine/v1/models/anthropic/claude.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/anthropic/claude.py#L226)

At the same time, the runtimes are not actually equivalent:

- chat owns message persistence, SSE event shaping, chat-specific tool loops,
  and chat-specific summarization:
  [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L184),
  [chat/llm_loop_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm_loop_service.py#L33),
  [chat/context_manager.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/context_manager.py#L38)
- engine/v1 owns agent runs, pause/resume requirements, structured outputs,
  sub-agents, sandbox lifecycle, and generic run events:
  [engine/v1/models/base.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/base.py#L324),
  [engine/v1/agents/agent.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/agents/agent.py#L98),
  [engine/v1/agents/response_handler.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/agents/response_handler.py#L54)

The correct target is therefore:

- one shared provider client layer
- two host-specific adapters
- no chat imports from core
- no engine/v1 imports from core

## Current Boundary Violations

`core/llm` already exists, but it is not yet a true core layer.

For example:

- [core/llm/execution_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/core/llm/execution_service.py#L14)
  imports `chat.llm`, `chat.schemas`, and `chat.tool_service`

That file is currently a chat-oriented orchestration service in the wrong
package.

Separately, the engine execution service is not an LLM provider service at all:

- [engine/agents/execution_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/agents/execution_service.py#L1)

That service handles task locking, realtime events, and milestone status
updates. It should remain in `engine` or a future `agent/application` package.
It should not move into `chat`, and it should not move into `core/llm`.

## Target Architecture

### Shared Layer

Add a neutral provider client layer under:

```text
src/ii_agent/core/llm/
  __init__.py
  factory.py
  types.py
  capabilities.py
  resources.py
  provider_state.py
  providers/
    __init__.py
    base.py
    openai_responses.py
    anthropic_messages.py
    gemini_generate.py
    openai_compat.py
```

This layer should own:

- provider selection from `LLMConfig`
- provider request formatting
- provider response parsing
- provider-specific streaming event parsing
- provider capabilities
- provider continuity metadata
- provider-side file and container resource contracts

This layer must not own:

- chat database models
- chat SSE events
- engine run events
- tool execution loops
- session locking
- milestone updates
- ORM persistence

### Host Adapters

Keep host-specific adapters outside `core`.

```text
src/ii_agent/chat/llm/
  bridge.py
  message_adapter.py
  event_adapter.py
  provider_state_store.py

src/ii_agent/engine/v1/models/
  shared_bridge.py
  message_adapter.py
  response_adapter.py
  provider_state_store.py
```

Chat remains responsible for:

- converting `chat.schemas.Message` to shared core messages
- converting shared stream events to chat SSE events
- running the chat tool loop
- persisting chat messages and chat provider metadata

Engine/v1 remains responsible for:

- converting `engine.v1.models.message.Message` to shared core messages
- converting shared responses to `ModelResponse`
- running the agent tool loop
- pause/resume requirements
- sub-agents, sandbox orchestration, and run events

## Shared Contracts

### Shared Request/Response Types

Introduce provider-neutral types in `core/llm/types.py`.

Example shape:

```python
@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    tools: list[LLMTool] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | type[BaseModel] | None = None
    builtin_tools: BuiltinToolConfig | None = None
    provider_options: dict[str, Any] | None = None


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    blocks: list[LLMBlock]
    provider_state: dict[str, Any] | None = None


@dataclass
class LLMResponse:
    role: str = "assistant"
    blocks: list[LLMBlock] = field(default_factory=list)
    finish_reason: FinishReason | None = None
    usage: LLMUsage | None = None
    parsed: Any = None
    citations: LLMCitations | None = None
    provider_state: dict[str, Any] | None = None
    generated_artifacts: list[LLMArtifact] = field(default_factory=list)
```

The important point is not the exact class names. The important point is that
these types must not depend on either:

- `ii_agent.chat.schemas`
- `ii_agent.engine.v1.models.*`

### Shared Provider Interface

Add `core/llm/providers/base.py`:

```python
class BaseLLMClient(ABC):
    @abstractmethod
    async def complete(
        self,
        request: LLMRequest,
        ctx: LLMRequestContext | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream(
        self,
        request: LLMRequest,
        ctx: LLMRequestContext | None = None,
    ) -> AsyncIterator[LLMStreamEvent]: ...

    @abstractmethod
    def capabilities(self) -> LLMCapabilities: ...
```

### Provider State Store

Provider clients need host-owned persistence for:

- response continuity state such as OpenAI `response_id`
- uploaded provider file IDs
- provider containers

That means the shared layer needs a persistence protocol, not direct ORM access.

Add `core/llm/provider_state.py`:

```python
class ProviderStateStore(Protocol):
    async def resolve_input_files(
        self,
        *,
        session_id: str,
        provider: str,
        files: list[AppFileRef],
    ) -> list[ProviderFileRef]: ...

    async def get_or_create_container(
        self,
        *,
        session_id: str,
        provider: str,
        purpose: str,
    ) -> ProviderContainerRef | None: ...

    async def load_message_state(
        self,
        *,
        session_id: str,
        provider: str,
    ) -> dict[str, Any]: ...

    async def save_message_state(
        self,
        *,
        session_id: str,
        provider: str,
        state: dict[str, Any],
    ) -> None: ...
```

This is the boundary that allows:

- chat to keep using its provider file/container tables
- engine to use a different persistence store later if needed
- core to stay free of application-layer ORM code

## What Moves Into The Shared Layer

### Move

- OpenAI Responses transport and parsing logic
- Anthropic Messages transport and parsing logic
- Gemini transport and parsing logic
- OpenAI-compatible transport logic
- provider capability detection
- request-level reasoning/tool config translation
- provider continuity parsing
- provider-neutral citations and usage models

### Do Not Move

- [chat/llm_loop_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm_loop_service.py#L33)
- [chat/tool_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/tool_service.py#L36)
- [chat/context_manager.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/context_manager.py#L38)
- [engine/v1/models/base.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/base.py#L324)
- [engine/v1/agents/response_handler.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/agents/response_handler.py#L54)
- [engine/agents/execution_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/agents/execution_service.py#L1)

These are runtime orchestration layers, not provider transport layers.

## Directory Plan

### Core

```text
src/ii_agent/core/llm/
  factory.py
  types.py
  capabilities.py
  resources.py
  provider_state.py
  providers/
    base.py
    openai_responses.py
    anthropic_messages.py
    gemini_generate.py
    openai_compat.py
```

### Chat

Keep or add:

```text
src/ii_agent/chat/llm/
  bridge.py
  message_adapter.py
  event_adapter.py
  provider_state_store.py
```

Move the current `core/llm/execution_service.py` behavior into chat
application-level orchestration if it still depends on chat types and chat tools.

Likely destination:

```text
src/ii_agent/chat/application/llm_execution_service.py
```

or, if the current flat layout remains for now:

```text
src/ii_agent/chat/llm_execution_service.py
```

### Engine

Keep provider bridges in engine/v1 close to current model abstractions:

```text
src/ii_agent/engine/v1/models/
  shared_bridge.py
  message_adapter.py
  response_adapter.py
  provider_state_store.py
```

## Migration Principles

1. Extract neutral types before moving any provider implementation.
2. Do not move code into `core` if it imports `chat` or `engine`.
3. Keep chat and engine adapters thin and reversible during migration.
4. Move one provider at a time, starting with OpenAI Responses.
5. Preserve existing external behavior before cleaning internals.
6. Do not merge chat and engine tool loops in this refactor.
7. Do not move agent execution orchestration into `chat`.

## Phase Plan

### Phase 0: Characterize Existing Behavior

Goal:

- freeze provider behavior before extracting shared code

Work:

- add or confirm characterization coverage for:
  - OpenAI Responses content streaming
  - OpenAI reasoning summary handling
  - OpenAI `previous_response_id` continuity
  - Anthropic thinking blocks and signatures
  - Anthropic tool calls and provider-executed tool results
  - Gemini thought signatures and tool calls

Exit criteria:

- provider-level behavior is covered in tests at the request/response boundary

### Phase 1: Introduce Neutral Core Types

Goal:

- make `core/llm` a real dependency sink instead of a chat-dependent package

Work:

- add `types.py`, `capabilities.py`, `resources.py`, `provider_state.py`
- define shared request/response contracts
- add a neutral `BaseLLMClient`
- add adapters in chat and engine/v1 that convert existing message/response
  models to the shared contracts

Exit criteria:

- `core/llm` no longer depends on `chat.schemas`
- `core/llm` no longer depends on `engine.v1.models.*`

### Phase 2: Extract OpenAI First

Goal:

- prove the architecture on the most duplicated provider

Work:

- create `core/llm/providers/openai_responses.py`
- move duplicated OpenAI Responses request shaping there
- move reasoning summary handling there
- move response continuity handling there
- keep host-owned resource persistence behind `ProviderStateStore`
- implement:
  - `ChatOpenAIProviderStateStore`
  - `EngineOpenAIProviderStateStore`

Source logic to consolidate:

- [chat/llm/openai.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/openai.py#L798)
- [engine/v1/models/openai/responses.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/openai/responses.py#L206)

Exit criteria:

- chat OpenAI requests go through `core/llm/providers/openai_responses.py`
- engine/v1 OpenAI requests go through the same provider client
- chat SSE behavior is unchanged
- engine run behavior is unchanged

### Phase 3: Extract Anthropic

Goal:

- centralize thinking/tool parsing and request shaping for Anthropic

Work:

- create `core/llm/providers/anthropic_messages.py`
- move message formatting, tool formatting, thinking parsing, and provider
  state parsing there
- keep file upload and container persistence behind `ProviderStateStore`

Source logic to consolidate:

- [chat/llm/anthropic/provider.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/anthropic/provider.py#L367)
- [engine/v1/models/anthropic/claude.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/anthropic/claude.py#L226)

Exit criteria:

- chat and engine/v1 both use the shared Anthropic client
- thinking signatures still round-trip correctly

### Phase 4: Extract Gemini

Goal:

- centralize Gemini request shaping, tool conversion, and thought signatures

Work:

- create `core/llm/providers/gemini_generate.py`
- move function declaration conversion there
- move thought-signature request and response logic there
- keep host adapters responsible only for converting host message types

Source logic to consolidate:

- [chat/llm/gemini.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/gemini.py#L182)
- [engine/v1/models/google/gemini.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/google/gemini.py#L266)

Exit criteria:

- chat and engine/v1 both use the shared Gemini client
- streamed reasoning/tool-call behavior remains correct

### Phase 5: Extract OpenAI-Compatible Provider

Goal:

- remove duplicated OpenAI-compatible logic from chat and engine

Work:

- create `core/llm/providers/openai_compat.py`
- absorb behavior now split across:
  - [chat/llm/custom.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/custom.py#L43)
  - [engine/v1/models/custom/custom.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/custom/custom.py#L8)
  - [engine/v1/models/openai/completions.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/models/openai/completions.py#L78)

Exit criteria:

- all provider transport logic now lives under `core/llm/providers/*`

### Phase 6: Move Or Rename Misplaced Core Services

Goal:

- clean up misleading package ownership after provider extraction

Work:

- remove chat-specific imports from
  [core/llm/execution_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/core/llm/execution_service.py#L14)
- if the service remains chat-specific, move it under chat
- keep engine execution orchestration in engine

Likely outcomes:

- `core/llm/execution_service.py` becomes a thin provider utility service only,
  or
- it is moved to `chat/application/llm_execution_service.py`

Exit criteria:

- no file in `core/llm` imports from `ii_agent.chat.*`
- no file in `core/llm` imports from `ii_agent.engine.*`

### Phase 7: Remove Legacy Provider Duplicates

Goal:

- delete the old provider stacks after all call sites are migrated

Work:

- remove old provider logic from:
  - `chat/llm/openai.py`
  - `chat/llm/gemini.py`
  - `chat/llm/anthropic/provider.py`
  - `chat/llm/custom.py`
  - `engine/v1/models/openai/responses.py`
  - `engine/v1/models/google/gemini.py`
  - `engine/v1/models/anthropic/claude.py`
  - `engine/v1/models/custom/custom.py`
- keep compatibility shims if needed for one release

Exit criteria:

- provider transport logic has exactly one implementation per provider

## Risks

### Provider State Is Not Purely Transport-Level

OpenAI response continuity, OpenAI containers, and Anthropic file uploads all
need persistence and storage access. If that logic is moved into core without a
state-store boundary, core will immediately depend on chat ORM models again.

### Chat And Engine Have Different Host Semantics

Chat wants:

- SSE-friendly events
- chat-owned message persistence
- chat-owned tool loop behavior

Engine wants:

- `ModelResponse`
- pause/resume requirements
- structured outputs
- sandbox and sub-agent behavior

Trying to unify those semantics directly in the shared layer will recreate the
current coupling in a different package.

### Current `core/llm` Name Can Hide Bad Moves

A file being in `core/llm` does not make it core. Import direction is the real
test.

## Non-Goals

- merge chat tool execution and agent tool execution into one loop
- move `engine/agents/execution_service.py` into `chat`
- replace `engine/v1` with chat runtime semantics
- redesign chat summaries and engine summaries in this refactor
- change end-user behavior while extracting provider logic

## Success Criteria

1. `core/llm` contains the only provider transport implementations.
2. `core/llm` does not import `ii_agent.chat.*`.
3. `core/llm` does not import `ii_agent.engine.*`.
4. chat keeps its own runtime semantics and external API behavior.
5. engine/v1 keeps its own runtime semantics and external API behavior.
6. OpenAI, Anthropic, Gemini, and OpenAI-compatible providers are each
   implemented once.
