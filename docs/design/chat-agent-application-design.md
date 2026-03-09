# Chat and Agent Application Design

Related docs:

- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)
- [Chat and Agent Migration Plan](./chat-agent-migration-plan.md)
- [Platform Database Redesign](./platform-database-redesign.md)
- [Platform Target Schema](./platform-target-schema.md)

## Decision

`chat` and `agent` are separate applications.

They can share platform infrastructure:

- `sessions`
- `auth`
- `billing`
- `files`
- `settings`
- `core`

They should not share application services, runtime orchestration, or runtime
tables.

This revision intentionally narrows scope:

- split the code structure first
- add `chat_runs` so chat stops using agent run state
- rename the chat-owned tables now
- do not rename agent tables yet
- treat `engine/v1` as the real agent runtime and rename it into `agent/runtime`

## Repo Reality Check

The current repository already shows the real ownership boundaries:

- `src/ii_agent/chat` is already a chat application, but it is too flat
- `src/ii_agent/engine` is the actual agent application
- `src/ii_agent/engine/v1` is not legacy; it is the current agent runtime
- `src/ii_agent/realtime` is mostly agent socket transport and agent event persistence
- `src/ii_agent/sessions` is overloaded with both shared session-shell behavior and agent-only behavior

Two corrections follow from that:

1. do not invent a giant shared `core.llm.providers` package yet
2. do not bundle the chat split with the full session-shell and agent-table redesign

The first migration should be smaller and cleaner than the previous draft.

## Target Top-Level Structure

```text
src/ii_agent/
├── agent/
├── chat/
├── sessions/
├── projects/
├── content/
├── integrations/
├── auth/
├── billing/
├── files/
├── settings/
├── core/
├── workers/
├── mobile/
└── app.py
```

### Top-Level Rules

- `engine/` becomes `agent/`
- `realtime/` is retired as a top-level package
- `core/` stays infrastructure-only
- `chat` must not import `agent`
- `agent` must not import `chat`

## Concrete Package Placement

This is the concrete target layout based on the current code, not an abstract
greenfield design.

### Agent

```text
src/ii_agent/agent/
├── api/            # current engine/v1/api
├── application/    # execution, planning, validation orchestration
├── events/         # current realtime/events + realtime/subscribers
├── prompts/        # current engine/prompts
├── runs/           # current engine/agents run models/repo/service
├── runtime/        # current engine/v1
├── sandboxes/      # current engine/sandboxes
├── socket/         # current realtime/socket
└── dependencies.py
```

#### Current To Target Map For Agent

| Current path | Target path | Notes |
| --- | --- | --- |
| `src/ii_agent/engine/agents/models.py` | `src/ii_agent/agent/runs/models.py` | Run lifecycle models stay agent-owned |
| `src/ii_agent/engine/agents/repository.py` | `src/ii_agent/agent/runs/repository.py` | Run persistence stays with the run aggregate |
| `src/ii_agent/engine/agents/agent_run_service.py` | `src/ii_agent/agent/runs/service.py` | Chat should stop importing this service |
| `src/ii_agent/engine/agents/agent_service.py` | `src/ii_agent/agent/application/agent_service.py` | Orchestrates runtime creation |
| `src/ii_agent/engine/agents/execution_service.py` | `src/ii_agent/agent/application/execution_service.py` | Socket command orchestration |
| `src/ii_agent/engine/agents/plan_service.py` | `src/ii_agent/agent/application/plan_service.py` | Agent planning workflow |
| `src/ii_agent/engine/agents/dependencies.py` | `src/ii_agent/agent/dependencies.py` | Container/DI should import `agent`, not `engine` |
| `src/ii_agent/engine/sandboxes/*` | `src/ii_agent/agent/sandboxes/*` | Sandboxes are agent-only runtime state |
| `src/ii_agent/engine/prompts/*` | `src/ii_agent/agent/prompts/*` | Agent-only prompts |
| `src/ii_agent/engine/v1/*` | `src/ii_agent/agent/runtime/*` | Rename package only; do not call it legacy |
| `src/ii_agent/realtime/socket/*` | `src/ii_agent/agent/socket/*` | Socket.IO transport belongs to agent |
| `src/ii_agent/realtime/events/*` | `src/ii_agent/agent/events/*` | Event persistence is agent-owned |
| `src/ii_agent/realtime/subscribers/*` | `src/ii_agent/agent/events/subscribers/*` | Subscribers are part of the agent event pipeline |
| `src/ii_agent/sessions/validation_service.py` | `src/ii_agent/agent/application/session_validation_service.py` | This is an agent pre-run concern, not a session-shell concern |

