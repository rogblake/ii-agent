# Chat and Agent Migration Plan

Related docs:

- [Chat and Agent Application Design](./chat-agent-application-design.md)
- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)
- [Platform Database Redesign](./platform-database-redesign.md)
- [Platform Target Schema](./platform-target-schema.md)

## Goal

Migrate the current codebase from:

- `engine` plus `realtime` acting as the agent app
- a flat `chat` package that reuses agent run state
- an overloaded `sessions` layer

to:

- a real `agent/` package
- a clearer internal `chat/` structure
- chat-owned run lifecycle storage
- explicit chat-owned table names
- a thinner session shell
- explicit agent-owned runtime tables

This plan is incremental. It keeps the full multi-phase migration, but it
changes the order so the first wave matches the revised application design.

## Scope By Wave

### First Wave

1. move agent-owned code from `engine/` and `realtime/` into `agent/`
2. keep `engine/v1` as the actual agent runtime and rename it to `agent/runtime`
3. move agent-only validation logic out of `sessions`
4. reshape `chat/` internally
5. add `chat_runs`
6. rename chat-owned tables to:
   - `chat_summaries`
   - `chat_provider_containers`
   - `chat_provider_files`
   - `chat_provider_vector_stores`

### Later Waves Still In This Plan

These are still part of the overall migration guide, but they happen after the
first wave:

- `sessions.app_kind`
- `session_shares`
- `session_bookmarks`
- `agent_run_tasks` -> `agent_runs`
- `agent_run_messages` -> `agent_run_snapshots`
- `agent_run_events` -> `agent_event_log`
- `session_summaries` -> `agent_summaries`
- `sandboxes` -> `agent_sandboxes`
- `events` -> `agent_ui_events`
- `agent_plans`, `agent_milestones`, `agent_requirements`
- final session-column cleanup

## Current Coupling To Break First

### Chat Still Uses Agent Run State

`ChatService` currently creates, updates, and cancels `AgentRunTask` rows:

- create run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L266)
- complete/fail run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L354)
- cancel run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L403)

This is the highest-value ownership cut.

### Agent Code Is Split Across Two False Top-Level Boundaries

Today the agent app is spread across:

- `src/ii_agent/engine/*`
- `src/ii_agent/engine/v1/*`
- `src/ii_agent/realtime/*`

That makes ownership unclear and makes the repo structure lie about the actual
application boundary.

### `sessions` Still Carries Agent-Only Behavior

The clearest example is:

