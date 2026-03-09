# Chat and Agent DB Ownership Design

Related docs:

- [Chat and Agent Application Design](./chat-agent-application-design.md)
- [Chat and Agent Migration Plan](./chat-agent-migration-plan.md)
- [Platform Database Redesign](./platform-database-redesign.md)
- [Platform Target Schema](./platform-target-schema.md)

## Core Decision

`chat` and `agent` should not share application-state tables.

They should share a small session shell in `sessions`, then own separate
application tables underneath it.

That means:

- keep one shared `sessions` table
- add separate `chat_*` tables for chat execution state
- keep separate `agent_*` tables for agent execution state
- stop letting `chat` write `agent_run_tasks`

## Short Answer

Yes, chat should have separate tables.

It already has part of that model today:

- `chat_messages`
- `conversation_summaries`
- `provider_containers`
- `provider_files`
- `provider_vector_stores`

What is missing is a chat-owned run lifecycle table.

Today, chat persists its visible conversation in chat tables, but uses
`agent_run_tasks` for run lifecycle, cancellation, and terminal status. That is
the wrong boundary for two separate applications.

The right shape is:

- shared `sessions`
- chat-owned `chat_runs`, `chat_messages`, `chat_summaries`, `chat_provider_*`
- agent-owned `agent_runs`, `agent_run_snapshots`, `agent_event_log`, `agent_*`

## Why This Matters

The current schema mixes three different concerns:

1. session ownership
2. chat conversation persistence
3. agent runtime persistence

That creates misleading coupling:

- chat depends on agent run state to stream and cancel turns
- session rows carry both chat and agent-specific fields
- there is no clear owner for event history
- integrity rules are inconsistent across tables

Once `chat` and `agent` are treated as separate applications, the database
should reflect that separation.

## Current Table Inventory

### Shared Session Shell

| Table | Current Owner | Notes |
| --- | --- | --- |
| `sessions` | `sessions` | Shared shell, but currently polluted with app-specific fields |

### Chat-Owned Today

| Table | Current Owner | Notes |
| --- | --- | --- |
| `chat_messages` | `chat` | Visible conversation messages |
| `conversation_summaries` | `chat` | Chat context compression |
| `provider_containers` | `chat` | Provider-side container state |
| `provider_files` | `chat` | Provider-side uploaded file mapping |
| `provider_vector_stores` | `chat` | Provider-side vector store mapping |

### Agent-Owned Today

| Table | Current Owner | Notes |
| --- | --- | --- |
| `agent_run_tasks` | `agent` | Run lifecycle table, but currently reused by chat |
| `agent_run_messages` | `agent` | Serialized run snapshot/history table |
| `agent_run_events` | `agent` | Low-level append-only event persistence |
| `session_summaries` | `agent` | Agent session summary table |
| `sandboxes` | `agent` | Sandbox lifecycle state |

### Generic In Name, Agent-Specific In Practice

| Table | Current Owner | Notes |
| --- | --- | --- |
| `events` | effectively `agent` | Frontend/socket projection table, not a true cross-app event store |

## Current Ownership Problems

### 1. Chat Writes Agent Tables

`chat` currently creates and updates `agent_run_tasks` for chat turns.

That makes chat dependent on agent lifecycle rules, status enums, cancellation
logic, and repository interfaces.

This is the main schema smell.

### 2. `sessions` Is Carrying Too Much Application State

The current `sessions` table includes a mix of:

- ownership and visibility fields
- chat-only summary pointers
- agent-only workspace and sandbox pointers
- token and cost counters that really belong to per-app execution data

That makes `sessions` harder to reason about and harder to evolve.

### 3. Event Ownership Is Fuzzy

There are two event tables today:

- `agent_run_events`
- `events`

They store different projections of mostly agent execution.

Neither is a good shared event model for both applications.

### 4. Referential Integrity Is Inconsistent

Several rows use plain strings where foreign keys should exist.