#### Agent Notes

- Keep `engine/v1` behavior intact; this is primarily a package move and import rewrite.
- Keep agent table renames out of the first DB cut.
- `realtime/socket/socketio.py` should become `agent/socket/server.py`, not stay under a generic transport package, because it knows about session join, agent commands, and agent event flow.

### Chat

```text
src/ii_agent/chat/
├── api/            # router, HTTP/SSE dependencies, request/response schemas
├── application/    # chat orchestration services
├── llm/            # provider clients stay chat-owned for now
├── media/          # media orchestration stays chat-owned
├── messages/       # message model/repo/services
├── prompts/
├── providers/      # provider-owned chat persistence models
├── runs/           # new chat run lifecycle
├── summaries/      # summary model/service
├── tools/
├── types/          # internal message/content/tool datatypes
└── vectorstore/
```

#### Current To Target Map For Chat

| Current path | Target path | Notes |
| --- | --- | --- |
| `src/ii_agent/chat/router.py` | `src/ii_agent/chat/api/router.py` | HTTP entrypoint only |
| `src/ii_agent/chat/dependencies.py` | `src/ii_agent/chat/api/dependencies.py` | Chat DI should live beside the router |
| `src/ii_agent/chat/service.py` | `src/ii_agent/chat/application/chat_service.py` | Keep a facade for routers, but split run/session concerns out of it |
| `src/ii_agent/chat/message_service.py` | `src/ii_agent/chat/messages/service.py` | Message creation/translation |
| `src/ii_agent/chat/message_history_service.py` | `src/ii_agent/chat/messages/history_service.py` | Read-model logic for history |
| `src/ii_agent/chat/repository.py` | `src/ii_agent/chat/messages/repository.py` | Message persistence only |
| `src/ii_agent/chat/context_manager.py` | `src/ii_agent/chat/application/context_service.py` | Coordinates message loading plus summaries |
| `src/ii_agent/chat/file_processing_service.py` | `src/ii_agent/chat/application/file_processing_service.py` | Upload ingestion logic |
| `src/ii_agent/chat/file_processor.py` | `src/ii_agent/chat/application/file_processor.py` | Helper stays local to chat |
| `src/ii_agent/chat/tool_service.py` | `src/ii_agent/chat/application/tool_service.py` | Tool registry/policy orchestration |
| `src/ii_agent/chat/llm_loop_service.py` | `src/ii_agent/chat/application/turn_loop_service.py` | Main assistant turn loop |
| `src/ii_agent/chat/models.py` | split across `messages/models.py`, `runs/models.py`, `summaries/models.py`, `providers/models.py` | Current file mixes four different storage concerns |
| `src/ii_agent/chat/schemas.py` | split across `chat/api/schemas.py` and `chat/types/*` | Separate HTTP DTOs from internal chat datatypes |
| `src/ii_agent/chat/llm/*` | `src/ii_agent/chat/llm/*` | Keep provider clients in chat for now |
| `src/ii_agent/chat/media/*` | `src/ii_agent/chat/media/*` | Already well-scoped to chat |
| `src/ii_agent/chat/tools/*` | `src/ii_agent/chat/tools/*` | Chat-specific tool surface |
| `src/ii_agent/chat/vectorstore/*` | `src/ii_agent/chat/vectorstore/*` | Chat retrieval implementation stays local |

#### Chat Notes

- Do not make chat depend on `agent/runs/service.py`.
- The first new package to add is `chat/runs/`.
- `chat/llm/*` stays in chat because the current chat provider clients are not shared abstractions with the agent runtime.

### Shared And Session Boundaries

Keep these shared:

- `sessions/models.py`
- `sessions/repository.py`
- `sessions/router.py`
- `sessions/schemas.py`

Keep this in `sessions` for now:

- `sessions/fork_service.py`

Reason:

- it still creates session-shell rows
- it does not yet copy agent runtime state

Move this out of `sessions`:

- `sessions/validation_service.py` -> `agent/application/session_validation_service.py`

Reduce `sessions/service.py` over time to:

