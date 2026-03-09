# Platform Target Schema

Related docs:

- [Platform Database Redesign](./platform-database-redesign.md)
- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)

## Scope

This document defines the exact target schema for the redesigned platform
database.

It is written as PostgreSQL-oriented DDL sketches.

Assumptions:

- PostgreSQL 15+
- `gen_random_uuid()` is available
- all tables live in the default `public` schema
- volatile application statuses remain `TEXT` and are validated in application code
- `updated_at` is maintained by application code unless a trigger is added later

## Shared Conventions

### Data Types

- internal root IDs: `UUID`
- append-heavy event/ledger tables: `BIGINT GENERATED ALWAYS AS IDENTITY`
- money / credits: `NUMERIC(18,6)`
- counters / tokens: `BIGINT`
- timestamps: `TIMESTAMPTZ`
- schemaless payloads: `JSONB`

### Delete Rules

- root-owned children: `ON DELETE CASCADE`
- optional references: `ON DELETE SET NULL`

### Naming

- root tables remain simple: `users`, `sessions`, `projects`
- app-owned runtime tables are prefixed: `chat_*`, `agent_*`
- projection tables are explicit: `agent_ui_events`

## Identity

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    password_hash TEXT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    login_provider TEXT NULL,
    organization TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_users_email_ci ON users ((lower(email)));
CREATE INDEX idx_users_created_at ON users (created_at DESC);


CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_name TEXT NULL,
    last_name TEXT NULL,
    avatar_url TEXT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    profile_metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE user_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NULL,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_user_api_keys_key_hash ON user_api_keys (key_hash);
CREATE INDEX idx_user_api_keys_user_active ON user_api_keys (user_id, is_active);
CREATE INDEX idx_user_api_keys_expires_at ON user_api_keys (expires_at);


CREATE TABLE waitlist_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_waitlist_entries_email_ci ON waitlist_entries ((lower(email)));
```

## Billing

```sql
CREATE TABLE billing_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_customer_id TEXT NOT NULL,
    customer_metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_billing_customers_user_provider
    ON billing_customers (user_id, provider);
CREATE UNIQUE INDEX uq_billing_customers_provider_external
    ON billing_customers (provider, external_customer_id);