Examples:

- `chat_messages.session_id`
- `provider_containers.session_id`
- `provider_files.session_id`
- `agent_run_events.session_id`
- `session_summaries.session_id`
- `session_summaries.agent_run_id`

That weakens deletion guarantees and makes backfills more fragile.

### 5. Naming Hides Ownership

Some current names are too generic:

- `events`
- `session_summaries`
- `provider_files`

For two separate applications, table names should reveal ownership directly.

## Ownership Model

### Shared Rule

The `sessions` domain owns only the session shell.

The session shell answers:

- who owns this conversation
- which application owns it
- whether it is public
- whether it is deleted
- how it is listed

The session shell should not be the place where chat turns or agent execution
state live.

### Session Ownership

Recommended `sessions` responsibilities:

- `id`
- `user_id`
- `app_kind`
- `name`
- `llm_setting_id`
- `is_public`
- `public_url`
- `deleted_at`
- `created_at`
- `updated_at`
- lightweight listing metadata such as `last_message_at`

Recommended change:

- add `app_kind` with values `chat` and `agent`
- stop using `agent_type` to distinguish chat from agent
- keep `agent_type` only for agent subtypes if that concept is still needed

Fields that should move out of `sessions` over time:

- `sandbox_id`
- `agent_state_path`
- `state_storage_url`
- `summary_message_id`
- `prompt_tokens`
- `completion_tokens`
- `cost`

Those belong in application-owned tables or derived projections.

### Chat Ownership

Chat should be message-centric and turn-centric.

It does not need the same persistence shape as agent.

Recommended chat-owned tables:

- `chat_runs`
- `chat_messages`
- `chat_summaries`
- `chat_provider_containers`
- `chat_provider_files`
- `chat_provider_vector_stores`

### `chat_runs`

This is the missing table.

One row per user turn / assistant generation lifecycle.

Recommended fields:

