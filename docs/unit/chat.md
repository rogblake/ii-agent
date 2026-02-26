# Unit Test Plan: `chat`

## Scope

- chat orchestration (`chat/service.py`)
- iterative model/tool loop (`chat/llm_loop_service.py`)
- message, context, and tool execution boundaries
- media-context and model-resolution fallback behavior

## Priority test suites

1. Session-level chat logic.
- session name truncation and untitled rename behavior
- private/public session access checks
- model lookup and fallback to system model config

2. Credit and model guards.
- missing credit service defaults to allow
- insufficient credits path is denied by caller contract

3. Streaming loop happy path.
- emits incremental events + usage + complete payload
- writes assistant message with usage/file metadata

4. Tool-use loop path.
- tool calls execute in order and emit tool_result events
- tool-result message is persisted and loop continues
- storybook polling shortcut branch emits progress and completes

5. Cancellation and summarization.
- cancellation checked before and after provider stream
- summarization hooks called after completion

6. Tool registry and request composition.
- default tools merged with request overrides
- media mode adds tool hints and context flags

## Fixtures / mocks

- fake provider async stream generator
- fake message/tool services with call assertions
- synthetic chat request objects for media/non-media variants

## Proposed test layout

- `src/tests/unit/chat/test_chat_service.py`
- `src/tests/unit/chat/test_llm_loop_service.py`
- `src/tests/unit/chat/test_tool_selection.py`
- `src/tests/unit/chat/test_context_manager_hooks.py`

## Exit criteria

- streaming contracts are stable
- tool loop behavior is deterministic across edge paths