CREATE TABLE billing_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_customer_id UUID NOT NULL REFERENCES billing_customers(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_subscription_id TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    status TEXT NOT NULL,
    billing_cycle TEXT NULL,
    subscription_metadata JSONB NULL,
    current_period_start TIMESTAMPTZ NULL,
    current_period_end TIMESTAMPTZ NULL,
    cancel_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_billing_subscriptions_provider_external
    ON billing_subscriptions (provider, provider_subscription_id);
CREATE INDEX idx_billing_subscriptions_customer_status
    ON billing_subscriptions (billing_customer_id, status);


CREATE TABLE billing_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    provider_object_id TEXT NULL,
    event_type TEXT NOT NULL,
    amount NUMERIC(18,6) NULL,
    currency TEXT NULL,
    raw_payload JSONB NULL,
    processed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_billing_events_provider_event
    ON billing_events (provider, provider_event_id);
CREATE INDEX idx_billing_events_user_created
    ON billing_events (user_id, created_at DESC);
CREATE INDEX idx_billing_events_object
    ON billing_events (provider, provider_object_id);


CREATE TABLE credit_ledger (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    source_table TEXT NULL,
    source_id UUID NULL,
    delta_credits NUMERIC(18,6) NOT NULL,
    balance_after NUMERIC(18,6) NULL,
    entry_metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_credit_ledger_user_created
    ON credit_ledger (user_id, created_at DESC);
CREATE INDEX idx_credit_ledger_source
    ON credit_ledger (source_table, source_id);


CREATE TABLE usage_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NULL,
    app_kind TEXT NOT NULL,
    run_id UUID NULL,
    source_table TEXT NOT NULL,
    source_id UUID NULL,
    model_id TEXT NULL,
    provider TEXT NULL,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    cache_read_tokens BIGINT NOT NULL DEFAULT 0,
    cache_write_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd NUMERIC(18,6) NULL,
    credits_delta NUMERIC(18,6) NULL,
    usage_metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_usage_records_app_kind
        CHECK (app_kind IN ('chat', 'agent'))
);

CREATE INDEX idx_usage_records_user_created
    ON usage_records (user_id, created_at DESC);
CREATE INDEX idx_usage_records_session_created
    ON usage_records (session_id, created_at DESC);
CREATE INDEX idx_usage_records_source
    ON usage_records (source_table, source_id);
```

## Settings

```sql
CREATE TABLE llm_provider_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    credential_name TEXT NOT NULL,
    api_type TEXT NOT NULL,
    encrypted_api_key TEXT NULL,
    base_url TEXT NULL,
    credential_metadata JSONB NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_llm_provider_credentials_user_provider_name
    ON llm_provider_credentials (user_id, provider, credential_name);
CREATE INDEX idx_llm_provider_credentials_user_active
    ON llm_provider_credentials (user_id, is_active);


CREATE TABLE llm_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id UUID NULL REFERENCES llm_provider_credentials(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature NUMERIC(6,3) NOT NULL DEFAULT 1.000,
    thinking_tokens BIGINT NULL,
    max_retries INTEGER NOT NULL DEFAULT 10,
    max_message_chars INTEGER NOT NULL DEFAULT 30000,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    profile_metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_llm_profiles_user_name
    ON llm_profiles (user_id, name)
    WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_llm_profiles_system_name
    ON llm_profiles (name)
    WHERE user_id IS NULL;
CREATE INDEX idx_llm_profiles_model_active
    ON llm_profiles (model, is_active);


CREATE TABLE mcp_server_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    config_json JSONB NOT NULL,
    config_metadata JSONB NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_mcp_server_configs_user_name
    ON mcp_server_configs (user_id, name);
CREATE INDEX idx_mcp_server_configs_user_active
    ON mcp_server_configs (user_id, is_active);
```

## Sessions

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_kind TEXT NOT NULL,
    name TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    llm_profile_id UUID NULL REFERENCES llm_profiles(id) ON DELETE SET NULL,
    parent_session_id UUID NULL REFERENCES sessions(id) ON DELETE SET NULL,
    session_metadata JSONB NULL,
    last_message_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    CONSTRAINT ck_sessions_app_kind
        CHECK (app_kind IN ('chat', 'agent'))
);

CREATE INDEX idx_sessions_user_created
    ON sessions (user_id, created_at DESC);
CREATE INDEX idx_sessions_app_last_message
    ON sessions (app_kind, last_message_at DESC);
CREATE INDEX idx_sessions_parent_session
    ON sessions (parent_session_id);
CREATE INDEX idx_sessions_not_deleted
    ON sessions (user_id, deleted_at, created_at DESC);


CREATE TABLE session_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL DEFAULT 'private',
    share_token TEXT NULL,
    public_url TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_session_shares_session
    ON session_shares (session_id);
CREATE UNIQUE INDEX uq_session_shares_token
    ON session_shares (share_token)
    WHERE share_token IS NOT NULL;


CREATE TABLE session_bookmarks (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, session_id)
);

CREATE INDEX idx_session_bookmarks_session
    ON session_bookmarks (session_id);
```

## Chat

```sql
CREATE TABLE chat_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_message_id UUID NULL,
    assistant_message_id UUID NULL,
    status TEXT NOT NULL,
    finish_reason TEXT NULL,
    model_id TEXT NULL,
    provider TEXT NULL,
    request_metadata JSONB NULL,
    usage JSONB NULL,
    cost_usd NUMERIC(18,6) NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_chat_runs_session_created
    ON chat_runs (session_id, created_at DESC);
CREATE INDEX idx_chat_runs_status
    ON chat_runs (status, created_at DESC);
CREATE UNIQUE INDEX uq_chat_runs_user_message
    ON chat_runs (user_message_id)
    WHERE user_message_id IS NOT NULL;
CREATE UNIQUE INDEX uq_chat_runs_assistant_message
    ON chat_runs (assistant_message_id)
    WHERE assistant_message_id IS NOT NULL;


CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id UUID NULL REFERENCES chat_runs(id) ON DELETE SET NULL,
    role TEXT NOT NULL,
    content JSONB NOT NULL,
    usage JSONB NULL,
    tokens BIGINT NULL,
    model TEXT NULL,
    tools JSONB NULL,
    metadata JSONB NULL,
    provider_metadata JSONB NULL,
    file_ids UUID[] NULL,
    parent_message_id UUID NULL REFERENCES chat_messages(id) ON DELETE SET NULL,
    is_finished BOOLEAN NOT NULL DEFAULT TRUE,
    finish_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_session_created
    ON chat_messages (session_id, created_at ASC);
CREATE INDEX idx_chat_messages_run_id
    ON chat_messages (run_id);
CREATE INDEX idx_chat_messages_parent
    ON chat_messages (parent_message_id);


CREATE TABLE chat_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    end_message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    parent_summary_id UUID NULL REFERENCES chat_summaries(id) ON DELETE SET NULL,
    summary_text TEXT NOT NULL,
    original_tokens BIGINT NOT NULL,
    summary_tokens BIGINT NOT NULL,
    compression_ratio NUMERIC(10,4) NOT NULL,
    model_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_summaries_session_created
    ON chat_summaries (session_id, created_at DESC);
CREATE INDEX idx_chat_summaries_end_message
    ON chat_summaries (end_message_id);


CREATE TABLE chat_provider_containers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    container_id TEXT NOT NULL,
    name TEXT NULL,
    status TEXT NULL,
    raw_container_object JSONB NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_chat_provider_containers_provider_container
    ON chat_provider_containers (provider, container_id);
CREATE INDEX idx_chat_provider_containers_session_provider
    ON chat_provider_containers (session_id, provider);
CREATE INDEX idx_chat_provider_containers_expires_at
    ON chat_provider_containers (expires_at);


CREATE TABLE chat_provider_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    file_upload_id UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_file_id TEXT NOT NULL,
    raw_file_object JSONB NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_chat_provider_files_provider_file
    ON chat_provider_files (provider, provider_file_id);
CREATE UNIQUE INDEX uq_chat_provider_files_upload_provider
    ON chat_provider_files (file_upload_id, provider);
CREATE INDEX idx_chat_provider_files_session_provider
    ON chat_provider_files (session_id, provider);


CREATE TABLE chat_provider_vector_stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NULL REFERENCES sessions(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'user',
    vector_store_id TEXT NOT NULL,
    raw_vector_object JSONB NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uq_chat_provider_vector_stores_user_provider_vector
    ON chat_provider_vector_stores (user_id, provider, vector_store_id);
CREATE INDEX idx_chat_provider_vector_stores_session
    ON chat_provider_vector_stores (session_id);
CREATE INDEX idx_chat_provider_vector_stores_expires_at
    ON chat_provider_vector_stores (expires_at);
```

## Agent

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
    origin_message_id UUID NULL,
    status TEXT NOT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_runs_session_created
    ON agent_runs (session_id, created_at DESC);
CREATE INDEX idx_agent_runs_parent
    ON agent_runs (parent_run_id);
CREATE INDEX idx_agent_runs_status_created
    ON agent_runs (status, created_at DESC);


CREATE TABLE agent_run_snapshots (
    run_id UUID PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL,
    run_input JSONB NULL,
    messages JSONB NULL,
    metrics JSONB NULL,
    additional_info JSONB NULL,
    tools JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_run_snapshots_session
    ON agent_run_snapshots (session_id, created_at DESC);
CREATE INDEX idx_agent_run_snapshots_parent
    ON agent_run_snapshots (parent_run_id);
CREATE INDEX idx_agent_run_snapshots_status
    ON agent_run_snapshots (status);


CREATE TABLE agent_event_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    event_group TEXT NOT NULL,
    event_name TEXT NOT NULL,
    payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_event_log_session_created
    ON agent_event_log (session_id, created_at DESC);
CREATE INDEX idx_agent_event_log_run_created
    ON agent_event_log (run_id, created_at DESC);
CREATE INDEX idx_agent_event_log_name_created
    ON agent_event_log (event_name, created_at DESC);


CREATE TABLE agent_ui_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id UUID NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_content JSONB NOT NULL,
    source TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_ui_events_session_created
    ON agent_ui_events (session_id, created_at DESC);
CREATE INDEX idx_agent_ui_events_run_created
    ON agent_ui_events (run_id, created_at DESC);
CREATE INDEX idx_agent_ui_events_type_created
    ON agent_ui_events (event_type, created_at DESC);


CREATE TABLE agent_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    topics JSONB NULL,
    metrics JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_summaries_session_created
    ON agent_summaries (session_id, created_at DESC);
CREATE INDEX idx_agent_summaries_run
    ON agent_summaries (run_id);


CREATE TABLE agent_sandboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_sandbox_id TEXT NULL,
    status TEXT NOT NULL,
    provider_data JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expired_at TIMESTAMPTZ NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uq_agent_sandboxes_session
    ON agent_sandboxes (session_id);
CREATE UNIQUE INDEX uq_agent_sandboxes_provider_sandbox
    ON agent_sandboxes (provider, provider_sandbox_id)
    WHERE provider_sandbox_id IS NOT NULL;
CREATE INDEX idx_agent_sandboxes_status
    ON agent_sandboxes (status);


CREATE TABLE agent_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 1,
    title TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    plan_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_agent_plans_run_revision
    ON agent_plans (run_id, revision);
CREATE INDEX idx_agent_plans_session_status
    ON agent_plans (session_id, status, created_at DESC);


CREATE TABLE agent_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    details JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_agent_milestones_plan_position
    ON agent_milestones (plan_id, position);
CREATE INDEX idx_agent_milestones_run_status
    ON agent_milestones (run_id, status, position);


CREATE TABLE agent_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    requirement_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NULL,
    resolved_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_requirements_run_status
    ON agent_requirements (run_id, status, created_at DESC);
```

## Files

```sql
CREATE TABLE file_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NULL REFERENCES sessions(id) ON DELETE SET NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    content_type TEXT NULL,
    storage_provider TEXT NOT NULL DEFAULT 'gcs',
    storage_path TEXT NOT NULL,
    checksum TEXT NULL,
    source_app_kind TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    CONSTRAINT ck_file_uploads_source_app_kind
        CHECK (source_app_kind IS NULL OR source_app_kind IN ('chat', 'agent'))
);

CREATE UNIQUE INDEX uq_file_uploads_storage_path
    ON file_uploads (storage_path);
CREATE INDEX idx_file_uploads_user_created
    ON file_uploads (user_id, created_at DESC);
CREATE INDEX idx_file_uploads_session_created
    ON file_uploads (session_id, created_at DESC);
CREATE INDEX idx_file_uploads_checksum
    ON file_uploads (checksum);
```

## Projects

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NULL REFERENCES sessions(id) ON DELETE SET NULL,
    name TEXT NULL,
    description TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    framework TEXT NULL,
    project_path TEXT NULL,
    production_url TEXT NULL,
    current_production_deployment_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_projects_session
    ON projects (session_id)
    WHERE session_id IS NOT NULL;
CREATE INDEX idx_projects_user_created
    ON projects (user_id, created_at DESC);
CREATE INDEX idx_projects_status
    ON projects (status, created_at DESC);


CREATE TABLE project_deployments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL,
    deployment_status TEXT NOT NULL,
    deployment_url TEXT NULL,
    provider TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_id TEXT NULL,
    source_path TEXT NULL,
    metadata JSONB NULL,
    error_phase TEXT NULL,
    error_message TEXT NULL,
    error_details JSONB NULL,
    started_at TIMESTAMPTZ NULL,
    deployed_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    deploy_duration_ms BIGINT NULL,
    upload_duration_ms BIGINT NULL,
    build_duration_ms BIGINT NULL,
    deployed_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_project_deployments_project_version
    ON project_deployments (project_id, version);
CREATE INDEX idx_project_deployments_project_environment
    ON project_deployments (project_id, environment, created_at DESC);
CREATE INDEX idx_project_deployments_project_status
    ON project_deployments (project_id, deployment_status, created_at DESC);


CREATE TABLE project_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    deployment_id UUID NULL REFERENCES project_deployments(id) ON DELETE SET NULL,
    domain_kind TEXT NOT NULL DEFAULT 'subdomain',
    subdomain TEXT NULL,
    full_domain TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    dns_status TEXT NOT NULL DEFAULT 'pending',
    ssl_status TEXT NOT NULL DEFAULT 'pending',
    provider_record_id TEXT NULL,
    claimed_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    claimed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_project_domains_full_domain_ci
    ON project_domains ((lower(full_domain)));
CREATE INDEX idx_project_domains_project
    ON project_domains (project_id, is_primary, created_at DESC);
CREATE INDEX idx_project_domains_deployment
    ON project_domains (deployment_id);


CREATE TABLE project_databases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL DEFAULT 'production',
    source TEXT NOT NULL,
    connection_string TEXT NOT NULL,
    host TEXT NULL,
    database_name TEXT NULL,
    role_name TEXT NULL,
    branch_name TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_databases_project_environment
    ON project_databases (project_id, environment, created_at DESC);
CREATE INDEX idx_project_databases_active
    ON project_databases (project_id, is_active);


CREATE TABLE project_secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL,
    secret_key TEXT NOT NULL,
    encrypted_value TEXT NULL,
    secret_ref TEXT NULL,
    created_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_project_secrets_project_env_key
    ON project_secrets (project_id, environment, secret_key);
CREATE INDEX idx_project_secrets_project_environment
    ON project_secrets (project_id, environment);


CREATE TABLE project_storage_resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL DEFAULT 'production',
    provider TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_identifier TEXT NOT NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_project_storage_resources_unique
    ON project_storage_resources (
        project_id, environment, provider, resource_type, resource_identifier
    );
CREATE INDEX idx_project_storage_resources_project_type
    ON project_storage_resources (project_id, resource_type, created_at DESC);
```

## Content

```sql
CREATE TABLE presentations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_presentations_session_created
    ON presentations (session_id, created_at DESC);


CREATE TABLE presentation_slides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    presentation_id UUID NOT NULL REFERENCES presentations(id) ON DELETE CASCADE,
    slide_number INTEGER NOT NULL,
    title TEXT NULL,
    content_html TEXT NOT NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_presentation_slides_number
    ON presentation_slides (presentation_id, slide_number);
CREATE INDEX idx_presentation_slides_presentation
    ON presentation_slides (presentation_id, slide_number);


CREATE TABLE presentation_slide_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    presentation_slide_id UUID NOT NULL REFERENCES presentation_slides(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    root_version_id UUID NULL REFERENCES presentation_slide_versions(id) ON DELETE SET NULL,
    parent_version_id UUID NULL REFERENCES presentation_slide_versions(id) ON DELETE SET NULL,
    image_url TEXT NOT NULL,
    thumbnail_url TEXT NULL,
    edit_summary TEXT NULL,
    instructions_applied JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_presentation_slide_versions_number
    ON presentation_slide_versions (presentation_slide_id, version);
CREATE INDEX idx_presentation_slide_versions_root
    ON presentation_slide_versions (root_version_id);
CREATE INDEX idx_presentation_slide_versions_parent
    ON presentation_slide_versions (parent_version_id);


CREATE TABLE slide_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    content_html TEXT NOT NULL,
    image_urls TEXT[] NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_slide_templates_name
    ON slide_templates (name);


CREATE TABLE storybooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aspect_ratio TEXT NOT NULL DEFAULT '1:1',
    resolution TEXT NOT NULL DEFAULT '1K',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_storybooks_session_created
    ON storybooks (session_id, created_at DESC);


CREATE TABLE storybook_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    storybook_id UUID NOT NULL REFERENCES storybooks(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    parent_version_id UUID NULL REFERENCES storybook_versions(id) ON DELETE SET NULL,
    style_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_storybook_versions_number
    ON storybook_versions (storybook_id, version);
CREATE INDEX idx_storybook_versions_parent
    ON storybook_versions (parent_version_id);


CREATE TABLE storybook_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_number INTEGER NOT NULL,
    image_url TEXT NULL,
    html_content TEXT NULL,
    text_content TEXT NULL,
    audio_url TEXT NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_storybook_pages_page_number
    ON storybook_pages (page_number);


CREATE TABLE storybook_version_pages (
    storybook_version_id UUID NOT NULL REFERENCES storybook_versions(id) ON DELETE CASCADE,
    page_id UUID NOT NULL REFERENCES storybook_pages(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (storybook_version_id, page_id)
);

CREATE UNIQUE INDEX uq_storybook_version_pages_position
    ON storybook_version_pages (storybook_version_id, position);
CREATE INDEX idx_storybook_version_pages_page
    ON storybook_version_pages (page_id);


CREATE TABLE media_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    preview_url TEXT NULL,
    template_type TEXT NULL,
    prompt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_media_templates_type_name
    ON media_templates (template_type, name);
```

## Skills

```sql
CREATE TABLE skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'builtin',
    source_url TEXT NULL,
    skill_md_content TEXT NOT NULL,
    sandbox_path TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    allowed_tools JSONB NULL DEFAULT '[]'::jsonb,
    license TEXT NULL,
    compatibility TEXT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_skills_user_name
    ON skills (user_id, name)
    WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_skills_builtin_name
    ON skills (name)
    WHERE user_id IS NULL;
CREATE INDEX idx_skills_source_enabled
    ON skills (source, is_enabled);
```

## Integrations

```sql
CREATE TABLE integration_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL,
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT NULL,
    token_expiry TIMESTAMPTZ NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_integration_connections_user_type
    ON integration_connections (user_id, integration_type);
CREATE INDEX idx_integration_connections_type
    ON integration_connections (integration_type);


CREATE TABLE composio_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name TEXT NOT NULL,
    toolkit_slug TEXT NOT NULL,
    toolkit_name TEXT NOT NULL,
    auth_config_id TEXT NOT NULL,
    connected_account_id TEXT NOT NULL,
    mcp_server_id TEXT NOT NULL,
    composio_user_id TEXT NOT NULL,
    encrypted_mcp_url TEXT NOT NULL,
    redirect_url TEXT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_tools JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_composio_profiles_user_name
    ON composio_profiles (user_id, profile_name);
CREATE INDEX idx_composio_profiles_user_toolkit
    ON composio_profiles (user_id, toolkit_slug);
CREATE INDEX idx_composio_profiles_status
    ON composio_profiles (status);
```

## Mobile

```sql
CREATE TABLE apple_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    apple_id TEXT NOT NULL,
    auth_state TEXT NOT NULL DEFAULT 'pending_login',
    encrypted_session_data TEXT NULL,
    selected_team_id TEXT NULL,
    team_name TEXT NULL,
    available_teams JSONB NULL,
    session_expiry TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_apple_accounts_user_apple_id
    ON apple_accounts (user_id, apple_id);
CREATE INDEX idx_apple_accounts_user_created
    ON apple_accounts (user_id, created_at DESC);


CREATE TABLE apple_build_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apple_account_id UUID NOT NULL REFERENCES apple_accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL DEFAULT 'ios',
    bundle_identifier TEXT NOT NULL,
    encrypted_expo_token TEXT NULL,
    encrypted_app_specific_password TEXT NULL,
    encrypted_p12 TEXT NULL,
    encrypted_p12_password TEXT NULL,
    encrypted_provisioning_profile TEXT NULL,
    certificate_id TEXT NULL,
    certificate_expires_at TIMESTAMPTZ NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_apple_build_credentials_account_bundle
    ON apple_build_credentials (apple_account_id, platform, bundle_identifier);
CREATE INDEX idx_apple_build_credentials_certificate_expiry
    ON apple_build_credentials (certificate_expires_at);
```

## System

```sql
CREATE TABLE system_configs (
    key TEXT PRIMARY KEY,
    value JSONB NULL,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_system_configs_is_secret
    ON system_configs (is_secret);
```

## Cross-Table Follow-Up Constraints

Some constraints are added after table creation because they are circular:

```sql
ALTER TABLE chat_runs
    ADD CONSTRAINT fk_chat_runs_user_message
    FOREIGN KEY (user_message_id) REFERENCES chat_messages(id) ON DELETE SET NULL;

ALTER TABLE chat_runs
    ADD CONSTRAINT fk_chat_runs_assistant_message
    FOREIGN KEY (assistant_message_id) REFERENCES chat_messages(id) ON DELETE SET NULL;

ALTER TABLE projects
    ADD CONSTRAINT fk_projects_current_production_deployment
    FOREIGN KEY (current_production_deployment_id)
    REFERENCES project_deployments(id) ON DELETE SET NULL;
```

## Notes

### `agent_ui_events` Is Optional

If the frontend can hydrate directly from `agent_event_log`, this table can be
removed.

### `usage_records.session_id` And `usage_records.run_id`

These are intentionally not hard foreign keys in this sketch because the row may
refer to either chat or agent usage, and `run_id` is polymorphic across
`chat_runs` and `agent_runs`.

If you want stronger integrity here, split the table into:

- `chat_usage_records`
- `agent_usage_records`

### `origin_message_id` On `agent_runs`

This is unconstrained in the sketch because the current agent model does not yet
have a clean, canonical agent input message table.
