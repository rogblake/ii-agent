# Platform DB Diagram And Data Flow

Related docs:

- [Platform Target Schema](./platform-target-schema.md)
- [Platform Database Redesign](./platform-database-redesign.md)
- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)
- [Chat and Agent Application Design](./chat-agent-application-design.md)

## Scope

This is a visual companion to the target schema docs.

- It uses the target table names from [Platform Target Schema](./platform-target-schema.md).
- It optimizes for readability, so it shows the main ownership edges and omits some secondary tables and most columns.
- It treats `sessions` as the shared shell and `chat_*` / `agent_*` as separate application-owned persistence.

Current repo naming is still partly transitional:

- `conversation_summaries` becomes `chat_summaries`
- `provider_*` becomes `chat_provider_*`
- `agent_run_tasks` / `agent_run_messages` / `agent_run_events` evolve toward `agent_runs` / `agent_run_snapshots` / `agent_event_log`

## Domain Map

| Domain | Main tables | Purpose |
| --- | --- | --- |
| Identity | `users`, `user_profiles`, `user_api_keys`, `waitlist_entries` | User identity, profile, API access, waitlist |
| Billing and metering | `billing_customers`, `billing_subscriptions`, `billing_events`, `credit_ledger`, `usage_records` | Customer state, webhook/event capture, credits, usage accounting |
| Settings | `llm_provider_credentials`, `llm_profiles`, `mcp_server_configs` | User-configured provider credentials and model profiles |
| Session shell | `sessions`, `session_shares`, `session_bookmarks` | Shared ownership and listing shell for both apps |
| Chat runtime | `chat_runs`, `chat_messages`, `chat_summaries`, `chat_provider_*` | Chat turn lifecycle, visible conversation, provider-side chat resources |
| Agent runtime | `agent_runs`, `agent_run_snapshots`, `agent_event_log`, `agent_ui_events`, `agent_summaries`, `agent_sandboxes`, `agent_plans`, `agent_milestones`, `agent_requirements` | Agent execution state, event history, planning, sandbox lifecycle |
| Files | `file_uploads` | User-uploaded files shared across app flows |
| Projects | `projects`, `project_deployments`, `project_domains`, `project_databases`, `project_secrets`, `project_storage_resources` | Project workspace and deployment resources |
| Content | `presentations`, `presentation_slides`, `presentation_slide_versions`, `slide_templates`, `storybooks`, `storybook_*`, `media_templates` | Generated slides and storybook assets |
| Skills and integrations | `skills`, `integration_connections`, `composio_profiles` | User-installed skills and external integrations |
| Mobile and system | `apple_accounts`, `apple_build_credentials`, `system_configs` | Apple build credentials and platform config |

## Core ER Diagram

This diagram focuses on the operational center of the redesign: identity, settings, sessions, chat, agent, files, projects, and metering.

```mermaid
erDiagram
    USERS {
        uuid id PK
        text email
        text role
        timestamptz created_at
    }

    USER_PROFILES {
        uuid user_id PK, FK
        text language
        jsonb profile_metadata
    }

    LLM_PROFILES {
        uuid id PK
        uuid user_id FK
        text name
        text model
    }

    SESSIONS {
        uuid id PK
        uuid user_id FK
        uuid llm_profile_id FK
        text app_kind
        timestamptz last_message_at
    }

    SESSION_SHARES {
        uuid id PK
        uuid session_id FK
        text visibility
        text public_url
    }

    SESSION_BOOKMARKS {
        uuid user_id PK, FK
        uuid session_id PK, FK
        timestamptz created_at
    }

    FILE_UPLOADS {
        uuid id PK
        uuid user_id FK
        uuid session_id FK
        text storage_path
    }

    CHAT_RUNS {
        uuid id PK
        uuid session_id FK
        text status
        text provider
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid session_id FK
        uuid run_id FK
        text role
        bool is_finished
    }

    CHAT_SUMMARIES {
        uuid id PK
        uuid session_id FK
        uuid end_message_id FK
        text model_id
    }

    AGENT_RUNS {
        uuid id PK
        uuid session_id FK
        uuid parent_run_id FK
        text status
    }

    AGENT_EVENT_LOG {
        bigint id PK
        uuid session_id FK
        uuid run_id FK
        text event_name
    }

    AGENT_PLANS {
        uuid id PK
        uuid run_id FK
        uuid session_id FK
        bigint revision
    }

    AGENT_SANDBOXES {
        uuid id PK
        uuid session_id FK
        text provider
        text status
    }

    PROJECTS {
        uuid id PK
        uuid user_id FK
        uuid session_id FK
        text status
    }

    PROJECT_DEPLOYMENTS {
        uuid id PK
        uuid project_id FK
        text environment
        text deployment_status
    }

    USAGE_RECORDS {
        bigint id PK
        uuid user_id FK
        uuid session_id
        uuid run_id
        text app_kind
    }

    CREDIT_LEDGER {
        bigint id PK
        uuid user_id FK
        numeric delta_credits
        timestamptz created_at
    }

    USERS ||--o| USER_PROFILES : has
    USERS ||--o{ LLM_PROFILES : owns
    USERS ||--o{ SESSIONS : owns
    USERS ||--o{ FILE_UPLOADS : uploads
    USERS ||--o{ PROJECTS : owns
    USERS ||--o{ USAGE_RECORDS : accrues
    USERS ||--o{ CREDIT_LEDGER : accrues

    LLM_PROFILES o|--o{ SESSIONS : configures

    SESSIONS o|--o{ SESSIONS : forks_from
    SESSIONS ||--o| SESSION_SHARES : exposes
    SESSIONS ||--o{ SESSION_BOOKMARKS : bookmarked_by
    SESSIONS o|--o{ FILE_UPLOADS : scopes
    SESSIONS ||--o{ CHAT_RUNS : owns
    SESSIONS ||--o{ CHAT_MESSAGES : contains
    SESSIONS ||--o{ CHAT_SUMMARIES : compresses
    SESSIONS ||--o{ AGENT_RUNS : owns
    SESSIONS ||--o{ AGENT_EVENT_LOG : collects
    SESSIONS ||--o{ AGENT_PLANS : tracks
    SESSIONS ||--o| AGENT_SANDBOXES : sandbox
    SESSIONS o|--o| PROJECTS : seeds

    CHAT_RUNS ||--o{ CHAT_MESSAGES : groups
    CHAT_MESSAGES o|--o{ CHAT_MESSAGES : parent_of
    CHAT_MESSAGES ||--o{ CHAT_SUMMARIES : summarized_at

    AGENT_RUNS o|--o{ AGENT_RUNS : parent_of
    AGENT_RUNS ||--o{ AGENT_EVENT_LOG : emits
    AGENT_RUNS ||--o{ AGENT_PLANS : drives

    PROJECTS ||--o{ PROJECT_DEPLOYMENTS : deploys

    SESSION_BOOKMARKS }o--|| USERS : created_by
    FILE_UPLOADS ||--o{ CHAT_MESSAGES : referenced_by
```