- `id`
- `session_id` FK -> `sessions.id`
- `user_message_id` FK -> `chat_messages.id`
- `assistant_message_id` FK -> `chat_messages.id`, nullable
- `status`
- `finish_reason`
- `model_id`
- `provider`
- `request_metadata`
- `usage`
- `cost`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`
- `cancelled_at`
- `created_at`
- `updated_at`
- `version`

Why chat needs this table:

- cancellation should target a chat run, not an agent run
- status should be chat-owned
- billing and usage should attach to a chat turn
- retries and incomplete assistant messages should attach to a chat run

### `chat_messages`

Keep this table, but strengthen it.

Recommended changes:

- add `session_id` FK -> `sessions.id`
- add `run_id` FK -> `chat_runs.id`, nullable for imported history if needed
- add `parent_message_id` FK -> `chat_messages.id`
- keep message content as structured parts
- keep provider metadata and tool metadata here only if they are message-scoped

Recommended responsibility:

- only visible or user-meaningful messages
- user messages
- assistant messages
- tool result messages if chat UI shows them as conversation artifacts

Do not overload this table with resumable runtime state.

### `chat_summaries`

This can evolve from `conversation_summaries`.

Recommended changes:

- rename `conversation_summaries` -> `chat_summaries`
- keep `session_id` FK -> `sessions.id`
- make `end_message_id` FK -> `chat_messages.id`
- keep recursive compression via `parent_summary_id`

Recommended responsibility:

- rolling context compression only
- not agent memory
- not replayable execution state

### `chat_provider_containers`

This can evolve from `provider_containers`.

Recommended responsibility:

- provider container IDs
- code interpreter/session handles
- TTL / expiration
- raw provider payload if needed for debugging

Recommended changes:

- rename to make ownership explicit
- add `session_id` FK -> `sessions.id`

### `chat_provider_files`

This can evolve from `provider_files`.

Recommended responsibility:

- mapping from platform file uploads to provider file IDs
- provider-side expiration and raw metadata

Recommended changes:

- rename to make ownership explicit
- add `session_id` FK -> `sessions.id`
- replace plain `file_id` with a real FK to `file_uploads.id` if that is the source object

### `chat_provider_vector_stores`

This can evolve from `provider_vector_stores`.

Recommended responsibility:

- provider-side vector store handles used by chat retrieval flows

Recommended changes:

- rename to make ownership explicit
- keep unique constraints on provider identifiers

### Do We Need `chat_events`?

Not by default.

Chat is already recoverable from:

- `chat_runs`
- `chat_messages`
- `chat_summaries`

If the product later needs replayable SSE debugging or fine-grained tool traces,
add a separate `chat_turn_events` projection table. Do not reuse the agent
event tables.

### Agent Ownership

Agent should remain run-centric and event-centric.

Recommended agent-owned tables:

- `agent_runs`
- `agent_run_snapshots`
- `agent_event_log`
- `agent_plans`
- `agent_milestones`
- `agent_summaries`
- `agent_sandboxes`

### `agent_runs`

This evolves from `agent_run_tasks`.

Recommended responsibility:

- canonical lifecycle for a single agent run
- parent-child run relationships
- status and terminal reason
- pointers to originating user input if needed

Recommended fields:

- `id`
- `session_id` FK -> `sessions.id`
- `parent_run_id` FK -> `agent_runs.id`, nullable
- `origin_message_id`, nullable
- `status`
- `error_message`
- `started_at`
- `completed_at`
- `created_at`
- `updated_at`
- `version`

### `agent_run_snapshots`

This evolves from `agent_run_messages`.

The current `agent_run_messages` table is not really “messages” in the chat
sense. It is a resumable run snapshot with serialized inputs, messages, tools,
metrics, and additional runtime metadata.

Recommended responsibility:

- resumable run state
- serialized message history for the runtime
- pending tools / requirements
- model/runtime metadata
- metrics for the run

Recommended change:

- rename from `agent_run_messages` to `agent_run_snapshots`

### `agent_event_log`

This evolves from `agent_run_events`.

Recommended responsibility:

- append-only execution/audit log
- replay
- debugging
- event-based recovery if needed

Recommended changes:

- add `session_id` FK -> `sessions.id`
- add `run_id` FK -> `agent_runs.id`
- keep event name, group, payload, timestamps

### `agent_ui_events`

Current `events` is effectively a UI projection for agent websocket consumers.

You have two options:

1. keep a separate projection table and rename `events` -> `agent_ui_events`
2. remove it later and hydrate UI directly from `agent_event_log`

My recommendation:

- keep it only if the frontend needs a filtered, stable projection
- otherwise collapse toward `agent_event_log`

What should not happen:

- keeping a generic `events` table that only agent really owns

### `agent_summaries`

This evolves from `session_summaries`.

Recommended changes:

- rename to make ownership explicit
- add `session_id` FK -> `sessions.id`
- replace `agent_run_id` with a real FK to the owning run or snapshot table

Recommended responsibility:

- agent memory compression
- run/session summaries for the agent runtime

This is not the same thing as chat context summarization and should stay
separate from `chat_summaries`.

### `agent_sandboxes`

This is already an agent-owned concept.

Recommended responsibility:

- sandbox provider IDs
- state machine
- lifecycle timestamps
- session and run linkage as needed

This should not live on the shared `sessions` shell.

## Adjacent Domain Ownership

### `files`

`files` owns uploaded file metadata and storage identity.

That means:

- `file_uploads` stays under `files`
- chat and agent should reference file rows by FK
- provider-side upload mappings belong to the app using them

Good split:

- `files.file_uploads` owns the local platform file
- `chat_provider_files` owns the provider mapping for chat usage
- if agent needs provider file mappings later, it should get its own `agent_*`
  table, not reuse chat's

### `projects`

`projects` stays separate from `sessions`.

Projects are session-scoped, but they are not part of chat or agent runtime
state. They own:

- project metadata
- deployments
- domains
- databases
- secrets

Keep those tables in `projects`.

### `billing`

`billing` should own credit and usage accounting tables.

Chat and agent should publish normalized usage records through services, not
write each other's run tables to infer cost later.

## Recommended Target Schema

```text
sessions
├── sessions

