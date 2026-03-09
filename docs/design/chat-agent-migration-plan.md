# Chat and Agent Migration Plan

Related docs:

- [Chat and Agent Application Design](./chat-agent-application-design.md)
- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)
- [Platform Database Redesign](./platform-database-redesign.md)
- [Platform Target Schema](./platform-target-schema.md)

## Goal

Migrate the current codebase from:

- one overloaded `sessions` shell
- chat reusing agent run tables
- agent behavior spread across `sessions`, `engine`, and `realtime`

to:

- a thin shared `sessions` shell
- chat-owned `chat_*` runtime tables
- agent-owned `agent_*` runtime tables
- clear ownership boundaries in services, repositories, and routes

This plan is incremental. It is designed to preserve behavior while changing
ownership in small, reversible steps.

## Current Code Inventory

### Shared Session Layer Today

- `sessions` in [sessions/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/models.py#L41)
- `session_wishlists` in [sessions/wishlist/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/wishlist/models.py#L14)

What `sessions` currently stores:

- ownership and naming
- public sharing fields
- sandbox linkage
- agent workspace state
- chat summary pointer
- token and cost counters
- chat-vs-agent discrimination through `agent_type`

### Chat-Owned Tables Today

- `chat_messages` in [chat/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/models.py#L23)
- `conversation_summaries` in [chat/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/models.py#L204)
- `provider_containers` in [chat/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/models.py#L89)
- `provider_files` in [chat/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/models.py#L126)
- `provider_vector_stores` in [chat/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/models.py#L165)

### Agent-Owned Tables Today

- `agent_run_tasks` in [engine/agents/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/agents/models.py#L36)
- `agent_run_messages` in [engine/v1/db/message.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/db/message.py#L9)
- `agent_run_events` in [engine/v1/db/agent.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/db/agent.py#L9)
- `session_summaries` in [engine/v1/db/summary.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/db/summary.py#L14)
- `sandboxes` in [engine/sandboxes/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/sandboxes/models.py)
- `events` in [realtime/events/models.py](/Users/pip/work/ii-agent-prod/src/ii_agent/realtime/events/models.py#L91)

## Current Code Coupling To Unwind

### `sessions` Owns Too Much

The main service and repository are overloaded:

- [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L28)
- [sessions/repository.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/repository.py#L14)

They currently own all of these concerns:

- shell CRUD
- public access
- chat-vs-agent filtering
- sandbox lookup
- run status lookup
- event hydration
- plan mutation

### Chat Reuses Agent Run State

`ChatService` currently creates and updates `AgentRunTask` rows:

- create run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L266)
- complete/fail run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L354)
- cancel run in [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L403)

This is the highest-value boundary to cut first.

### Agent-Specific Behavior Lives In `sessions`

- session preparation in [sessions/validation_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/validation_service.py#L46)
- forking in [sessions/fork_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/fork_service.py#L35)
- plan mutation in [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L287)
- event queries in [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L236)
- running status in [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L223)

### Runtime And Integration Callers Depend On The Old Contract

- Socket.IO join path in [realtime/socket/socketio.py](/Users/pip/work/ii-agent-prod/src/ii_agent/realtime/socket/socketio.py#L217)
- sandbox fallback in [engine/sandboxes/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/sandboxes/service.py#L186)
- MCP SSE agent bootstrap in [integrations/mcp_sse/agent.py](/Users/pip/work/ii-agent-prod/src/ii_agent/integrations/mcp_sse/agent.py#L320)
- public access checks in files/content/chat routes using `get_public_by_id`

## Target Ownership

### Shared `sessions`

Shared shell only:

- `id`
- `user_id`
- `app_kind`
- `name`
- `status`
- `llm_profile_id`
- `parent_session_id`
- `session_metadata`
- `last_message_at`
- `deleted_at`
- `created_at`
- `updated_at`

Keep `session_wishlists` for the first cutover. It can be renamed to
`session_bookmarks` later, but it does not block the split.

### Shared Session Services

- `SessionShellService`
- `SessionCatalogService`
- `SessionShareService`
- `SessionAccessService`

### Shared Session Repositories

- `SessionRepository`
- `SessionQueryRepository`
- `SessionShareRepository`

### Chat-Owned Runtime

- `chat_runs`
- `chat_messages`
- `chat_summaries`
- `chat_provider_containers`
- `chat_provider_files`
- `chat_provider_vector_stores`

### Agent-Owned Runtime

- `agent_runs`
- `agent_run_snapshots`
- `agent_event_log`
- `agent_plans`
- `agent_milestones`
- `agent_requirements`
- `agent_summaries`
- `agent_sandboxes`
- `agent_ui_events`

## Current To Target Mapping

| Current artifact | Target artifact | Phase | Notes |
| --- | --- | --- | --- |
| `sessions.agent_type` as app discriminator | `sessions.app_kind` | 1, 2 | Keep `agent_type` temporarily only for agent subtype semantics |
| `sessions.llm_setting_id` | `sessions.llm_profile_id` | 1, 2 | Use mapping/default profile rules during backfill |
| `sessions.is_public`, `sessions.public_url` | `session_shares` | 1, 3, 7 | Move reads first, then writes, then drop columns |
| `sessions.sandbox_id` | `agent_sandboxes` or agent-owned state | 5, 7 | Keep read compatibility until all agent callers move |
| `sessions.agent_state_path`, `sessions.state_storage_url` | agent-owned runtime state | 5, 7 | Do not move until agent runtime services exist |
| `sessions.summary_message_id` | `chat_summaries` linkage | 4, 7 | Remove from shell once chat summary reads no longer require it |
| `sessions.prompt_tokens`, `sessions.completion_tokens`, `sessions.cost` | `usage_records` or app-owned run usage | 7 | Do not backfill into shell replacements first |
| `conversation_summaries` | `chat_summaries` | 4 | Rename after chat run cutover is stable |
| `provider_containers` | `chat_provider_containers` | 4 | Naming cleanup can happen after behavior cutover |
| `provider_files` | `chat_provider_files` | 4 | Also enforce local file FK ownership |
| `provider_vector_stores` | `chat_provider_vector_stores` | 4 | Keep user/provider uniqueness semantics |
| `agent_run_tasks` reused by chat | `chat_runs` for chat, `agent_runs` for agent | 4, 5 | Chat cutover first, agent rename second |
| `agent_run_messages` | `agent_run_snapshots` | 5 | Clarify purpose before deeper runtime cleanup |
| `agent_run_events` | `agent_event_log` | 5 | Keep append-only semantics |
| `session_summaries` | `agent_summaries` | 5 | Clarify owner |
| `events` | `agent_ui_events` | 5, 6 | Treat as agent projection table, not shared event store |
| `SessionRepository.get_public_by_id()` | `SessionShareRepository` + `SessionShareService` | 3 | Shared access concern, not shell persistence |
| `SessionRepository.get_sandbox_id()` | agent-owned repository/service | 5 | Remove from `sessions` repo |
| `SessionService.update_session_plan()` | `AgentPlanService` | 5 | Move with milestone and plan logic |
| `SessionValidationService` | `agent.application.session_validation_service` | 5 | Split by app instead of mutating shell |
| `SessionForkService` | `agent.application.fork_service` | 5 | It is agent/fork workflow, not shell ownership |
| `ChatService -> AgentRunService` | `ChatRunService` | 4 | Highest-value decoupling |

## Temporary Compatibility Layer

During the migration, the old `sessions` API must remain callable while the new
services are introduced.

### Compatibility Rules

1. `SessionService` stays in place as a facade until Phase 6.
2. Existing route signatures stay stable until the owning domain is ready.
3. Old columns remain readable until all call sites switch to new tables.
4. New code must use the new services directly; only old code may depend on the facade.

### Facade Delegate Map

| Existing method on `SessionService` | Temporary delegate | Final owner |
| --- | --- | --- |
| `create_session()` | `SessionShellService.create_session()` | `sessions` |
| `get_session_by_id()` | `SessionShellService.get_session()` | `sessions` |
| `get_session_details()` | `SessionCatalogService.get_owned_session()` | `sessions` |
| `get_public_session_details()` | `SessionShareService.get_public_session()` | `sessions` |
| `update_session_name()` | `SessionShellService.rename()` | `sessions` |
| `update_session_llm_setting_id()` | `SessionShellService.set_llm_profile()` | `sessions` |
| `soft_delete_session()` | `SessionShellService.soft_delete()` | `sessions` |
| `bulk_soft_delete_sessions()` | `SessionShellService.bulk_soft_delete()` | `sessions` |
| `get_user_sessions()` | `SessionCatalogService.list_sessions()` | `sessions` |
| `set_session_public()` | `SessionShareService.set_public()` | `sessions` |
| `get_sessions_with_running_status()` | `AgentRunQueryService.list_running_sessions()` | `agent` |
| `get_session_running_status()` | `AgentRunQueryService.get_running_status()` | `agent` |
| `get_session_events_with_details()` | `AgentEventQueryService.get_session_events()` | `agent` |
| `update_session_plan()` | `AgentPlanService.update_plan()` | `agent` |
| `update_sandbox_id()` | compatibility shim only | `agent` |
| `update_session_agent_type()` | compatibility shim only | `agent` |
| `ensure_session_exists()` | app bootstrap service | `chat` or `agent` |
| `get_or_create_session()` | app bootstrap service | `chat` or `agent` |

## Migration Principles

1. Add before removing.
2. Backfill before read cutover.
3. Dual-write before deleting old paths.
4. Keep `SessionService` as a temporary facade while new services are introduced.
5. Cut chat over before deeply refactoring the agent runtime.
6. Do not mix schema renames and behavior changes in the same release.
7. Prefer wrappers and delegates over large rename-only commits.
8. Do not remove old read paths until verification queries are green.

## Phase Plan

### Phase 0: Characterization And Safety Checks

Goal:

- freeze current behavior before moving ownership

Work:

- add tests for session listing, public access, chat cancel, agent join, session fork, and sandbox resolution
- identify dead code such as `get_by_workspace()` in [sessions/repository.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/repository.py#L52), which references a non-existent session column

Files to touch:

- `src/ii_agent/sessions/*`
- `src/ii_agent/chat/service.py`
- `src/ii_agent/realtime/socket/socketio.py`
- `src/ii_agent/sessions/fork_service.py`
- `src/ii_agent/engine/sandboxes/service.py`

Verification:

- session list still returns the same rows for `chat` and `agent`
- public session fetch still respects sharing rules
- chat cancel still marks the last run as aborted
- agent join still creates or attaches to the same session ID

Exit criteria:

- current behavior is covered by regression tests

### Phase 1: Additive Schema Expansion

Goal:

- add the new schema without breaking current reads/writes

DB work:

- add `sessions.app_kind`
- add `sessions.llm_profile_id`
- create `session_shares`
- create `chat_runs`
- add nullable `chat_messages.run_id`
- create `agent_plans`
- create `agent_milestones`
- create `agent_requirements`

Backfill rules:

- `sessions.app_kind = 'chat'` where `agent_type = 'chat'`
- `sessions.app_kind = 'agent'` otherwise
- `session_shares` from `sessions.is_public` and `sessions.public_url`
- `sessions.llm_profile_id` from `llm_setting_id` via mapping or default profile rules

Migration implementation notes:

- make all new columns nullable first
- create indexes before large read cutovers
- use batched backfills for `chat_runs` and `chat_messages.run_id`
- keep old columns authoritative until Phase 3 and Phase 4 cutovers are complete

Schema files expected:

- Alembic revision for `sessions.app_kind`, `sessions.llm_profile_id`, `session_shares`
- Alembic revision for `chat_runs` and `chat_messages.run_id`
- Alembic revision for `agent_plans`, `agent_milestones`, `agent_requirements`

Exit criteria:

- new tables and columns exist
- backfills run successfully
- old code paths still work

### Phase 2: Introduce The New Session Boundary In Code

Goal:

- stop adding new behavior to the overloaded session service

Code work:

- add `SessionShellService`
- add `SessionCatalogService`
- add `SessionShareService`
- add `SessionAccessService`
- add `SessionQueryRepository`
- add `SessionShareRepository`
- keep [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L28) as a facade that delegates to the new services

API changes:

- switch session list filtering from `agent_type` to `app_kind`
- add share lookups through `session_shares`

Files to add:

- `src/ii_agent/sessions/shell_service.py`
- `src/ii_agent/sessions/catalog_service.py`
- `src/ii_agent/sessions/share_service.py`
- `src/ii_agent/sessions/share_repository.py`
- `src/ii_agent/sessions/query_repository.py`

Files to edit:

- [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L28)
- [sessions/repository.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/repository.py#L14)
- [sessions/dependencies.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/dependencies.py)
- [sessions/schemas.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/schemas.py#L26)

Compatibility contract:

- old methods remain present
- new methods emit the new DTO shape internally
- list filtering uses `app_kind`, but old callers can still pass `session_type`

Exit criteria:

- new session services exist
- old `SessionService` still works through delegation
- no new code is written against the old mixed contract

### Phase 3: Cut Public Sharing Over To `session_shares`

Goal:

- remove sharing from the `sessions` table without changing user-visible behavior

Code work:

- replace `get_public_by_id()` and `set_session_public()` usage with `SessionShareService`
- update these callers:
  - [sessions/router.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/router.py)
  - [files/router.py](/Users/pip/work/ii-agent-prod/src/ii_agent/files/router.py)
  - [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L126)
  - [content/slides/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/content/slides/service.py)
  - [content/storybook/router.py](/Users/pip/work/ii-agent-prod/src/ii_agent/content/storybook/router.py)

Compatibility contract:

- `SessionRepository.get_public_by_id()` may remain temporarily, but it must delegate to the share repository
- `SessionService.get_public_session_details()` may remain temporarily, but it must delegate to the share service

Verification:

- public route checks no longer read `sessions.is_public`
- publish/unpublish only writes `session_shares`
- content and file public routes return unchanged payloads

Exit criteria:

- public access no longer reads `sessions.is_public` or `sessions.public_url`
- publish/unpublish only touches `session_shares`

### Phase 4: Cut Chat Over To `chat_runs`

Goal:

- stop letting chat write agent run tables

Code work:

- add `ChatRunRepository`
- add `ChatRunService`
- change [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L78) to create shell sessions with `app_kind='chat'`
- change [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L266) to create `chat_runs`
- change [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L354) to update `chat_runs`
- change [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py#L403) to cancel `chat_runs`
- add `chat_messages.run_id` writes for new turns

Files to add:

- `src/ii_agent/chat/run_repository.py`
- `src/ii_agent/chat/run_service.py`

Files to edit:

- [chat/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/chat/service.py)
- `src/ii_agent/chat/dependencies.py`
- `src/ii_agent/chat/schemas.py`
- any chat cancellation endpoints or handlers

Compatibility:

- if historical chat rows still map to `agent_run_tasks`, keep read compatibility during the transition
- chat history reads must not assume every old message has `run_id`
- only new chat turns write `chat_runs`

Verification:

- new chat turns create `chat_runs` only
- chat stop/cancel no longer calls `AgentRunService`
- no new rows are inserted into `agent_run_tasks` for chat sessions

Exit criteria:

- new chat turns only use `chat_runs`
- chat no longer depends on `AgentRunService`

### Phase 5: Move Agent-Specific Logic Out Of `sessions`

Goal:

- make `sessions` a shell and move runtime logic under `agent`

Code work:

- move session preparation from [sessions/validation_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/validation_service.py#L46) into `agent.application.session_validation_service`
- move forking from [sessions/fork_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/fork_service.py#L35) into `agent.application.fork_service`
- move plan updates from [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L287) into `agent.application.plan_service`
- move event queries from [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L236) into `agent.application.event_query_service`
- move run status lookups from [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py#L223) into `agent.application.run_query_service`
- move sandbox linkage away from `sessions.sandbox_id`

Caller updates:

- [realtime/socket/socketio.py](/Users/pip/work/ii-agent-prod/src/ii_agent/realtime/socket/socketio.py#L217)
- [integrations/mcp_sse/agent.py](/Users/pip/work/ii-agent-prod/src/ii_agent/integrations/mcp_sse/agent.py#L320)
- [engine/sandboxes/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/sandboxes/service.py#L186)
- [engine/v1/agents/sandbox_provider.py](/Users/pip/work/ii-agent-prod/src/ii_agent/engine/v1/agents/sandbox_provider.py)

Files to add under the target layout:

- `src/ii_agent/agent/application/session_validation_service.py`
- `src/ii_agent/agent/application/fork_service.py`
- `src/ii_agent/agent/application/plan_service.py`
- `src/ii_agent/agent/application/event_query_service.py`
- `src/ii_agent/agent/application/run_query_service.py`

Likely compatibility shims:

- keep [sessions/validation_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/validation_service.py) as a thin wrapper temporarily
- keep [sessions/fork_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/fork_service.py) as a thin wrapper temporarily
- keep `SessionService.update_session_plan()` temporarily delegating to `AgentPlanService`

Verification:

- agent join/resume still works
- forking still produces the same child session relationships
- sandbox resolution no longer requires `sessions.sandbox_id`
- plan update and event queries no longer depend on `SessionService`

Exit criteria:

- agent runtime no longer mutates session shell fields like `sandbox_id` or `agent_state_path`
- agent-specific logic lives under `agent`

### Phase 6: Router And API Ownership Cleanup

Goal:

- make API ownership match domain ownership

Code work:

- keep `sessions/router.py` for shell concerns only:
  - get session shell
  - list sessions
  - delete sessions
  - maybe public/share endpoints if you want them session-scoped
- move agent-specific routes out:
  - session events
  - run status
  - plan update
  - fork

Target ownership:

- session shell endpoints stay in `sessions`
- share endpoints may remain session-scoped but use `SessionShareService`
- agent runtime endpoints move under `agent`
- chat runtime endpoints stay under `chat`

Routes to move or rewrite:

- `GET /sessions/{id}/events`
- `GET /sessions/{id}/public/events`
- `POST /sessions/{id}/fork`
- `POST /sessions/{id}/plan`

Files to edit:

- [sessions/router.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/router.py)
- agent router module once introduced
- any frontend/API client that assumes agent event endpoints live under `/sessions`

Verification:

- session shell endpoints return shell DTOs only
- agent runtime endpoints are served by the `agent` application
- chat API shape is unchanged for chat clients

Exit criteria:

- `sessions` API surface only exposes shell concerns

### Phase 7: Contract Cleanup And Column Removal

Goal:

- remove the old mixed contract once all callers are cut over

Drop from `sessions`:

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
- chat use of `AgentRunService`

Files likely removed or heavily reduced:

- [sessions/service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/service.py)
- [sessions/validation_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/validation_service.py)
- [sessions/fork_service.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/fork_service.py)
- public helpers in [sessions/repository.py](/Users/pip/work/ii-agent-prod/src/ii_agent/sessions/repository.py)

Final verification:

- no new reads of dropped session columns
- no new chat writes to `agent_run_tasks`
- all session list filters use `app_kind`
- all public access checks use `session_shares`

Exit criteria:

- `sessions` is a thin shell only
- chat and agent own their own runtime state

## Phase Ordering Rationale

This order matters:

1. sharing first because it is isolated and low risk
2. chat next because it has the clearest incorrect dependency on agent tables
3. agent runtime after that because it has the highest number of callers
4. final cleanup only after all reads and writes are cut over

Do not start by renaming every file or moving every folder. That creates churn
without changing ownership.

## First Concrete Implementation Slice

If implementation starts now, the best first slice is:

1. add `sessions.app_kind`
2. add `session_shares`
3. add `chat_runs`
4. introduce the split session services behind the existing facade
5. cut chat off `AgentRunService`

That removes the worst boundary with the smallest blast radius.

## Release Packaging Suggestion

Use separate deployable releases instead of one long-running branch.

### Release A

- Phase 0
- Phase 1

### Release B

- Phase 2
- Phase 3

### Release C

- Phase 4

### Release D

- Phase 5
- Phase 6

### Release E

- Phase 7

This keeps the highest-risk runtime cutovers isolated:

- sharing cutover
- chat run cutover
- agent runtime cutover

## Rollback Posture

### Safe To Roll Back

- additive schema changes
- new repositories/services that are not yet the default path
- share read cutover before old columns are removed

### Roll Back Carefully

- chat run cutover after new `chat_runs` writes begin
- agent runtime cutover after sandbox and plan logic move

### Do Not Roll Back Blindly

- after old session columns are dropped
- after old routes are removed from clients

For Phase 4 and Phase 5, keep old read compatibility for at least one release
after the write cutover.

## Out Of Scope For The First Migration

These can wait until the session/chat/agent split is stable:

- `projects` JSON normalization
- content table redesign
- deeper billing redesign beyond what the new session split needs
- `session_wishlists` rename to `session_bookmarks`