- [sessions/validation_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/validation_service.py#L1)

That is an agent pre-run concern and should move under `agent/application/`.

## Migration Principles

1. Move packages before redesigning the session shell.
2. Cut chat off agent run storage before renaming agent tables.
3. Add new tables before cutting reads and writes over.
4. Do not synthesize fake historical `chat_runs`.
5. Keep `engine/*`, `realtime/*`, and flat `chat/*.py` import shims during the transition.
6. Keep `chat/llm` and `agent/runtime` local to their applications for now.
7. Do not mix the chat run split with the later `sessions.app_kind` and `session_shares` rollout.

## Phase Plan

### Phase 0: Characterization And Safety Checks

Goal:

- freeze current behavior before moving code and schema ownership

Work:

- add or confirm regression coverage for chat streaming, chat cancel, agent socket join, session fork, and sandbox lookup
- confirm current chat behavior around incomplete messages and cancellation
- identify dead or misleading code such as `SessionRepository.get_by_workspace()`

Files to exercise:

- [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py)
- [chat/router.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/router.py)
- [realtime/socket/socketio.py](/Users/pip/work/ii-agent-prod/src/ii_agent/realtime/socket/socketio.py)
- [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py)
- [engine/sandboxes/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/sandboxes/service.py)

Exit criteria:

- current chat cancel behavior is covered
- current agent socket join behavior is covered
- current sandbox resolution behavior is covered

### Phase 1: Create The Real `agent/` Package Boundary

Goal:

- make the package structure match the actual application boundary

Code work:

- add `src/ii_agent/agent/`
- add `src/ii_agent/agent/dependencies.py`
- add target subpackages:
  - `agent/runs/`
  - `agent/application/`
  - `agent/runtime/`
  - `agent/sandboxes/`
  - `agent/socket/`
  - `agent/events/`
  - `agent/prompts/`
  - `agent/api/`

Initial file moves:

- `engine/agents/models.py` -> `agent/runs/models.py`
- `engine/agents/repository.py` -> `agent/runs/repository.py`
- `engine/agents/agent_run_service.py` -> `agent/runs/service.py`
- `engine/agents/agent_service.py` -> `agent/application/agent_service.py`
- `engine/agents/execution_service.py` -> `agent/application/execution_service.py`
- `engine/agents/plan_service.py` -> `agent/application/plan_service.py`
- `engine/sandboxes/*` -> `agent/sandboxes/*`
- `engine/prompts/*` -> `agent/prompts/*`
- `engine/v1/*` -> `agent/runtime/*`
- `engine/v1/api/*` -> `agent/api/*`
- `realtime/socket/*` -> `agent/socket/*`
- `realtime/events/*` -> `agent/events/*`
- `realtime/subscribers/*` -> `agent/events/subscribers/*`

Compatibility rule:

- keep `src/ii_agent/engine/*` and `src/ii_agent/realtime/*` as forwarding shims for one release

Files to rewire immediately:

- [core/container.py](/Users/pip/work/ii-agent-prod/src/ii_agent/core/container.py)
- [app.py](/Users/pip/work/ii-agent-prod/src/ii_agent/app.py)
- integrations that import `engine` or `realtime`

Exit criteria:

- `core/container.py` imports `ii_agent.agent.*`
- new code imports `ii_agent.agent.*`
- `engine/v1` is treated as the live runtime, not a deprecated adapter

### Phase 2: Move Agent-Only Validation Out Of `sessions`

Goal:

- stop keeping agent pre-run logic in the session shell package

Code work:

- move `sessions/validation_service.py` to `agent/application/session_validation_service.py`
- update container wiring and socket handlers
- keep `sessions/fork_service.py` in `sessions/` for now

Why `fork_service` stays for now:

- it still creates session-shell rows
- it still depends on current `sessions` fields such as `agent_type`, `sandbox_id`, and `llm_setting_id`

Exit criteria:

- `sessions/validation_service.py` no longer exists
- no agent pre-run path imports validation from `sessions`

### Phase 3: Reshape `chat/` Internally Without Changing Behavior

Goal:

- prepare chat for the run split and table renames

Code work:

- add `chat/api/`
- add `chat/application/`
- add `chat/messages/`
- add `chat/runs/`
- add `chat/summaries/`
- add `chat/providers/`
- move existing flat modules into those packages

Initial file moves:

- `chat/router.py` -> `chat/api/router.py`
- `chat/dependencies.py` -> `chat/api/dependencies.py`
- `chat/service.py` -> `chat/application/chat_service.py`
- `chat/message_service.py` -> `chat/messages/service.py`
- `chat/message_history_service.py` -> `chat/messages/history_service.py`
- `chat/repository.py` -> `chat/messages/repository.py`
- `chat/context_manager.py` -> `chat/application/context_service.py`
- `chat/file_processing_service.py` -> `chat/application/file_processing_service.py`
- `chat/file_processor.py` -> `chat/application/file_processor.py`
- `chat/tool_service.py` -> `chat/application/tool_service.py`
- `chat/llm_loop_service.py` -> `chat/application/turn_loop_service.py`

Model split to prepare:

- message model into `chat/messages/models.py`
- run model into `chat/runs/models.py`
- summary model into `chat/summaries/models.py`
- provider mapping models into `chat/providers/models.py`

Compatibility rule:

- keep old flat `chat/*.py` modules as forwarding imports until internal imports are rewritten

Exit criteria:

- chat code is importable through the new package structure
- no behavior change yet

### Phase 4: Add `chat_runs` And Cut Chat Off Agent Run State

Goal:

- make chat own its own run lifecycle

Schema work:

- create `chat_runs`
- add nullable `chat_messages.chat_run_id`
- add safe FKs:
  - `chat_runs.session_id -> sessions.id`
  - `chat_runs.user_message_id -> chat_messages.id`
  - `chat_runs.assistant_message_id -> chat_messages.id`
  - `chat_messages.chat_run_id -> chat_runs.id`

Important backfill rule:

- do not create synthetic `chat_runs` for historical chat history
- leave historical `chat_messages.chat_run_id` as `NULL`
- only new turns write `chat_runs`

Code work:

- add `ChatRun` model
- add `ChatRunRepository`
- add `ChatRunService`
- update chat DI to inject `ChatRunService`
- replace `ChatService -> AgentRunService` with `ChatService -> ChatRunService`
- stop importing `AgentRunTask` and `RunStatus` in chat code
- keep using the existing cancellation registry, but register chat run IDs instead of agent task IDs

Concrete call-site changes:

- create chat run before streaming starts
- update chat run to `completed`, `failed`, or `cancelled`
- attach `assistant_message_id` when the assistant message is persisted
- use `ChatRunService.find_running_run_for_cancel()` in stop/cancel flows

Exit criteria:

- no module under `src/ii_agent/chat` imports `AgentRunService`
- no module under `src/ii_agent/chat` imports `engine.agents.models.RunStatus`
- chat cancellation targets `chat_runs`

### Phase 5: Rename Chat-Owned Tables And ORM Classes

Goal:

- make chat-owned storage read as chat-owned storage

Schema work:

- rename `conversation_summaries` -> `chat_summaries`
- rename `provider_containers` -> `chat_provider_containers`
- rename `provider_files` -> `chat_provider_files`
- rename `provider_vector_stores` -> `chat_provider_vector_stores`

Schema tightening in the same phase:

- add `chat_summaries.session_id -> sessions.id`
- add `chat_summaries.end_message_id -> chat_messages.id`
- add `chat_provider_containers.session_id -> sessions.id`
- add `chat_provider_files.session_id -> sessions.id`
- add `chat_provider_files.file_upload_id -> file_uploads.id`
- keep `chat_provider_vector_stores` user-scoped

ORM rename work:

- `ConversationSummary` -> `ChatSummary`
- `ProviderContainer` -> `ChatProviderContainer`
- `ProviderFile` -> `ChatProviderFile`
- `ProviderVectorStore` -> `ChatProviderVectorStore`

Expected code updates:

- [chat/context_manager.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/context_manager.py)
- [chat/llm/openai.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/openai.py)
- [chat/llm/anthropic/provider.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/llm/anthropic/provider.py)
- [chat/vectorstore/openai.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/vectorstore/openai.py)
- tests that import old ORM class names

Important note:

- `chat_provider_vector_stores` remains user-scoped because the current OpenAI vector-store implementation reuses one provider vector store per user, not one per session

Exit criteria:

- no SQLAlchemy model in chat points at `conversation_summaries`
- no SQLAlchemy model in chat points at `provider_containers`
- no SQLAlchemy model in chat points at `provider_files`
- no SQLAlchemy model in chat points at `provider_vector_stores`

### Phase 6: Remove Package And Module Compatibility Shims

Goal:

- finish the first-wave package move cleanly after behavior and schema cutovers are stable

Remove:

- `src/ii_agent/engine/*` forwarding shims
- `src/ii_agent/realtime/*` forwarding shims
- flat `chat/*.py` forwarding shims that only re-export moved modules

Verification searches:

- `rg -n "ii_agent\\.engine\\." src/ii_agent`
- `rg -n "ii_agent\\.realtime\\." src/ii_agent`
- `rg -n "AgentRunService" src/ii_agent/chat`
- `rg -n "conversation_summaries|provider_containers|provider_files|provider_vector_stores" src/ii_agent`

Exit criteria:

- imports resolve through `ii_agent.agent.*`, `ii_agent.chat.*`, `ii_agent.sessions.*`, and shared domains only
- chat has no dependency on agent run storage

### Phase 7: Introduce The Thinner Session Shell

Goal:

- finish the session-shell redesign after chat is already decoupled from agent run state

DB work:

- add `sessions.app_kind`
- create `session_shares`
- keep `agent_type` temporarily only for agent subtype semantics if still needed

Code work:

- add `SessionShellService`
- add `SessionCatalogService`
- add `SessionShareService`
- add `SessionAccessService`
- add `SessionQueryRepository`
- add `SessionShareRepository`
- keep `SessionService` as a temporary facade while call sites move

Behavior cutovers:

- switch session list filtering from `agent_type` to `app_kind`
- route public/private access through `session_shares`
- stop adding new app-specific behavior to `sessions/service.py`

Exit criteria:

- session list and lookup paths use `app_kind`
- share reads no longer depend on `sessions.is_public` and `sessions.public_url`
- `SessionService` mainly delegates to thinner services

### Phase 8: Cut Public Sharing Fully Over To `session_shares`

Goal:

- remove sharing from the `sessions` table without changing user-visible behavior

Code work:

- replace `get_public_by_id()` and `set_session_public()` usage with `SessionShareService`
- update callers in sessions, files, chat, and content routes

Compatibility rule:

- `SessionRepository.get_public_by_id()` may remain temporarily, but it must delegate to the share repository
- `SessionService.get_public_session_details()` may remain temporarily, but it must delegate to the share service

Exit criteria:

- public route checks no longer read `sessions.is_public`
- publish/unpublish only writes `session_shares`

### Phase 9: Rename Agent-Owned Tables And Extract Planning State

Goal:

- make the agent runtime tables read as agent-owned tables
- move plan, milestone, and HITL state out of `sessions.session_metadata`

DB work:

- rename `agent_run_tasks` -> `agent_runs`
- rename `agent_run_messages` -> `agent_run_snapshots`
- rename `agent_run_events` -> `agent_event_log`
- rename `session_summaries` -> `agent_summaries`
- rename `sandboxes` -> `agent_sandboxes`
- rename or replace `events` -> `agent_ui_events`
- create `agent_plans`
- create `agent_milestones`
- create `agent_requirements`

Code work:

- update ORM models and repositories under `agent/runs`, `agent/events`, and `agent/sandboxes`
- update `agent/runtime` persistence imports
- update plan, milestone, and requirement flows to use the new agent-owned tables

Important rule:

- this phase is agent-only; chat should already be fully off agent run storage before this begins

Exit criteria:

- agent code imports only the renamed agent-owned tables
- current plan state no longer depends on `sessions.session_metadata`
- no chat path refers to any agent runtime table

### Phase 10: Final Session And Schema Cleanup

Goal:

- remove old compatibility columns and remaining overloaded session-shell behavior

Drop or move from `sessions`:

- `is_public`
- `public_url`
- `sandbox_id`
- `agent_state_path`
- `state_storage_url`
- `summary_message_id`
- `prompt_tokens`
- `completion_tokens`
- `cost`

Semantic cleanup:

- stop using `agent_type` as the chat-vs-agent discriminator
- keep it temporarily as agent subtype only, or rename it later

Old code to remove:

- public access helpers on `SessionRepository`
- sandbox helpers on `SessionRepository`
- agent/runtime methods on `SessionService`
- any remaining compatibility wrappers in `sessions`

Exit criteria:

- `sessions` behaves as a real shared shell
- app-specific runtime fields no longer live on the session row

## Phase Ordering Rationale

This order matters:

1. package boundary first, because `agent` and `chat` ownership should be honest before deeper schema work
2. chat run split second, because it is the clearest incorrect dependency
3. session shell redesign after chat is already decoupled from agent run state
4. agent table rename and planning-table work after the chat cut is stable
5. final cleanup only after all reads and writes are cut over

Do not start by renaming every table or moving every session concern at once.

## First Concrete Implementation Slice

If implementation starts now, the best first slice is:

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4

That gives you the highest-value ownership cut first:

- real `agent/` package
- real `chat/` internal structure
- `chat_runs`
- no new chat writes to `agent_run_tasks`

## Release Packaging Suggestion

Use separate deployable releases instead of one long-running branch.

### Release A

- Phase 0
- Phase 1
- Phase 2

### Release B

- Phase 3
- Phase 4

### Release C

- Phase 5
- Phase 6

### Release D

- Phase 7
- Phase 8

### Release E

- Phase 9

### Release F

- Phase 10

This keeps the highest-risk cutovers isolated:

- package move
- chat run cutover
- chat table rename
- session shell redesign
- agent runtime rename and plan-state extraction

## Rollback Posture

### Safe To Roll Back

- package moves while shims still exist
- additive `chat_runs` schema before write cutover
- new repositories/services that are not yet the default path
- share read cutover before old columns are removed

### Roll Back Carefully

- chat run cutover after new `chat_runs` writes begin
- chat table rename after ORM imports switch over
- agent table rename after runtime persistence switches

### Do Not Roll Back Blindly

- after old session columns are dropped
- after old import shims are removed
- after old routes are removed from clients

For the first-wave cutovers, keep old read compatibility for at least one
release after the write cutover.

## Final Verification Checklist

The migration is complete when all of the following are true:

- `engine/v1` code lives under `agent/runtime`
- Socket.IO and event persistence live under `agent/socket` and `agent/events`
- `sessions/validation_service.py` has moved under `agent/application`
- chat creates `chat_runs`, not `agent_run_tasks`
- chat-owned tables are renamed to `chat_*`
- no code under `chat/` imports agent run services or agent run models
- session ownership uses an explicit shell design with `app_kind` and `session_shares`
- agent tables are renamed to explicit agent-owned names
- plan, milestone, and requirement state are agent-owned rather than stored in session metadata
- app-specific runtime fields no longer live on `sessions`