chat
├── chat_runs
├── chat_messages
├── chat_summaries
├── chat_provider_containers
├── chat_provider_files
└── chat_provider_vector_stores

agent
├── agent_runs
├── agent_run_snapshots
├── agent_event_log
├── agent_ui_events        # optional projection
├── agent_plans
├── agent_milestones
├── agent_summaries
└── agent_sandboxes

projects
├── projects
├── project_deployments
├── project_custom_domains
└── project_databases

files
└── file_uploads
```

## Database Flow By Application

### Chat Flow

1. `sessions` creates or loads the shared session shell with `app_kind=chat`.
2. `chat` creates `chat_runs` with `status=running`.
3. `chat` writes the user message to `chat_messages`.
4. `chat` resolves provider state from `chat_provider_*`.
5. `chat` streams the assistant turn.
6. `chat` writes assistant/tool messages to `chat_messages`.
7. `chat` updates `chat_runs` with terminal status, finish reason, usage, and cost.
8. `chat` updates `chat_summaries` if compression is needed.
9. `sessions` may update shell metadata like `last_message_at`.

No agent tables should be touched in this flow.

### Agent Flow

1. `sessions` creates or loads the shared session shell with `app_kind=agent`.
2. `agent` creates `agent_runs` with `status=running`.
3. `agent` appends execution records to `agent_event_log`.
4. `agent` updates `agent_run_snapshots` as resumable state changes.
5. `agent` updates `agent_plans`, `agent_milestones`, and `agent_sandboxes` as needed.
6. `agent` optionally projects frontend-facing events into `agent_ui_events`.
7. `agent` marks `agent_runs` terminal status.
8. `agent` updates `agent_summaries` for future runs.
9. `sessions` may update shell metadata like `last_message_at`.

No chat tables should be touched in this flow.

## Referential Integrity Rules

Recommended minimum rules:

- every `*_runs.session_id` should FK `sessions.id`
- `chat_messages.run_id` should FK `chat_runs.id`
- `chat_messages.parent_message_id` should FK `chat_messages.id`
- `chat_summaries.end_message_id` should FK `chat_messages.id`
- `agent_run_snapshots.run_id` should FK `agent_runs.id`
- `agent_event_log.run_id` should FK `agent_runs.id`
- provider mapping tables should FK their owning app/session records
- file references should FK `file_uploads.id` where applicable

If a row cannot have a foreign key for a hard technical reason, document why and
make that exception explicit.

## Exact Migration Sequence

This is the rollout order I would use in production.

It is intentionally an expand -> backfill -> dual-write -> cutover -> contract
sequence.

Do not try to rename, backfill, and cut application reads over in one revision.

### Release 1: Expand Schema Only

Add the minimum schema needed for the new chat-owned lifecycle without changing
runtime behavior yet.

Create one Alembic revision for this step.

Recommended changes:

1. add `sessions.app_kind` as nullable
2. create `chat_runs`
3. add nullable `chat_messages.run_id`
4. add supporting indexes
5. add foreign keys as `NOT VALID` where table size or dirty historical data
   makes immediate validation risky

Recommended phase-1 `chat_runs` columns:

- `id UUID PRIMARY KEY`
- `session_id`
- `user_message_id`
- `assistant_message_id`
- `status`
- `finish_reason`
- `model_id`
- `usage`
- `error_message`
- `started_at`
- `completed_at`
- `cancelled_at`
- `created_at`
- `updated_at`
- `version`

Alembic-style shape:

```python
def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("app_kind", sa.String(length=16), nullable=True),
    )

    op.create_table(
        "chat_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("finish_reason", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("usage", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_runs"),
    )

    op.add_column(
        "chat_messages",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sessions_app_kind "
            "ON sessions (app_kind)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chat_runs_session_created "
            "ON chat_runs (session_id, created_at)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chat_runs_user_message "
            "ON chat_runs (user_message_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chat_messages_run_id "
            "ON chat_messages (run_id)"
        )

    op.execute(
        "ALTER TABLE chat_runs "
        "ADD CONSTRAINT fk_chat_runs_session_id "
        "FOREIGN KEY (session_id) REFERENCES sessions(id) "
        "ON DELETE CASCADE NOT VALID"
    )
    op.execute(
        "ALTER TABLE chat_messages "
        "ADD CONSTRAINT fk_chat_messages_run_id "
        "FOREIGN KEY (run_id) REFERENCES chat_runs(id) "
        "ON DELETE SET NULL NOT VALID"
    )