- session shell CRUD
- list/catalog queries
- public/private sharing
- lightweight session metadata

Do not move these into `core` in this phase:

- chat provider clients
- agent runtime model wrappers
- chat tool implementations
- agent event models

`core` should remain:

- config
- db manager/base repository
- redis locks and cancellation
- storage
- middleware
- service container
- shared LLM config/billing helpers that are already truly shared

## First DB Cut

### Goal

The first DB cut is not the full platform redesign.

Its goal is only this:

- stop chat from writing agent run tables
- make chat-owned tables read as chat-owned tables

### Tables In Scope Now

Chat-owned tables after the first cut:

- `chat_runs` new
- `chat_messages` existing name stays
- `chat_summaries` rename from `conversation_summaries`
- `chat_provider_containers` rename from `provider_containers`
- `chat_provider_files` rename from `provider_files`
- `chat_provider_vector_stores` rename from `provider_vector_stores`

Agent tables stay as-is in this cut:

- `agent_run_tasks`
- `agent_run_messages`
- `agent_run_events`
- `session_summaries`
- `sandboxes`
- `events`

Those tables are still agent-owned; only the rename is deferred.

### Recommended `chat_runs` Shape

`chat_runs` is the missing chat-owned lifecycle table.

Recommended columns:

- `id`
- `session_id`
- `user_message_id`
- `assistant_message_id` nullable
- `status`
- `finish_reason`
- `provider`
- `model_id`
- `request_metadata`
- `usage`
- `cost`
- `error_code`
- `error_message`
- `started_at`
- `completed_at` nullable
- `cancelled_at` nullable
- `created_at`
- `updated_at`
- `version`

Recommended status set:

- `running`
- `completed`
- `failed`
- `cancelled`

### Recommended Relationships

- `chat_runs.session_id -> sessions.id`
- `chat_runs.user_message_id -> chat_messages.id`
- `chat_runs.assistant_message_id -> chat_messages.id`
- `chat_messages.chat_run_id -> chat_runs.id` nullable
- `chat_summaries.session_id -> sessions.id`
- `chat_summaries.end_message_id -> chat_messages.id`
- `chat_provider_containers.session_id -> sessions.id`
- `chat_provider_files.session_id -> sessions.id`
- `chat_provider_files.file_upload_id -> file_uploads.id`
- `chat_provider_vector_stores.user_id -> users.id`

Important detail:

- `chat_provider_vector_stores` should remain user-scoped in the first cut, because the current OpenAI vector-store implementation reuses one provider vector store per user, not per session

### ORM Split For Chat Persistence

Rename the current chat ORM classes when the tables are renamed:

- `ConversationSummary` -> `ChatSummary`
- `ProviderContainer` -> `ChatProviderContainer`
- `ProviderFile` -> `ChatProviderFile`
- `ProviderVectorStore` -> `ChatProviderVectorStore`

Recommended module split:

- `chat/runs/models.py` -> `ChatRun`
- `chat/runs/repository.py` -> `ChatRunRepository`
- `chat/runs/service.py` -> `ChatRunService`
- `chat/messages/models.py` -> `ChatMessage`
- `chat/messages/repository.py` -> `ChatMessageRepository`
- `chat/messages/service.py` -> `MessageService`
- `chat/summaries/models.py` -> `ChatSummary`
- `chat/providers/models.py` -> provider-owned chat mapping tables

### Code Changes Implied By The First Cut

1. Replace `ChatService -> AgentRunService` with `ChatService -> ChatRunService`.
2. Create the chat run before the LLM turn starts and use that run ID for cancellation.
3. Update `chat/application/turn_loop_service.py` to receive a chat run ID, not an agent task ID.
4. Update provider and summary imports to use renamed chat-owned ORM classes.
5. Leave agent runtime services and tables alone in this step.

## What This Revision Does Not Do

These are valid later migrations, but they should not be bundled into the first
chat/agent split:

- adding `sessions.app_kind`
- moving public sharing into `session_shares`
- renaming `agent_run_tasks` to `agent_runs`
- renaming `agent_run_messages` to `agent_run_snapshots`
- renaming `agent_run_events` to `agent_event_log`
- creating `agent_plans`, `agent_milestones`, and `agent_requirements`
- moving all provider clients into a shared `core.llm.providers` package

That work can happen after chat is fully decoupled from agent run state.
