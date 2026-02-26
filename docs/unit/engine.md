# Unit Test Plan: `engine`

## Scope

- agent creation/orchestration (`engine/agents/*`)
- execution lifecycle and milestone updates
- sandbox lifecycle wrappers (`engine/sandboxes/*`)
- v1 factory/model/tool resolution (`engine/v1/*`)

## Priority test suites

1. Agent creation.
- `create_agent_v1()` wires tool args, session info, and dependencies
- optional skill tool and connector tool injection paths
- plan/suggestions agents apply expected system prompts

2. Factory resolution logic.
- API type -> provider mapping (`PROVIDER_SPEC_MAP`)
- correct model resolver and tool resolver invocation
- task-agent creation path uses task tool profile

3. Execution service lock flow.
- existing running task returns `None`
- new task path saves user event + task + processing event
- failure handling does not emit duplicate task creation

4. Milestone prompt/context logic.
- single milestone prompt construction
- multi milestone prompt construction
- unknown milestone IDs return `None`

5. Milestone status mutation.
- completed/failed/aborted status transitions
- events persisted for updated milestones only

6. Sandbox service resilience.
- init retries up to `MAX_ATTEMPT`
- fallback status for missing/failed sandbox
- forked-session shared sandbox fallback resolution

## Fixtures / mocks

- fake `AgentRunService`, `EventService`, `SessionService`, sandbox repos
- monkeypatched lock factory and DB session context manager
- fake tool manager/model resolver for v1 factory tests

## Proposed test layout

- `src/tests/unit/engine/test_agent_service.py`
- `src/tests/unit/engine/test_factory.py`
- `src/tests/unit/engine/test_execution_service.py`
- `src/tests/unit/engine/test_sandbox_service.py`
- `src/tests/unit/engine/test_plan_milestones.py`

## Exit criteria

- run orchestration and milestone state changes are deterministic
- sandbox retry and fallback behaviors are validated