```

Large-table rule for Release 1:

- add nullable columns first
- avoid `server_default` on large existing tables unless you want a table rewrite
- create big indexes concurrently
- do not rename existing large tables in this release

### Release 2: Backfill Data

Run the schema revision first, then backfill in batches outside Alembic.

Use the script here:

- [backfill_chat_split.py](/Users/pip/work/ii-agent-prod/scripts/backfill_chat_split.py)

Recommended order:

1. backfill `sessions.app_kind`
2. backfill `chat_runs` from existing chat-linked `agent_run_tasks`
3. backfill `chat_messages.run_id`

Recommended commands:

```bash
uv run python scripts/backfill_chat_split.py --phase sessions-app-kind
uv run python scripts/backfill_chat_split.py --phase chat-runs --batch-size 1000
uv run python scripts/backfill_chat_split.py --phase message-run-id --batch-size 1000
```

For cautious production rollout:

```bash
uv run python scripts/backfill_chat_split.py --phase chat-runs --batch-size 500 --max-batches 20 --sleep-seconds 0.2
uv run python scripts/backfill_chat_split.py --phase message-run-id --batch-size 1000 --max-batches 20 --sleep-seconds 0.2
```

### Release 3: Dual-Write Application

Deploy application code that writes both old and new chat lifecycle state.

Required behavior:

1. chat creates `chat_runs`
2. chat continues writing `agent_run_tasks` temporarily
3. chat writes `chat_messages.run_id` for all new messages
4. chat cancellation can still fall back to `agent_run_tasks` during this phase

This release reduces risk because backfill and new writes can coexist.

### Release 4: Read Cutover

Deploy application code that reads chat lifecycle only from chat-owned tables.

Required behavior:

1. chat status lookup reads `chat_runs`
2. chat cancellation targets `chat_runs`
3. chat billing and usage derive from `chat_runs` + `chat_messages`
4. `sessions.app_kind` becomes the authoritative app discriminator

At this point, `chat` should no longer depend on `AgentRunService`.

### Release 5: Contract Constraints

Once backfill and read cutover are stable:

1. validate foreign keys
2. set `sessions.app_kind` to `NOT NULL`
3. add any remaining `NOT NULL` constraints that are now safe
4. remove dual-write from chat

Alembic-style shape:

```python
def upgrade() -> None:
    op.execute("ALTER TABLE chat_runs VALIDATE CONSTRAINT fk_chat_runs_session_id")
    op.execute("ALTER TABLE chat_messages VALIDATE CONSTRAINT fk_chat_messages_run_id")

    op.alter_column("sessions", "app_kind", nullable=False)