Notes:

- Omitted for readability: `billing_*`, `llm_provider_credentials`, `mcp_server_configs`, `chat_provider_*`, `agent_run_snapshots`, `agent_ui_events`, `agent_summaries`, `agent_milestones`, `agent_requirements`, content tables, integrations, mobile, and system tables.
- `usage_records.run_id` is intentionally not shown as a hard foreign key edge because the target schema treats it as polymorphic across `chat_runs` and `agent_runs`.
- `projects.current_production_deployment_id` is also omitted from the diagram because it is a follow-up circular foreign key in the DDL sketch.

## Data Flow

The key design rule is: `sessions` is the shared shell, while chat and agent write their own runtime tables.

### Chat Turn Flow

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant ChatApp as Chat app
    participant SessionDB as sessions, llm_profiles
    participant FileDB as file_uploads, chat_provider_*
    participant ChatDB as chat_runs, chat_messages, chat_summaries
    participant Metering as usage_records, credit_ledger

    User->>ChatApp: send prompt, session_id, optional files
    ChatApp->>SessionDB: load session shell and llm profile
    ChatApp->>FileDB: resolve uploads and provider file/vector mappings
    ChatApp->>ChatDB: insert user chat_message
    ChatApp->>ChatDB: create chat_run(status=running)
    ChatApp->>ChatDB: create or update assistant chat_message while streaming
    ChatApp->>ChatDB: finalize chat_run and optional chat_summary
    ChatApp->>SessionDB: update sessions.last_message_at
    ChatApp->>Metering: append usage_records and credit_ledger rows
```

### Agent Run Flow

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant AgentApp as Agent app or socket
    participant SessionDB as sessions, llm_profiles
    participant ProjectDB as projects, project_*
    participant AgentDB as agent_runs, snapshots, events, plans, sandboxes
    participant Metering as usage_records, credit_ledger

    User->>AgentApp: start or resume agent run
    AgentApp->>SessionDB: load session shell, llm profile, parent session
    AgentApp->>ProjectDB: resolve linked project resources when present
    AgentApp->>AgentDB: create agent_run(status=running)
    AgentApp->>AgentDB: create or refresh agent_sandbox
    AgentApp->>AgentDB: write snapshots and append event log or ui events
    AgentApp->>AgentDB: update plans, milestones, and requirements during execution
    AgentApp->>AgentDB: finalize run and optional agent_summary
    AgentApp->>SessionDB: update sessions.last_message_at
    AgentApp->>Metering: append usage_records and credit_ledger rows
```

### Cross-Cutting Rules

- `sessions` should answer ownership, app kind, sharing, and list metadata; it should not carry chat turn state or agent runtime state.
- Chat cancellation and completion should target `chat_runs`, not `agent_runs`.
- Agent execution history should append to `agent_event_log` and related agent-owned tables, not to generic cross-app tables.
- Files, projects, and billing are shared supporting domains; they should be referenced by chat or agent, but not used to collapse the app boundary.