```

### Release 6: Remove Legacy Chat Use Of Agent Tables

Only after cutover is proven:

1. stop chat writes to `agent_run_tasks`
2. delete chat-specific code paths from `AgentRunService` consumers
3. decide whether historical chat rows remain in `agent_run_tasks` or get archived

Do not drop legacy tables just because chat has stopped using them.
Keep that as a separate, later cleanup decision.

## Large Table Migration Rules

These rules matter for `chat_messages`, `agent_run_tasks`, and any future event
or snapshot table.

### Rules

1. never do a single-shot `UPDATE` or `INSERT ... SELECT` for millions of rows
   inside one Alembic transaction
2. add nullable columns first, backfill later, then enforce `NOT NULL`
3. use keyset pagination, not `OFFSET`
4. create large indexes concurrently
5. commit every batch
6. make backfills idempotent
7. preserve an easy rollback point between each release

### What Belongs In Alembic

- additive schema changes
- new tables
- nullable columns
- constraints added as `NOT VALID`
- small metadata updates

### What Should Not Live In Alembic

- hours-long backfills
- high-churn batch jobs
- operational throttling logic
- resumable progress loops

Those belong in an operational script like
[backfill_chat_split.py](/Users/pip/work/ii-agent-prod/scripts/backfill_chat_split.py).

## Post-Backfill Verification

Run these checks before read cutover.

### Check 1: Session App Kind

```sql
SELECT app_kind, COUNT(*)
FROM sessions
GROUP BY app_kind;
```

### Check 2: Chat Run Count Matches Legacy

```sql
SELECT COUNT(*)
FROM agent_run_tasks art
JOIN sessions s ON s.id = art.session_id
WHERE COALESCE(s.app_kind, CASE WHEN s.agent_type = 'chat' THEN 'chat' ELSE 'agent' END) = 'chat';

SELECT COUNT(*)
FROM chat_runs;
```

### Check 3: Messages Missing Run Links

```sql
SELECT role, COUNT(*)
FROM chat_messages
WHERE role IN ('user', 'assistant', 'tool')
  AND run_id IS NULL
GROUP BY role;
```

### Check 4: Legacy/New Status Drift

```sql
SELECT art.status AS legacy_status, cr.status AS new_status, COUNT(*)
FROM agent_run_tasks art
JOIN chat_runs cr ON cr.id = art.id
GROUP BY art.status, cr.status
ORDER BY COUNT(*) DESC;
```

## Migration Plan

### Phase 1: Draw The Ownership Line

1. add `sessions.app_kind`
2. stop using `agent_type == "chat"` as the app discriminator
3. add `chat_runs`
4. update `chat` to use `chat_runs` instead of `agent_run_tasks`

This is the highest-value change.

### Phase 2: Fix Naming And Integrity

1. rename `conversation_summaries` -> `chat_summaries`
2. rename `provider_*` tables -> `chat_provider_*`
3. rename `agent_run_tasks` -> `agent_runs`
4. rename `agent_run_messages` -> `agent_run_snapshots`
5. rename `agent_run_events` -> `agent_event_log`
6. rename `session_summaries` -> `agent_summaries`
7. add missing foreign keys and indexes

### Phase 3: Reduce Session Pollution

1. move agent-only fields off `sessions`
2. move chat-only fields off `sessions`
3. keep only shell metadata in `sessions`

### Phase 4: Clean Up Event Projections

1. decide whether `events` survives as `agent_ui_events`
2. if yes, make it explicitly agent-owned
3. if no, remove it after frontend hydration can read from `agent_event_log`

## Immediate Fixes

These are worth doing before the bigger migration:

1. add deleted-session filtering consistently to all session access paths
2. stop chat from creating and updating `agent_run_tasks`
3. add missing foreign keys for obvious ownership links
4. split app discriminator from agent subtype by introducing `sessions.app_kind`

## Final Recommendation

Yes, chat should have separate tables.

More specifically:

- keep one shared `sessions` shell
- do not create a separate `chat_sessions` root table unless product ownership
  truly diverges later
- create `chat_runs` as the missing chat lifecycle table
- keep `chat_messages` and `chat_summaries` as chat-owned tables
- keep agent runtime state entirely under `agent_*` tables

That gives you a clean ownership model without duplicating the session shell.
