# Final Database Design & Migration Plan

Date: 2026-03-11 (updated)

This document is the single authoritative reference for the II-Agent database
migration. It merges:

- A full audit of the current 36-table SQLAlchemy schema
- `SCHEMA_MIGRATION_GUIDE.md` (ideal-state architecture)
- `docs/design/migration-priority-guide.md` (implementation-level priorities)
- A comparative review of both guides to pick the best of each

Where the two source guides diverge, this file chooses one target shape and one
migration order. The reasoning is documented inline.

---

## Table of Contents

1. [Current State (36 Tables)](#1-current-state)
2. [Critical Problems](#2-critical-problems)
3. [Design Decisions](#3-design-decisions)
4. [Target Schema (All Tables & Columns)](#4-target-schema)
5. [Current-to-Target Mapping](#5-current-to-target-mapping)
6. [Migration Priority Order](#6-migration-priority-order)
7. [Step-by-Step Migration Guide](#7-step-by-step-migration-guide)
8. [Migration Rules](#8-migration-rules)

---

## 1. Current State

### Table Inventory (36 Tables)

```
Domain            Tables
────────────────  ──────────────────────────────────────────────────
auth              users, api_keys, waitlist
billing           billing_transactions, session_metrics, credit_ledger,
                  credit_balances, billing_customers
sessions          sessions, session_wishlists
chat              chat_messages, chat_summaries, chat_runs,
                  chat_provider_containers, chat_provider_files,
                  chat_provider_vector_stores
agent             agent_run_tasks, agent_run_messages, agent_event_log,
                  agent_summaries, agent_events, agent_sandboxes
files             file_uploads
projects          projects, project_deployments, project_databases,
                  project_custom_domains
content           slide_contents, slide_versions, slide_templates,
                  storybooks, storybook_pages, storybook_page_links,
                  media_templates, skills
settings          llm_settings, mcp_settings
integrations      connectors, composio_profiles
mobile            apple_credentials
core              application_configs
```

### Current Column Detail

#### `users`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| email | String | UNIQUE | |
| password_hash | String | nullable | |
| first_name | String | nullable | **MOVE** -> user_profiles |
| last_name | String | nullable | **MOVE** -> user_profiles |
| avatar | String | nullable | **MOVE** -> user_profiles |
| role | String | default "user" | |
| is_active | Boolean | default True | |
| email_verified | Boolean | default False | |
| login_provider | String | nullable | |
| organization | String | nullable | |
| language | String | default "en" | **MOVE** -> user_profiles |
| metadata | JSONB | nullable | **MOVE** -> user_profiles |
| stripe_customer_id | String | nullable | **DEPRECATE** -> billing_customers |
| subscription_plan | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_status | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_billing_cycle | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_current_period_end | TIMESTAMPTZ | nullable | **DEPRECATE** -> billing_subscriptions |
| credits | Float | default 0 | **DEPRECATE** -> credit_balances (Float->Numeric bug) |
| bonus_credits | Float | default 0 | **DEPRECATE** -> credit_balances (Float->Numeric bug) |
| last_login_at | TIMESTAMPTZ | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `api_keys`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| user_id | String | FK users.id CASCADE | |
| api_key | String | UNIQUE | **SECURITY: stores raw key** |
| is_active | Boolean | default True | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `waitlist`

| Column | Type | Constraints |
|--------|------|-------------|
| email | String | PK |
| created_at | TIMESTAMPTZ | server default |

#### `billing_transactions`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| stripe_event_id | String | UNIQUE |
| stripe_object_id | String | nullable |
| stripe_customer_id | String | nullable |
| stripe_subscription_id | String | nullable |
| stripe_invoice_id | String | nullable |
| stripe_payment_intent_id | String | nullable |
| amount | Numeric(18,6) | nullable |
| currency | String | nullable |
| plan_id | String | nullable |
| billing_cycle | String | nullable |
| credits | Numeric(18,6) | nullable |
| status | String | nullable |
| raw_payload | JSONB | nullable |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `billing_customers`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| user_id | String | FK users.id CASCADE | |
| provider | String | default "stripe" | |
| external_customer_id | String | | |
| subscription_plan | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_status | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_billing_cycle | String | nullable | **DEPRECATE** -> billing_subscriptions |
| subscription_current_period_end | TIMESTAMPTZ | nullable | **DEPRECATE** -> billing_subscriptions |
| customer_metadata | JSONB | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

Unique: (user_id, provider), (provider, external_customer_id)

#### `credit_ledger`

| Column | Type | Constraints |
|--------|------|-------------|
| id | BigInteger | PK (identity) |
| user_id | String | FK users.id CASCADE |
| entry_type | String | NOT NULL |
| source_domain | String | nullable |
| source_id | String | nullable |
| idempotency_key | String | nullable, unique partial index |
| delta_credits | Numeric(18,6) | NOT NULL |
| delta_bonus_credits | Numeric(18,6) | default 0 |
| balance_after_credits | Numeric(18,6) | nullable |
| balance_after_bonus_credits | Numeric(18,6) | nullable |
| entry_metadata | JSONB | nullable |
| created_at | TIMESTAMPTZ | server default |

#### `credit_balances`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE, UNIQUE |
| credits | Numeric(18,6) | default 0, CHECK >= 0 |
| bonus_credits | Numeric(18,6) | default 0, CHECK >= 0 |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `session_metrics`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | **DEPRECATE** -> usage_records |
| session_id | String | FK sessions.id CASCADE, UNIQUE | |
| credits | Numeric(18,6) | default 0 | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `sessions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| user_id | String | FK users.id CASCADE | |
| sandbox_id | String | nullable | **DEPRECATE** (redundant with agent_sandboxes) |
| version | BigInteger | default 0 | Optimistic locking |
| llm_setting_id | String | FK llm_settings.id, nullable | **REPLACE** with llm_profile_id |
| name | String | nullable | |
| status | String | default "active" | |
| agent_state_path | String | nullable | **DEPRECATE** -> agent domain |
| agent_type | String | nullable | **DEPRECATE** -> session_metadata |
| app_kind | String | default "agent" | |
| public_url | String | nullable | **DEPRECATE** -> session_shares |
| is_public | Boolean | default False | **DEPRECATE** -> session_shares |
| api_version | String | default "v0" | **DEPRECATE** |
| parent_session_id | String | FK sessions.id, nullable | |
| session_metadata | JSONB | nullable | |
| last_message_at | TIMESTAMPTZ | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |
| deleted_at | TIMESTAMPTZ | nullable | Soft delete |

#### `session_wishlists`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| session_id | String | FK sessions.id CASCADE |
| created_at | TIMESTAMPTZ | server default |

Unique: (user_id, session_id)

#### `chat_messages`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| session_id | String | **NO FK** | **Missing FK** |
| role | String | | |
| content | JSONB | | |
| usage | JSONB | nullable | |
| tokens | BigInteger | nullable | |
| model | String | nullable | |
| tools | JSONB | nullable | |
| metadata | JSONB | nullable | |
| provider_metadata | JSONB | nullable | |
| file_ids | UUID[] | nullable | **Should use join table** |
| parent_message_id | UUID | nullable | **Missing self-FK** |
| is_finished | Boolean | default True | |
| finish_reason | String | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `chat_summaries`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| session_id | String | FK sessions.id CASCADE |
| summary_text | Text | |
| end_message_id | UUID | |
| original_tokens | BigInteger | |
| summary_tokens | BigInteger | |
| compression_ratio | Float | |
| model_id | String | |
| parent_summary_id | String | FK chat_summaries.id, nullable |
| created_at | TIMESTAMPTZ | server default |

#### `chat_runs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| session_id | String | FK sessions.id CASCADE | |
| user_message_id | UUID | nullable | |
| status | String | default "running" | |
| error_message | String | nullable | |
| version | BigInteger | default 0 | Optimistic locking |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |
| | | | **Missing:** model_id, provider, usage, cost_usd, timing |

#### `chat_provider_containers`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| session_id | String | **NO FK** | **Missing FK** |
| provider | String | | |
| container_id | String | | |
| name | String | nullable | |
| expires_at | TIMESTAMPTZ | nullable | |
| raw_container_object | JSONB | nullable | |
| status | String | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

Unique: (container_id, provider)

#### `chat_provider_files`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| file_id | String | | **Missing FK** |
| session_id | String | **NO FK** | **Missing FK** |
| provider | String | | |
| provider_file_id | String | | |
| raw_file_object | JSONB | nullable | |
| expires_at | TIMESTAMPTZ | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

Unique: (provider_file_id, provider)

#### `chat_provider_vector_stores`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| user_id | String | **NO FK** | **Missing FK** |
| provider | String | | |
| vector_store_id | String | | |
| version | BigInteger | default 0 | Optimistic locking |
| raw_vector_object | JSONB | nullable | |
| expires_at | TIMESTAMPTZ | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

Unique: (user_id, provider, vector_store_id)

#### `agent_run_tasks`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| session_id | String | FK sessions.id CASCADE |
| user_message_id | UUID | nullable |
| status | String | default "running" |
| error_message | String | nullable |
| version | BigInteger | default 0 (optimistic locking) |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `agent_run_messages`

| Column | Type | Constraints |
|--------|------|-------------|
| id | BigInteger | PK (autoincrement) |
| session_id | String | FK sessions.id CASCADE |
| run_id | UUID | FK agent_run_tasks.id CASCADE |
| parent_run_id | UUID | nullable |
| model_id | String | NOT NULL |
| status | String | default "running" |
| run_input | JSONB | nullable |
| messages | JSONB | nullable |
| metrics | JSONB | nullable |
| additional_info | JSONB | nullable |
| tools | JSONB | nullable |
| version | BigInteger | default 0 (optimistic locking) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | onupdate |

#### `agent_event_log`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| session_id | String | **NO FK** | **Missing FK** |
| run_id | UUID | **NO FK** | **Missing FK** |
| group | String | NOT NULL | |
| name | String | NOT NULL | RunEvent enum |
| payload | JSONB | nullable | |
| created_at | TIMESTAMPTZ | | |

#### `agent_summaries`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | BigInteger | PK (autoincrement) | |
| content | String | NOT NULL | |
| topics | JSONB | nullable | |
| metrics | JSONB | nullable | |
| session_id | String | **NO FK** | **Missing FK** |
| agent_run_id | BigInteger | default 0 | |
| version | BigInteger | default 0 | Optimistic locking |
| created_at | TIMESTAMPTZ | | |
| updated_at | TIMESTAMPTZ | onupdate | |

#### `agent_events`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| session_id | String | FK sessions.id CASCADE |
| run_id | UUID | nullable |
| type | String | EventType enum |
| content | JSONB | |
| source | String | nullable |
| created_at | TIMESTAMPTZ | server default |

#### `agent_sandboxes`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| provider | String | default "e2b" | |
| provider_sandbox_id | String | nullable | |
| provider_data | JSONB | nullable | |
| session_id | UUID/String | **NO FK**, unique | **Missing FK** |
| status | String | default "not_initialized" | |
| version | Integer | default 0 | Optimistic locking |
| created_at | TIMESTAMPTZ | server default | |
| expired_at | TIMESTAMPTZ | nullable | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `file_uploads`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| file_name | String | |
| file_size | BigInteger | |
| storage_path | String | |
| content_type | String | nullable |
| session_id | String | FK sessions.id CASCADE, nullable |
| created_at | TIMESTAMPTZ | server default |

#### `projects`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| user_id | String | FK users.id CASCADE | |
| session_id | String | FK sessions.id SET NULL, nullable, UNIQUE | |
| name | String | nullable | |
| description | Text | nullable | |
| status | String | default "active" | |
| current_build_status | String | default "pending" | **DEPRECATE** |
| framework | String | nullable | |
| project_path | String | nullable | |
| production_url | String | nullable | |
| database_json | JSONB | nullable | **DEPRECATE** -> project_databases |
| storage_json | JSONB | nullable | **DEPRECATE** -> project_storage_configs |
| secrets_json | JSONB | nullable | **DEPRECATE** -> project_secrets |
| current_production_deployment_id | String | FK project_deployments.id SET NULL | |
| custom_domain_id | String | FK project_custom_domains.id SET NULL | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |
| deleted_at | TIMESTAMPTZ | nullable | Soft delete |

#### `project_deployments`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| project_id | String | FK projects.id CASCADE |
| environment | String | |
| deployment_status | String | default "pending" |
| deployment_url | String | nullable |
| started_at | TIMESTAMPTZ | nullable |
| deployed_at | TIMESTAMPTZ | nullable |
| finished_at | TIMESTAMPTZ | nullable |
| deploy_duration_ms | BigInteger | nullable |
| error_message | Text | nullable |
| deployed_by_user_id | String | FK users.id SET NULL, nullable |
| provider | String | default "cloud_run" |
| version | Integer | default 1 |
| snapshot_id | String | nullable |
| source_path | String | nullable |
| metadata | JSONB | nullable |
| error_phase | String | nullable |
| error_details | JSONB | nullable |
| upload_duration_ms | BigInteger | nullable |
| build_duration_ms | BigInteger | nullable |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `project_databases`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| session_id | String | FK sessions.id CASCADE | **REKEY** -> project_id |
| source | String | default "neondb" | |
| connection_string | String | | |
| host | String | nullable | |
| database_name | String | nullable | |
| role_name | String | nullable | |
| branch_name | String | nullable | |
| is_active | Boolean | default True | |
| metadata | JSONB | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `project_custom_domains`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| project_id | String | FK projects.id CASCADE, UNIQUE |
| subdomain | String(63) | UNIQUE |
| full_domain | String(255) | |
| deployment_id | String | FK project_deployments.id SET NULL, nullable |
| dns_status | String | default "pending" |
| ssl_status | String | default "pending" |
| cloudflare_record_id | String(100) | nullable |
| claimed_at | TIMESTAMPTZ | nullable |
| claimed_by_user_id | String | FK users.id SET NULL, nullable |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `llm_settings`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | **SPLIT** into credentials + profiles |
| user_id | String | FK users.id CASCADE | |
| model | String | | -> llm_profiles |
| api_type | String | | -> llm_provider_credentials |
| encrypted_api_key | String | nullable | -> llm_provider_credentials |
| base_url | String | nullable | -> llm_provider_credentials |
| max_retries | BigInteger | default 10 | -> llm_profiles |
| max_message_chars | BigInteger | default 30000 | -> llm_profiles |
| temperature | Float | default 1.0 | -> llm_profiles |
| thinking_tokens | BigInteger | nullable | -> llm_profiles |
| is_active | Boolean | default True | |
| metadata | JSONB | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

#### `mcp_settings`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| mcp_config | JSONB | |
| metadata | JSONB | nullable |
| is_active | Boolean | default True |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

#### `connectors`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | String (UUID) | PK | |
| user_id | String | FK users.id CASCADE | |
| connector_type | String | | |
| access_token | String | | **SECURITY: plaintext** |
| refresh_token | String | nullable | **SECURITY: plaintext** |
| token_expiry | TIMESTAMPTZ | nullable | |
| metadata | JSONB | nullable | |
| created_at | TIMESTAMPTZ | server default | |
| updated_at | TIMESTAMPTZ | server default, onupdate | |

Unique: (user_id, connector_type)

#### `composio_profiles`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| profile_name | String | |
| toolkit_slug | String | |
| toolkit_name | String | |
| auth_config_id | String | |
| connected_account_id | String | |
| mcp_server_id | String | |
| composio_user_id | String | |
| encrypted_mcp_url | String | |
| redirect_url | String | nullable |
| status | String | default "pending" |
| is_default | Boolean | default False |
| enabled_tools | JSONB | default [] |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

Unique: (user_id, profile_name)

#### `apple_credentials`

| Column | Type | Constraints |
|--------|------|-------------|
| id | String (UUID) | PK |
| user_id | String | FK users.id CASCADE |
| apple_id | String | |
| auth_state | String | default "pending_login" |
| encrypted_session_data | Text | nullable |
| selected_team_id | String | nullable |
| team_name | String | nullable |
| available_teams | JSONB | nullable |
| session_expiry | TIMESTAMPTZ | nullable |
| encrypted_expo_token | Text | nullable |
| encrypted_app_specific_password | Text | nullable |
| encrypted_ios_p12 | Text | nullable |
| encrypted_ios_p12_password | Text | nullable |
| encrypted_ios_provisioning_profile | Text | nullable |
| ios_bundle_identifier | String | nullable |
| ios_certificate_expiry | TIMESTAMPTZ | nullable |
| ios_certificate_id | String | nullable |
| created_at | TIMESTAMPTZ | server default |
| updated_at | TIMESTAMPTZ | server default, onupdate |

Unique: (user_id, apple_id)

#### `application_configs`

| Column | Type | Constraints |
|--------|------|-------------|
| id | BigInteger | PK (autoincrement) |
| key | String | UNIQUE (ConfigKey enum) |
| value | JSONB | nullable |
| is_secret | Boolean | default False |
| version | BigInteger | default 0 |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | onupdate |

#### Content Tables

`slide_contents`, `slide_versions`, `slide_templates`, `storybooks`,
`storybook_pages`, `storybook_page_links`, `media_templates`, `skills` —
structurally sound, lowest priority for migration. Key issues:
- `slide_versions.image_url` and `storybook_pages.image_url` should eventually
  reference an `assets` table
- `storybook_page_links` lacks explicit ordering

---

## 2. Critical Problems

### P0: Data Correctness Bugs

| # | Problem | Impact |
|---|---------|--------|
| P0-1 | Storybook/voice billing has no idempotency keys in 3 entry points | Double-charging on Celery retry |
| P0-2 | `users.credits` / `users.bonus_credits` are Float, not Numeric | Floating-point drift vs credit_balances |
| P0-3 | Subscription state duplicated across `users`, `billing_customers`, `billing_transactions` | No single source of truth |

### P1: Missing Foreign Keys (11 total)

| Table | Column | Should Reference |
|-------|--------|-----------------|
| chat_messages | session_id | sessions.id |
| chat_messages | parent_message_id | chat_messages.id |
| chat_provider_containers | session_id | sessions.id |
| chat_provider_files | session_id | sessions.id |
| chat_provider_files | file_id | file_uploads.id |
| chat_provider_vector_stores | user_id | users.id |
| agent_sandboxes | session_id | sessions.id |
| agent_event_log | session_id | sessions.id |
| agent_event_log | run_id | agent_run_tasks.id |
| agent_summaries | session_id | sessions.id |
| project_databases | session_id | should be projects.id |

### P2: Missing Analytics Data

- No `usage_records` table — per-charge detail only in JSONB
- `session_metrics` only stores one aggregate credit number
- `chat_runs` missing model_id, provider, usage, cost_usd, timing

### P3: Structural Overloading

- `users` carries identity + profile + billing + preferences
- `projects` embeds database_json, storage_json, secrets_json
- `project_databases` FK points to sessions.id instead of projects.id
- `llm_settings` mixes credential storage with model config

### P4: Security Gaps

- `api_keys.api_key` stores raw key (not hashed)
- `connectors.access_token` / `connectors.refresh_token` are plaintext

---

## 3. Design Decisions

### Chosen principles

- One canonical owner per business concept.
- UUID primary keys for root entities.
- BIGINT identity keys for append-heavy facts and logs.
- `NUMERIC(18,6)` for all money and credits, never Float.
- `TIMESTAMPTZ` everywhere.
- JSONB for provider payloads and flexible metadata, not for primary query paths.

### Key architectural choices

**Billing split: webhook_events + invoices (not a single billing_events).**
Webhooks are raw infrastructure; invoices are business objects. Different
lifecycle, different query patterns. This is stricter than a single
`billing_events` table.

**Project environments as a first-class table with FK.**
`project_environments` sits between `projects` and
databases/secrets/storage. An `environment_id` FK is more correct than a
flat `environment TEXT` column for multi-environment support.

**Unified runtime core (incremental).**
The repo currently duplicates execution concepts in two shapes:
`chat_runs` / `agent_run_tasks`, `chat_messages` / `agent_run_messages`,
`agent_events` / `agent_event_log`. The end state converges on shared
tables (`app_runs`, `messages`, `message_parts`, etc.), but the migration
is phased:
- Phase A: `llm_invocations` + `tool_invocations` (dual-write, no read cutover)
- Phase B: `app_runs` + `messages` + `message_parts` (dual-write)
- Phase C: `event_log` + `session_summaries` (dual-write)
- Phase D: Read cutover + deprecation

**Security early.** API key hashing and connector token encryption are
small, independent changes that don't depend on structural migrations.
They run in parallel with P0/P1.

**`sessions.project_id` replaces `projects.session_id`.**
Add `sessions.project_id` early (P3), deprecate reads from
`projects.session_id` at the same time, don't wait until the final cleanup.

**`usage_records` is a standalone early win.**
It's the single highest-value new table for product analytics and ships
independently from the billing restructuring.

---

## 4. Target Schema

### Naming Conventions

- `NUMERIC(18,6)` for all money/credit values
- `UUID` primary keys for root tables
- `BIGINT GENERATED ALWAYS AS IDENTITY` for append-heavy tables
- `TIMESTAMPTZ` for all timestamps
- `JSONB` only for genuinely schemaless data

### 4.1 Identity Domain

#### `users` (MODIFY — slim down)

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    password_hash   TEXT,
    role            TEXT NOT NULL DEFAULT 'user',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    login_provider  TEXT,
    organization    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_users_email_ci ON users ((lower(email)));
```

#### `user_profiles` (NEW)

```sql
CREATE TABLE user_profiles (
    user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_name        TEXT,
    last_name         TEXT,
    avatar_url        TEXT,
    language          TEXT NOT NULL DEFAULT 'en',
    profile_metadata  JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `user_api_keys` (RENAME + security fix)

```sql
CREATE TABLE user_api_keys (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT,
    key_hash      TEXT NOT NULL,
    key_prefix    TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at  TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_user_api_keys_key_hash ON user_api_keys (key_hash);
```

#### `waitlist_entries` (RENAME)

```sql
CREATE TABLE waitlist_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_waitlist_entries_email_ci ON waitlist_entries ((lower(email)));
```

### 4.2 Billing Domain

#### `billing_customers` (MODIFY — remove subscription columns)

```sql
CREATE TABLE billing_customers (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider              TEXT NOT NULL DEFAULT 'stripe',
    external_customer_id  TEXT NOT NULL,
    customer_metadata     JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_billing_customers_user_provider
    ON billing_customers (user_id, provider);
CREATE UNIQUE INDEX uq_billing_customers_provider_external
    ON billing_customers (provider, external_customer_id);
```

#### `billing_subscriptions` (NEW)

```sql
CREATE TABLE billing_subscriptions (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_customer_id       UUID NOT NULL REFERENCES billing_customers(id) ON DELETE CASCADE,
    provider                  TEXT NOT NULL,
    external_subscription_id  TEXT NOT NULL,
    plan_code                 TEXT NOT NULL,
    billing_interval          TEXT,
    status                    TEXT NOT NULL,
    current_period_start      TIMESTAMPTZ,
    current_period_end        TIMESTAMPTZ,
    trial_end                 TIMESTAMPTZ,
    cancel_at                 TIMESTAMPTZ,
    canceled_at               TIMESTAMPTZ,
    ended_at                  TIMESTAMPTZ,
    raw_payload               JSONB,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_billing_subscriptions_provider_external
    ON billing_subscriptions (provider, external_subscription_id);
```

#### `billing_invoices` (NEW)

```sql
CREATE TABLE billing_invoices (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_customer_id       UUID NOT NULL REFERENCES billing_customers(id) ON DELETE CASCADE,
    billing_subscription_id   UUID REFERENCES billing_subscriptions(id) ON DELETE SET NULL,
    provider                  TEXT NOT NULL,
    external_invoice_id       TEXT NOT NULL,
    amount_due                NUMERIC(18,6),
    amount_paid               NUMERIC(18,6),
    currency                  TEXT,
    status                    TEXT NOT NULL,
    period_start              TIMESTAMPTZ,
    period_end                TIMESTAMPTZ,
    issued_at                 TIMESTAMPTZ,
    paid_at                   TIMESTAMPTZ,
    raw_payload               JSONB,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_billing_invoices_provider_external
    ON billing_invoices (provider, external_invoice_id);
```

#### `billing_webhook_events` (NEW — replaces billing_transactions)

```sql
CREATE TABLE billing_webhook_events (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider            TEXT NOT NULL,
    external_event_id   TEXT NOT NULL,
    external_object_id  TEXT,
    event_type          TEXT NOT NULL,
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    processing_status   TEXT NOT NULL DEFAULT 'pending',
    payload             JSONB NOT NULL,
    processed_at        TIMESTAMPTZ,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_billing_webhook_events_provider_event
    ON billing_webhook_events (provider, external_event_id);
```

#### `credit_ledger` (KEEP)

```sql
-- No changes. Already correct.
```

#### `credit_balances` (KEEP)

```sql
-- No changes. Already correct.
```

#### `usage_records` (NEW — replaces session_metrics)

```sql
CREATE TABLE usage_records (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id          UUID,
    project_id          UUID,
    run_id              UUID,
    ledger_entry_id     BIGINT REFERENCES credit_ledger(id),
    source_domain       TEXT NOT NULL,
    app_kind            TEXT,
    model_id            TEXT,
    provider            TEXT,
    input_tokens        BIGINT NOT NULL DEFAULT 0,
    output_tokens       BIGINT NOT NULL DEFAULT 0,
    cache_read_tokens   BIGINT NOT NULL DEFAULT 0,
    cache_write_tokens  BIGINT NOT NULL DEFAULT 0,
    reasoning_tokens    BIGINT NOT NULL DEFAULT 0,
    latency_ms          BIGINT,
    cost_usd            NUMERIC(18,6),
    credits_charged     NUMERIC(18,6),
    usage_metadata      JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_records_user_created ON usage_records (user_id, created_at DESC);
CREATE INDEX idx_usage_records_session ON usage_records (session_id, created_at DESC);
CREATE INDEX idx_usage_records_model ON usage_records (model_id, created_at DESC);
CREATE INDEX idx_usage_records_source ON usage_records (source_domain, created_at DESC);
```

### 4.3 Sessions Domain

#### `sessions` (MODIFY — slim down)

```sql
CREATE TABLE sessions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id         UUID REFERENCES projects(id) ON DELETE SET NULL,
    app_kind           TEXT NOT NULL,
    name               TEXT,
    status             TEXT NOT NULL DEFAULT 'active',
    llm_profile_id     UUID REFERENCES llm_profiles(id) ON DELETE SET NULL,
    parent_session_id  UUID REFERENCES sessions(id) ON DELETE SET NULL,
    session_metadata   JSONB,
    last_message_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ
);
CREATE INDEX idx_sessions_user_created ON sessions (user_id, created_at DESC);
CREATE INDEX idx_sessions_not_deleted ON sessions (user_id, deleted_at, created_at DESC);
CREATE INDEX idx_sessions_project ON sessions (project_id) WHERE project_id IS NOT NULL;
```

#### `session_shares` (NEW)

```sql
CREATE TABLE session_shares (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    visibility   TEXT NOT NULL DEFAULT 'private',
    share_token  TEXT,
    public_url   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_session_shares_session ON session_shares (session_id);
CREATE UNIQUE INDEX uq_session_shares_token ON session_shares (share_token)
    WHERE share_token IS NOT NULL;
```

#### `session_bookmarks` (RENAME from session_wishlists)

```sql
CREATE TABLE session_bookmarks (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, session_id)
);
```

### 4.4 Projects & Runtime Resources

#### `projects` (MODIFY — remove JSON blobs)

```sql
CREATE TABLE projects (
    id                                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                              TEXT,
    description                       TEXT,
    status                            TEXT NOT NULL DEFAULT 'active',
    framework                         TEXT,
    project_path                      TEXT,
    production_url                    TEXT,
    current_production_deployment_id  UUID,
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at                        TIMESTAMPTZ
);
```

#### `project_environments` (NEW)

```sql
CREATE TABLE project_environments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_project_environments_project_name
    ON project_environments (project_id, name);
```

#### `project_databases` (MODIFY — rekey to project/environment)

```sql
CREATE TABLE project_databases (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id    UUID NOT NULL REFERENCES project_environments(id) ON DELETE CASCADE,
    source            TEXT NOT NULL,
    connection_string TEXT NOT NULL,
    host              TEXT,
    database_name     TEXT,
    role_name         TEXT,
    branch_name       TEXT,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    db_metadata       JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `project_secrets` (NEW)

```sql
CREATE TABLE project_secrets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id      UUID NOT NULL REFERENCES project_environments(id) ON DELETE CASCADE,
    key                 TEXT NOT NULL,
    secret_ref          TEXT NOT NULL,
    source              TEXT NOT NULL,
    is_required         BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_project_secrets_project_env_key
    ON project_secrets (project_id, environment_id, key);
```

#### `project_storage_configs` (NEW)

```sql
CREATE TABLE project_storage_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id  UUID NOT NULL REFERENCES project_environments(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    bucket          TEXT NOT NULL,
    base_path       TEXT,
    config_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `project_deployments` (MODIFY — add environment_id)

```sql
CREATE TABLE project_deployments (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id        UUID NOT NULL REFERENCES project_environments(id) ON DELETE CASCADE,
    provider              TEXT NOT NULL,
    version               INTEGER NOT NULL,
    snapshot_id           TEXT,
    source_path           TEXT,
    deployment_status     TEXT NOT NULL DEFAULT 'pending',
    deployment_url        TEXT,
    started_at            TIMESTAMPTZ,
    deployed_at           TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ,
    deploy_duration_ms    BIGINT,
    upload_duration_ms    BIGINT,
    build_duration_ms     BIGINT,
    error_phase           TEXT,
    error_code            TEXT,
    error_message         TEXT,
    error_details         JSONB,
    deploy_metadata       JSONB,
    deployed_by_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_project_deployments_project_version
    ON project_deployments (project_id, version);
```

#### `deployment_steps` (NEW)

```sql
CREATE TABLE deployment_steps (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id   UUID NOT NULL REFERENCES project_deployments(id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL,
    sequence        INTEGER NOT NULL,
    status          TEXT NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    error_code      TEXT,
    error_message   TEXT,
    payload         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_deployment_steps_deployment_sequence
    ON deployment_steps (deployment_id, sequence);
```

#### `project_domains` (RENAME from project_custom_domains)

```sql
CREATE TABLE project_domains (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    deployment_id       UUID REFERENCES project_deployments(id) ON DELETE SET NULL,
    subdomain           TEXT NOT NULL,
    full_domain         TEXT NOT NULL,
    dns_status          TEXT NOT NULL DEFAULT 'pending',
    ssl_status          TEXT NOT NULL DEFAULT 'pending',
    provider_record_id  TEXT,
    claimed_at          TIMESTAMPTZ,
    claimed_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_project_domains_project ON project_domains (project_id);
CREATE UNIQUE INDEX uq_project_domains_subdomain ON project_domains (subdomain);
```

### 4.5 Runtime Core (Unified)

#### `app_runs` (NEW — replaces chat_runs + agent_run_tasks)

```sql
CREATE TABLE app_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id          UUID REFERENCES projects(id) ON DELETE SET NULL,
    app_kind            TEXT NOT NULL,
    run_kind            TEXT NOT NULL,
    parent_run_id       UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    trigger_message_id  UUID,
    status              TEXT NOT NULL,
    error_code          TEXT,
    error_message       TEXT,
    request_metadata    JSONB,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    version             BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX idx_app_runs_session_created ON app_runs (session_id, created_at DESC);
CREATE INDEX idx_app_runs_status ON app_runs (status);
```

#### `run_steps` (NEW)

```sql
CREATE TABLE run_steps (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        UUID NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    step_type     TEXT NOT NULL,
    step_name     TEXT NOT NULL,
    sequence      INTEGER NOT NULL,
    status        TEXT NOT NULL,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    latency_ms    BIGINT,
    message_id    UUID,
    payload       JSONB,
    error_code    TEXT,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_run_steps_run_sequence ON run_steps (run_id, sequence);
```

#### `messages` (NEW — replaces chat_messages + agent_run_messages transcript)

```sql
CREATE TABLE messages (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id         UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id             UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    parent_message_id  UUID REFERENCES messages(id) ON DELETE SET NULL,
    role               TEXT NOT NULL,
    model_id           TEXT,
    is_finished        BOOLEAN NOT NULL DEFAULT TRUE,
    finish_reason      TEXT,
    tokens_total       BIGINT,
    message_metadata   JSONB,
    provider_metadata  JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_session_created ON messages (session_id, created_at ASC);
CREATE INDEX idx_messages_run ON messages (run_id);
```

#### `message_parts` (NEW)

```sql
CREATE TABLE message_parts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id   UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    part_type    TEXT NOT NULL,
    text_content TEXT,
    data_json    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_message_parts_message_ordinal ON message_parts (message_id, ordinal);
```

#### `message_attachments` (NEW)

```sql
CREATE TABLE message_attachments (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id       UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    asset_id         UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    attachment_role  TEXT NOT NULL,
    ordinal          INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `llm_invocations` (NEW)

```sql
CREATE TABLE llm_invocations (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    step_id             BIGINT REFERENCES run_steps(id) ON DELETE SET NULL,
    message_id          UUID,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    request_kind        TEXT NOT NULL,
    prompt_tokens       BIGINT NOT NULL DEFAULT 0,
    completion_tokens   BIGINT NOT NULL DEFAULT 0,
    cache_read_tokens   BIGINT NOT NULL DEFAULT 0,
    cache_write_tokens  BIGINT NOT NULL DEFAULT 0,
    reasoning_tokens    BIGINT NOT NULL DEFAULT 0,
    latency_ms          BIGINT,
    cost_usd            NUMERIC(18,6),
    credits_charged     NUMERIC(18,6),
    success             BOOLEAN NOT NULL DEFAULT TRUE,
    error_code          TEXT,
    request_payload     JSONB,
    response_payload    JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_llm_invocations_run ON llm_invocations (run_id, created_at);
CREATE INDEX idx_llm_invocations_model ON llm_invocations (model, created_at DESC);
```

#### `tool_invocations` (NEW)

```sql
CREATE TABLE tool_invocations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    step_id         BIGINT REFERENCES run_steps(id) ON DELETE SET NULL,
    message_id      UUID,
    tool_name       TEXT NOT NULL,
    tool_namespace  TEXT,
    status          TEXT NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    latency_ms      BIGINT,
    input_payload   JSONB,
    output_payload  JSONB,
    error_code      TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tool_invocations_run ON tool_invocations (run_id, created_at);
CREATE INDEX idx_tool_invocations_tool ON tool_invocations (tool_name, created_at DESC);
```

#### `event_log` (NEW — replaces agent_events + agent_event_log)

```sql
CREATE TABLE event_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id      UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    step_id     BIGINT REFERENCES run_steps(id) ON DELETE SET NULL,
    scope       TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_event_log_session ON event_log (session_id, created_at);
CREATE INDEX idx_event_log_run ON event_log (run_id, created_at);
```

#### `session_summaries` (NEW — replaces chat_summaries + agent_summaries)

```sql
CREATE TABLE session_summaries (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id              UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    summary_type        TEXT NOT NULL,
    parent_summary_id   BIGINT REFERENCES session_summaries(id) ON DELETE SET NULL,
    end_message_id      UUID,
    content             TEXT NOT NULL,
    topics              JSONB,
    metrics             JSONB,
    original_tokens     BIGINT,
    summary_tokens      BIGINT,
    compression_ratio   NUMERIC(8,4),
    model_id            TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_session_summaries_session ON session_summaries (session_id, created_at);
```

### 4.6 Agent-Specific Runtime State

#### `agent_run_snapshots` (RENAME from agent_run_messages, PK change)

```sql
CREATE TABLE agent_run_snapshots (
    run_id          UUID PRIMARY KEY REFERENCES app_runs(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_run_id   UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    model_id        TEXT NOT NULL,
    status          TEXT NOT NULL,
    run_input       JSONB,
    messages_json   JSONB,
    metrics         JSONB,
    additional_info JSONB,
    tools           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    version         BIGINT NOT NULL DEFAULT 0
);
```

#### `agent_plans` (NEW)

```sql
CREATE TABLE agent_plans (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    revision    BIGINT NOT NULL DEFAULT 1,
    title       TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    plan_json   JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_agent_plans_run_revision ON agent_plans (run_id, revision);
```

#### `agent_milestones` (NEW)

```sql
CREATE TABLE agent_milestones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id     UUID NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE,
    run_id      UUID NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    status      TEXT NOT NULL,
    title       TEXT NOT NULL,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_agent_milestones_plan_position ON agent_milestones (plan_id, position);
```

#### `agent_sandboxes` (MODIFY — add real FK)

```sql
CREATE TABLE agent_sandboxes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id              UUID REFERENCES app_runs(id) ON DELETE SET NULL,
    provider            TEXT NOT NULL,
    provider_sandbox_id TEXT,
    provider_data       JSONB,
    status              TEXT NOT NULL,
    version             INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expired_at          TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_agent_sandboxes_session ON agent_sandboxes (session_id);
```

### 4.7 Settings Domain

#### `llm_provider_credentials` (NEW — split from llm_settings)

```sql
CREATE TABLE llm_provider_credentials (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider              TEXT NOT NULL,
    credential_name       TEXT NOT NULL,
    api_type              TEXT NOT NULL,
    encrypted_api_key     TEXT,
    base_url              TEXT,
    credential_metadata   JSONB,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_llm_creds_user_provider_name
    ON llm_provider_credentials (user_id, provider, credential_name);
```

#### `llm_profiles` (NEW — split from llm_settings)

```sql
CREATE TABLE llm_profiles (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES users(id) ON DELETE CASCADE,
    credential_id     UUID REFERENCES llm_provider_credentials(id) ON DELETE SET NULL,
    name              TEXT NOT NULL,
    model             TEXT NOT NULL,
    temperature       NUMERIC(6,3) NOT NULL DEFAULT 1.000,
    thinking_tokens   BIGINT,
    max_retries       INTEGER NOT NULL DEFAULT 10,
    max_message_chars INTEGER NOT NULL DEFAULT 30000,
    is_default        BOOLEAN NOT NULL DEFAULT FALSE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    profile_metadata  JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `mcp_server_configs` (RENAME from mcp_settings)

```sql
CREATE TABLE mcp_server_configs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    config_json      JSONB NOT NULL,
    config_metadata  JSONB,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_mcp_server_configs_user_name ON mcp_server_configs (user_id, name);
```

### 4.8 Assets & Files

#### `assets` (NEW)

```sql
CREATE TABLE assets (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    project_id        UUID,
    session_id        UUID,
    source_kind       TEXT NOT NULL,
    media_kind        TEXT NOT NULL,
    storage_provider  TEXT NOT NULL,
    bucket            TEXT,
    object_path       TEXT NOT NULL,
    public_url        TEXT,
    mime_type         TEXT,
    size_bytes        BIGINT,
    checksum          TEXT,
    provider_asset_id TEXT,
    asset_metadata    JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_assets_user ON assets (owner_user_id);
CREATE INDEX idx_assets_session ON assets (session_id);
```

#### `file_uploads` (KEEP temporarily — replaced by assets long-term)

No immediate changes.

### 4.9 Integrations Domain

#### `integration_connections` (RENAME from connectors + encrypt)

```sql
CREATE TABLE integration_connections (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    integration_type         TEXT NOT NULL,
    encrypted_access_token   TEXT NOT NULL,
    encrypted_refresh_token  TEXT,
    token_expiry             TIMESTAMPTZ,
    connection_metadata      JSONB,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_integration_connections_user_type
    ON integration_connections (user_id, integration_type);
```

#### `connector_credentials` (NEW)

```sql
CREATE TABLE connector_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id   UUID NOT NULL REFERENCES integration_connections(id) ON DELETE CASCADE,
    credential_type TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);
```

#### `connector_sync_runs` (NEW)

```sql
CREATE TABLE connector_sync_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id   UUID NOT NULL REFERENCES integration_connections(id) ON DELETE CASCADE,
    sync_type       TEXT NOT NULL,
    status          TEXT NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    records_scanned BIGINT,
    records_changed BIGINT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `composio_profiles` (KEEP)

No changes.

### 4.10 Mobile Domain

#### `apple_accounts` (NEW — split from apple_credentials)

```sql
CREATE TABLE apple_accounts (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    apple_id                 TEXT NOT NULL,
    auth_state               TEXT NOT NULL DEFAULT 'pending_login',
    encrypted_session_data   TEXT,
    selected_team_id         TEXT,
    team_name                TEXT,
    available_teams          JSONB,
    session_expiry           TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_apple_accounts_user_apple ON apple_accounts (user_id, apple_id);
```

#### `apple_build_credentials` (NEW — split from apple_credentials)

```sql
CREATE TABLE apple_build_credentials (
    id                                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apple_account_id                  UUID NOT NULL REFERENCES apple_accounts(id) ON DELETE CASCADE,
    bundle_identifier                 TEXT NOT NULL,
    encrypted_expo_token              TEXT,
    encrypted_app_specific_password   TEXT,
    encrypted_p12                     TEXT,
    encrypted_p12_password            TEXT,
    encrypted_provisioning_profile    TEXT,
    certificate_id                    TEXT,
    certificate_expires_at            TIMESTAMPTZ,
    metadata                          JSONB,
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.11 System Domain

#### `system_configs` (RENAME from application_configs)

```sql
CREATE TABLE system_configs (
    key        TEXT PRIMARY KEY,
    value      JSONB,
    is_secret  BOOLEAN NOT NULL DEFAULT FALSE,
    version    BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.12 Content Domain (KEEP — lowest priority changes)

#### `presentations` (NEW — root for slides)

```sql
CREATE TABLE presentations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id  UUID REFERENCES projects(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

All other content tables (`slide_contents`, `slide_versions`,
`slide_templates`, `storybooks`, `storybook_pages`, `storybook_page_links`,
`media_templates`, `skills`) keep their current structure with future asset FK
migration.

---

## 5. Current-to-Target Mapping

| Current Table | Target Table(s) | Action |
|---|---|---|
| `users` | `users` + `user_profiles` | Split, remove billing columns |
| `api_keys` | `user_api_keys` | Rename, hash keys |
| `waitlist` | `waitlist_entries` | Rename, add UUID PK |
| `billing_transactions` | `billing_webhook_events` + `billing_invoices` | Split raw webhooks from business invoices |
| `billing_customers` | `billing_customers` + `billing_subscriptions` | Keep customer identity, move subscription out |
| `credit_ledger` | `credit_ledger` | **Keep** |
| `credit_balances` | `credit_balances` | **Keep** |
| `session_metrics` | `usage_records` | Replace |
| `sessions` | `sessions` + `session_shares` | Slim, split sharing |
| `session_wishlists` | `session_bookmarks` | Rename, composite PK |
| `chat_runs` | `app_runs` | Backfill then replace |
| `chat_messages` | `messages` + `message_parts` + `message_attachments` | Backfill then replace |
| `chat_summaries` | `session_summaries` | Unify |
| `chat_provider_containers` | `chat_provider_containers` | Add FK, keep for now |
| `chat_provider_files` | `chat_provider_files` | Add FKs, later point to assets |
| `chat_provider_vector_stores` | `chat_provider_vector_stores` | Add FK |
| `agent_run_tasks` | `app_runs` | Backfill then replace |
| `agent_run_messages` | `agent_run_snapshots` + `messages`/`message_parts` | Split snapshot from canonical |
| `agent_event_log` | `event_log` | Unify |
| `agent_events` | `event_log` | Unify |
| `agent_summaries` | `session_summaries` | Unify |
| `agent_sandboxes` | `agent_sandboxes` | Add real FK |
| `file_uploads` | `assets` (long-term) | Keep temporarily |
| `projects` | `projects` | Remove JSON blobs, remove session ownership |
| `project_deployments` | `project_deployments` + `deployment_steps` | Add step detail |
| `project_databases` | `project_databases` | Rekey session_id -> project_id + environment_id |
| `project_custom_domains` | `project_domains` | Rename |
| *(none)* | `project_environments` | **New** |
| *(none)* | `project_secrets` | **New** |
| *(none)* | `project_storage_configs` | **New** |
| `llm_settings` | `llm_provider_credentials` + `llm_profiles` | Split |
| `mcp_settings` | `mcp_server_configs` | Rename |
| `connectors` | `integration_connections` + `connector_credentials` + `connector_sync_runs` | Split + encrypt |
| `composio_profiles` | `composio_profiles` | **Keep** |
| `apple_credentials` | `apple_accounts` + `apple_build_credentials` | Split |
| `application_configs` | `system_configs` | Rename |
| Content tables | Keep + future asset FKs | Lowest priority |
| *(none)* | `app_runs` | **New** |
| *(none)* | `run_steps` | **New** |
| *(none)* | `messages` | **New** |
| *(none)* | `message_parts` | **New** |
| *(none)* | `message_attachments` | **New** |
| *(none)* | `llm_invocations` | **New** |
| *(none)* | `tool_invocations` | **New** |
| *(none)* | `event_log` | **New** |
| *(none)* | `session_summaries` | **New** |
| *(none)* | `agent_run_snapshots` | **New** |
| *(none)* | `agent_plans` | **New** |
| *(none)* | `agent_milestones` | **New** |
| *(none)* | `assets` | **New** |
| *(none)* | `presentations` | **New** |
| *(none)* | `session_shares` | **New** |
| *(none)* | `billing_subscriptions` | **New** |
| *(none)* | `billing_invoices` | **New** |
| *(none)* | `billing_webhook_events` | **New** |
| *(none)* | `usage_records` | **New** |
| *(none)* | `deployment_steps` | **New** |

---

## 6. Migration Priority Order

### P0: Stabilize baseline + Security hardening (parallel tracks)

**Track A — Schema stabilization:**
- Add 11 missing FK constraints (NOT VALID, then validate)
- Standardize timezone-aware timestamps
- Add missing uniqueness constraints
- Add idempotency keys to storybook/voice billing (code only)

**Track B — Security (runs in parallel with Track A):**
- Hash API keys: add key_hash + key_prefix columns, backfill, update auth, drop raw key
- Encrypt connector tokens: add encrypted_* columns, backfill, update service, drop plaintext

### P1: Usage analytics + ChatRun expansion

- Create `usage_records` table
- Expand `chat_runs` with model_id, provider, usage, cost_usd, timing columns
- Dual-write UsageService to both session_metrics and usage_records
- Backfill usage_records from credit_ledger.entry_metadata
- New analytics API endpoints

### P2: Consolidate subscription state

- Create `billing_subscriptions`
- Create `billing_invoices`
- Create `billing_webhook_events`
- Backfill from users + billing_customers + billing_transactions
- Update webhook handlers to write new tables
- Stop writing users.subscription_* and billing_customers.subscription_*

### P3: Project ownership + session.project_id

- Add `sessions.project_id`, backfill from projects.session_id
- Create `project_environments`
- Rekey `project_databases` from session_id to project_id + environment_id
- Create `project_secrets`, backfill from projects.secrets_json
- Create `project_storage_configs`, backfill from projects.storage_json
- Create `deployment_steps`
- Deprecate reads from projects.session_id (code switches to sessions.project_id)

### P4: Session slimdown + sharing

- Create `session_shares`, backfill from sessions.is_public / public_url
- Cut sharing reads/writes to session_shares
- Remove sandbox_id, agent_state_path from sessions

### P5: Settings split

- Split `llm_settings` into `llm_provider_credentials` + `llm_profiles`
- Migrate sessions.llm_setting_id -> llm_profile_id
- Rename `mcp_settings` -> `mcp_server_configs`
- Split `apple_credentials` -> `apple_accounts` + `apple_build_credentials`

### P6: Unified runtime core (phased)

**Phase 6A — Telemetry tables (dual-write, no read cutover):**
- Create `app_runs`
- Create `llm_invocations` + `tool_invocations`
- Dual-write from chat and agent execution flows

**Phase 6B — Message normalization (dual-write):**
- Create `messages` + `message_parts`
- Dual-write from both chat_messages and agent_run_messages paths

**Phase 6C — Event & summary unification (dual-write):**
- Create `event_log` (replaces agent_events + agent_event_log)
- Create `session_summaries` (replaces chat_summaries + agent_summaries)
- Create `run_steps`
- Dual-write from current event/summary paths

**Phase 6D — Read cutover:**
- Switch all read paths to unified tables
- Verify data consistency
- Stop writing to legacy tables

### P7: Agent-specific state

- Create `agent_run_snapshots` (1:1 with app_runs for agent runs)
- Create `agent_plans` + `agent_milestones`
- Backfill plans from sessions.session_metadata.plan
- Bind agent_sandboxes with real FK to sessions

### P8: Assets + file normalization

- Create `assets` table
- Backfill from file_uploads, storybook media URLs, slide version URLs
- Create `message_attachments` (depends on messages + assets)
- Update provider_files to reference assets

### P9: User/project structural cleanup

- Create `user_profiles`, split from users
- Rename connectors -> integration_connections + connector_credentials
- Rename billing_transactions -> keep as read-only archive
- Rename waitlist -> waitlist_entries
- Rename application_configs -> system_configs
- Rename project_custom_domains -> project_domains
- Drop projects.session_id, database_json, storage_json, secrets_json

### P10: Content normalization + final cleanup

- Create `presentations` root table
- Normalize storybook_page_links -> storybook_version_pages with position
- Replace URL columns with asset_id FKs on slide/storybook tables
- Drop all legacy tables and columns (session_metrics, billing_transactions,
  chat_runs, chat_messages, chat_summaries, agent_run_tasks, agent_run_messages,
  agent_events, agent_event_log, agent_summaries, file_uploads, api_keys,
  llm_settings, mcp_settings, apple_credentials)
- Drop deprecated columns from users, sessions, projects

---

## 7. Step-by-Step Migration Guide

Each step is one Alembic revision unless noted otherwise. Steps within a
priority can be parallelized if they touch different tables.

### P0-A: Schema Stabilization

#### Step 0A-1: Add missing foreign keys (NOT VALID)

**Alembic revision: `add_missing_fks_not_valid`**

```python
def upgrade():
    # chat_messages.session_id -> sessions.id
    op.execute("""
        ALTER TABLE chat_messages
        ADD CONSTRAINT fk_chat_messages_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)
    # chat_messages.parent_message_id -> chat_messages.id
    op.execute("""
        ALTER TABLE chat_messages
        ADD CONSTRAINT fk_chat_messages_parent
        FOREIGN KEY (parent_message_id) REFERENCES chat_messages(id) ON DELETE SET NULL
        NOT VALID
    """)
    # chat_provider_containers.session_id -> sessions.id
    op.execute("""
        ALTER TABLE chat_provider_containers
        ADD CONSTRAINT fk_chat_provider_containers_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)
    # chat_provider_files.session_id -> sessions.id
    op.execute("""
        ALTER TABLE chat_provider_files
        ADD CONSTRAINT fk_chat_provider_files_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)
    # chat_provider_files.file_id -> file_uploads.id
    op.execute("""
        ALTER TABLE chat_provider_files
        ADD CONSTRAINT fk_chat_provider_files_file
        FOREIGN KEY (file_id) REFERENCES file_uploads(id) ON DELETE SET NULL
        NOT VALID
    """)
    # chat_provider_vector_stores.user_id -> users.id
    op.execute("""
        ALTER TABLE chat_provider_vector_stores
        ADD CONSTRAINT fk_chat_provider_vector_stores_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        NOT VALID
    """)
    # agent_sandboxes.session_id -> sessions.id
    op.execute("""
        ALTER TABLE agent_sandboxes
        ADD CONSTRAINT fk_agent_sandboxes_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)
    # agent_event_log.session_id -> sessions.id
    op.execute("""
        ALTER TABLE agent_event_log
        ADD CONSTRAINT fk_agent_event_log_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)
    # agent_event_log.run_id -> agent_run_tasks.id
    op.execute("""
        ALTER TABLE agent_event_log
        ADD CONSTRAINT fk_agent_event_log_run
        FOREIGN KEY (run_id) REFERENCES agent_run_tasks(id) ON DELETE CASCADE
        NOT VALID
    """)
    # agent_summaries.session_id -> sessions.id
    op.execute("""
        ALTER TABLE agent_summaries
        ADD CONSTRAINT fk_agent_summaries_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        NOT VALID
    """)

def downgrade():
    for tbl, name in [
        ("chat_messages", "fk_chat_messages_session"),
        ("chat_messages", "fk_chat_messages_parent"),
        ("chat_provider_containers", "fk_chat_provider_containers_session"),
        ("chat_provider_files", "fk_chat_provider_files_session"),
        ("chat_provider_files", "fk_chat_provider_files_file"),
        ("chat_provider_vector_stores", "fk_chat_provider_vector_stores_user"),
        ("agent_sandboxes", "fk_agent_sandboxes_session"),
        ("agent_event_log", "fk_agent_event_log_session"),
        ("agent_event_log", "fk_agent_event_log_run"),
        ("agent_summaries", "fk_agent_summaries_session"),
    ]:
        op.drop_constraint(name, tbl, type_="foreignkey")
```

**Pre-flight:** Run orphan-detection queries first. Clean up orphan rows before
adding constraints.

```sql
-- Example: find orphan chat_messages
SELECT cm.id FROM chat_messages cm
LEFT JOIN sessions s ON cm.session_id = s.id
WHERE s.id IS NULL;
-- Delete or archive orphans before proceeding
```

#### Step 0A-2: Validate foreign keys

**Alembic revision: `validate_missing_fks`**

Run in a separate migration after 0A-1 has been deployed and orphans cleaned.

```python
def upgrade():
    for stmt in [
        "ALTER TABLE chat_messages VALIDATE CONSTRAINT fk_chat_messages_session",
        "ALTER TABLE chat_messages VALIDATE CONSTRAINT fk_chat_messages_parent",
        "ALTER TABLE chat_provider_containers VALIDATE CONSTRAINT fk_chat_provider_containers_session",
        "ALTER TABLE chat_provider_files VALIDATE CONSTRAINT fk_chat_provider_files_session",
        "ALTER TABLE chat_provider_files VALIDATE CONSTRAINT fk_chat_provider_files_file",
        "ALTER TABLE chat_provider_vector_stores VALIDATE CONSTRAINT fk_chat_provider_vector_stores_user",
        "ALTER TABLE agent_sandboxes VALIDATE CONSTRAINT fk_agent_sandboxes_session",
        "ALTER TABLE agent_event_log VALIDATE CONSTRAINT fk_agent_event_log_session",
        "ALTER TABLE agent_event_log VALIDATE CONSTRAINT fk_agent_event_log_run",
        "ALTER TABLE agent_summaries VALIDATE CONSTRAINT fk_agent_summaries_session",
    ]:
        op.execute(stmt)
```

#### Step 0A-3: Add idempotency keys to storybook/voice billing

**Code-only change (no Alembic).**

Files to modify:
- `workers/celery/tasks.py` -> `_deduct_storybook_credits()`:
  generate idempotency key from `(storybook_id, page_id, task_id)`
- `content/storybook/voice_service.py` -> `generate_voiceover_and_deduct_credits()`:
  generate idempotency key from `(storybook_id, page_id, "voice", timestamp_bucket)`
- `content/storybook/ai_edit_service.py` -> image generation billing:
  generate idempotency key from `(storybook_id, page_id, "image_edit", timestamp_bucket)`

Wire keys through existing `CreditLedgerService` which already supports
`idempotency_key`.

### P0-B: Security Hardening (parallel with P0-A)

#### Step 0B-1: Add hash columns to api_keys

**Alembic revision: `add_api_key_hash_columns`**

```python
def upgrade():
    op.add_column("api_keys", sa.Column("key_hash", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("key_prefix", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("name", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("last_used_at",
        sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("expires_at",
        sa.TIMESTAMP(timezone=True), nullable=True))
```

#### Step 0B-2: Backfill api_key hashes

**Operational script (not Alembic).**

```python
# scripts/backfill_api_key_hashes.py
import hashlib

async def backfill():
    """Idempotent: skips rows that already have key_hash."""
    batch_size = 100
    last_id = None
    while True:
        query = select(ApiKey).where(ApiKey.key_hash.is_(None))
        if last_id:
            query = query.where(ApiKey.id > last_id)
        query = query.order_by(ApiKey.id).limit(batch_size)
        rows = (await db.execute(query)).scalars().all()
        if not rows:
            break
        for row in rows:
            row.key_hash = hashlib.sha256(row.api_key.encode()).hexdigest()
            row.key_prefix = row.api_key[:8]
            last_id = row.id
        await db.commit()
```

#### Step 0B-3: Update auth middleware to compare hashes

**Code change.** Update `auth/dependencies.py` to:
1. Hash the incoming API key
2. Look up by `key_hash` instead of `api_key`
3. Update `last_used_at` on successful auth

#### Step 0B-4: Enforce key_hash NOT NULL, drop raw key

**Alembic revision: `enforce_api_key_hash`**

```python
def upgrade():
    op.alter_column("api_keys", "key_hash", nullable=False)
    op.alter_column("api_keys", "key_prefix", nullable=False)
    op.create_unique_constraint("uq_api_keys_key_hash", "api_keys", ["key_hash"])
    op.drop_column("api_keys", "api_key")
```

#### Step 0B-5: Add encrypted connector token columns

**Alembic revision: `add_encrypted_connector_tokens`**

```python
def upgrade():
    op.add_column("connectors",
        sa.Column("encrypted_access_token", sa.String(), nullable=True))
    op.add_column("connectors",
        sa.Column("encrypted_refresh_token", sa.String(), nullable=True))
```

#### Step 0B-6: Backfill encrypted connector tokens

**Operational script.** Encrypt existing plaintext tokens using application
encryption key. Idempotent: skip rows where encrypted column is already set.

#### Step 0B-7: Switch connector service, drop plaintext

**Code change:** Update connector service to read/write encrypted columns.

**Alembic revision: `drop_plaintext_connector_tokens`**

```python
def upgrade():
    op.alter_column("connectors", "encrypted_access_token", nullable=False)
    op.drop_column("connectors", "access_token")
    op.drop_column("connectors", "refresh_token")
```

### P1: Usage Analytics + ChatRun Expansion

#### Step 1-1: Create usage_records table

**Alembic revision: `create_usage_records`**

```python
def upgrade():
    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(), nullable=True),
        sa.Column("project_id", postgresql.UUID(), nullable=True),
        sa.Column("run_id", postgresql.UUID(), nullable=True),
        sa.Column("ledger_entry_id", sa.BigInteger(), sa.ForeignKey("credit_ledger.id"), nullable=True),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("app_kind", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("credits_charged", sa.Numeric(18, 6), nullable=True),
        sa.Column("usage_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_usage_records_user_created", "usage_records", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_session", "usage_records", ["session_id", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_model", "usage_records", ["model_id", sa.text("created_at DESC")])
    op.create_index("idx_usage_records_source", "usage_records", ["source_domain", sa.text("created_at DESC")])
```

#### Step 1-2: Expand chat_runs

**Alembic revision: `expand_chat_runs`**

```python
def upgrade():
    op.add_column("chat_runs", sa.Column("assistant_message_id", postgresql.UUID(), nullable=True))
    op.add_column("chat_runs", sa.Column("finish_reason", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("model_id", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("usage", postgresql.JSONB(), nullable=True))
    op.add_column("chat_runs", sa.Column("cost_usd", sa.Numeric(18, 6), nullable=True))
    op.add_column("chat_runs", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("chat_runs", sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("chat_runs", sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("chat_runs", sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True))
```

#### Step 1-3: Dual-write UsageService

**Code change.** Update `UsageService.deduct_and_track_session_usage()`:
1. Continue writing `session_metrics` (existing)
2. Also write `usage_records` with denormalized fields from `entry_metadata`

Fields to extract: `model_id`, `provider`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `cost_usd`,
`credits_charged`.

#### Step 1-4: Update ChatRunRepository for new columns

**Code change.** Update `ChatRunRepository` to write `model_id`, `provider`,
`usage`, `cost_usd`, `started_at`, `completed_at`, `cancelled_at`,
`assistant_message_id`, `finish_reason` during turn lifecycle.

Data is already available in `TurnLoopService` — just pass it through.

#### Step 1-5: Backfill usage_records from credit_ledger

**Operational script: `scripts/backfill_usage_records.py`**

Read all `credit_ledger` entries with `entry_type='deduction'`, extract token
breakdown from `entry_metadata` JSONB, insert into `usage_records`.

Use keyset pagination on `credit_ledger.id`. Make idempotent by checking
`ledger_entry_id` uniqueness before insert.

#### Step 1-6: Add analytics API endpoints

**Code change.** New endpoints:

```
GET /credits/usage/by-model?period=30d
GET /credits/usage/by-session/{session_id}/details
GET /credits/usage/summary?period=30d
```

Query `usage_records` directly.

### P2: Consolidate Subscription State

#### Step 2-1: Create billing tables

**Alembic revision: `create_billing_subscriptions_invoices_webhooks`**

Create three tables in one migration:
- `billing_subscriptions`
- `billing_invoices`
- `billing_webhook_events`

All with DDL from Section 4.2.

#### Step 2-2: Backfill billing_subscriptions

**Operational script: `scripts/backfill_billing_subscriptions.py`**

Source priority:
1. `billing_customers` rows with `subscription_*` columns set
2. `users` rows with `subscription_*` columns set (fallback)
3. `billing_transactions` with subscription events in `raw_payload`

For each user, create one `billing_subscriptions` row linked via
`billing_customer_id`.

#### Step 2-3: Backfill billing_webhook_events

**Operational script: `scripts/backfill_billing_webhook_events.py`**

Read all `billing_transactions` rows. Map:
- `stripe_event_id` -> `external_event_id`
- `raw_payload` -> `payload`
- Extract `event_type` from `raw_payload.type`
- Set `processing_status = 'processed'`, `processed_at = created_at`

#### Step 2-4: Backfill billing_invoices

**Operational script: `scripts/backfill_billing_invoices.py`**

Extract invoice data from `billing_transactions` where
`stripe_invoice_id IS NOT NULL`. Link to `billing_subscriptions` via
`stripe_subscription_id`.

#### Step 2-5: Update webhook handlers

**Code change.** Update all four Stripe webhook handlers:
- `checkout.session.completed`
- `invoice.payment_succeeded`
- `customer.subscription.deleted`
- `customer.subscription.updated`

Each handler should:
1. Write `billing_webhook_events` (raw event)
2. Upsert `billing_subscriptions` (subscription state)
3. Upsert `billing_invoices` (if invoice event)
4. Continue writing `billing_customers` and `users` (dual-write period)

#### Step 2-6: Stop writing subscription columns to users + billing_customers

**Code change.** After one release of dual-write:
1. Remove writes to `users.subscription_*`
2. Remove writes to `billing_customers.subscription_*`
3. Update all read paths to use `billing_subscriptions`

### P3: Project Ownership

#### Step 3-1: Add sessions.project_id

**Alembic revision: `add_sessions_project_id`**

```python
def upgrade():
    op.add_column("sessions",
        sa.Column("project_id", sa.String(), nullable=True))
    op.create_foreign_key("fk_sessions_project", "sessions", "projects",
        ["project_id"], ["id"], ondelete="SET NULL")
    op.create_index("idx_sessions_project", "sessions", ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"))
```

#### Step 3-2: Backfill sessions.project_id

**Operational script: `scripts/backfill_sessions_project_id.py`**

```sql
UPDATE sessions s
SET project_id = p.id
FROM projects p
WHERE p.session_id = s.id
  AND s.project_id IS NULL;
```

#### Step 3-3: Create project_environments

**Alembic revision: `create_project_environments`**

Create table with DDL from Section 4.4. Then backfill a default
"production" environment for every existing project:

**Operational script: `scripts/backfill_project_environments.py`**

```sql
INSERT INTO project_environments (id, project_id, name, is_default, status)
SELECT gen_random_uuid(), id, 'production', TRUE, 'active'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM project_environments pe WHERE pe.project_id = projects.id
);
```

#### Step 3-4: Rekey project_databases

**Alembic revision: `rekey_project_databases`**

```python
def upgrade():
    op.add_column("project_databases",
        sa.Column("project_id", sa.String(), nullable=True))
    op.add_column("project_databases",
        sa.Column("environment_id", postgresql.UUID(), nullable=True))
```

**Operational script: `scripts/backfill_project_databases_project_id.py`**

```sql
-- Set project_id from session -> project mapping
UPDATE project_databases pd
SET project_id = p.id
FROM projects p
WHERE p.session_id = pd.session_id
  AND pd.project_id IS NULL;

-- Set environment_id to default production environment
UPDATE project_databases pd
SET environment_id = pe.id
FROM project_environments pe
WHERE pe.project_id = pd.project_id
  AND pe.is_default = TRUE
  AND pd.environment_id IS NULL;
```

**Alembic revision: `enforce_project_databases_project_id`**

```python
def upgrade():
    op.alter_column("project_databases", "project_id", nullable=False)
    op.alter_column("project_databases", "environment_id", nullable=False)
    op.create_foreign_key("fk_project_databases_project", "project_databases",
        "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_project_databases_environment", "project_databases",
        "project_environments", ["environment_id"], ["id"], ondelete="CASCADE")
    # Keep session_id for now, will drop in P9
```

#### Step 3-5: Create project_secrets

**Alembic revision: `create_project_secrets`**

Create table with DDL from Section 4.4.

**Operational script: `scripts/backfill_project_secrets.py`**

Parse `projects.secrets_json` for each project. For each key-value pair,
insert into `project_secrets` with `environment_id` set to the project's
default environment.

#### Step 3-6: Create project_storage_configs

**Alembic revision: `create_project_storage_configs`**

Create table, backfill from `projects.storage_json` similarly.

#### Step 3-7: Create deployment_steps

**Alembic revision: `create_deployment_steps`**

Create table with DDL from Section 4.4. No backfill needed — new
deployments start writing steps going forward.

#### Step 3-8: Switch code to read from new project tables

**Code change.** Update:
- `ProjectService` to read databases from `project_databases` via `project_id`
- `ProjectService` to read secrets from `project_secrets`
- `ProjectService` to read storage config from `project_storage_configs`
- Stop reading `projects.database_json`, `projects.storage_json`,
  `projects.secrets_json`
- Stop reading `projects.session_id` for ownership — use `sessions.project_id`

### P4: Session Slimdown

#### Step 4-1: Create session_shares

**Alembic revision: `create_session_shares`**

Create table with DDL from Section 4.3.

**Operational script: `scripts/backfill_session_shares.py`**

```sql
INSERT INTO session_shares (id, session_id, visibility, public_url, created_at)
SELECT gen_random_uuid(), id,
       CASE WHEN is_public THEN 'public' ELSE 'private' END,
       public_url, created_at
FROM sessions
WHERE is_public = TRUE OR public_url IS NOT NULL;
```

#### Step 4-2: Cut sharing reads/writes

**Code change.** Update:
- `SessionService.set_session_public()` -> write `session_shares`
- `SessionRepository.get_public_by_id()` -> read from `session_shares`
- All public session routes -> join `session_shares`

#### Step 4-3: Remove agent workspace fields from sessions

**Code change.** Stop reading `sessions.sandbox_id` (already redundant with
`agent_sandboxes.session_id` unique constraint). Stop reading
`sessions.agent_state_path`. Agent code should use agent-owned tables.

### P5: Settings Split

#### Step 5-1: Create llm_provider_credentials + llm_profiles

**Alembic revision: `create_llm_credentials_and_profiles`**

Create both tables with DDL from Section 4.7.

#### Step 5-2: Backfill from llm_settings

**Operational script: `scripts/backfill_llm_settings_split.py`**

For each `llm_settings` row:
1. Create `llm_provider_credentials` row with `api_type`, `encrypted_api_key`,
   `base_url`
2. Create `llm_profiles` row with `model`, `temperature`, `thinking_tokens`,
   `max_retries`, `max_message_chars`, linked to credential via `credential_id`

#### Step 5-3: Add sessions.llm_profile_id

**Alembic revision: `add_sessions_llm_profile_id`**

```python
def upgrade():
    op.add_column("sessions",
        sa.Column("llm_profile_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key("fk_sessions_llm_profile", "sessions",
        "llm_profiles", ["llm_profile_id"], ["id"], ondelete="SET NULL")
```

**Operational script:** Backfill `llm_profile_id` from `llm_setting_id`
mapping.

#### Step 5-4: Cut reads/writes to new settings tables

**Code change.** Update SettingsService, SessionService, and all LLM provider
code to read from `llm_profiles` + `llm_provider_credentials`.

#### Step 5-5: Rename mcp_settings

**Alembic revision: `rename_mcp_settings`**

```python
def upgrade():
    op.rename_table("mcp_settings", "mcp_server_configs")
    op.add_column("mcp_server_configs", sa.Column("name", sa.String(), nullable=True))
    # Backfill name from mcp_config JSON or generate default
    op.execute("""
        UPDATE mcp_server_configs
        SET name = COALESCE(config_json->>'name', 'default-' || id)
        WHERE name IS NULL
    """)
    op.alter_column("mcp_server_configs", "name", nullable=False)
    op.create_unique_constraint("uq_mcp_server_configs_user_name",
        "mcp_server_configs", ["user_id", "name"])
```

Note: rename `mcp_config` column to `config_json`, `metadata` to
`config_metadata` in the same migration.

#### Step 5-6: Split apple_credentials

**Alembic revision: `create_apple_accounts_and_build_credentials`**

Create both tables with DDL from Section 4.10.

**Operational script: `scripts/backfill_apple_credentials_split.py`**

For each `apple_credentials` row:
1. Create `apple_accounts` row with auth fields
2. Create `apple_build_credentials` row with certificate/build fields
   (only if build fields are populated)

### P6: Unified Runtime Core

#### Phase 6A: Telemetry Tables

##### Step 6A-1: Create app_runs

**Alembic revision: `create_app_runs`**

Create table with DDL from Section 4.5.

##### Step 6A-2: Create llm_invocations + tool_invocations

**Alembic revision: `create_invocation_tables`**

Create both tables with DDL from Section 4.5.

##### Step 6A-3: Dual-write app_runs from chat flow

**Code change.** In `ChatRunRepository` / `TurnLoopService`:
- On chat run start: also create `app_runs` row with
  `app_kind='chat'`, `run_kind='chat'`
- On chat run complete: also update `app_runs.status`, `finished_at`
- On LLM call: also write `llm_invocations`
- On tool call: also write `tool_invocations`

##### Step 6A-4: Dual-write app_runs from agent flow

**Code change.** In agent run lifecycle:
- On agent run start: also create `app_runs` row with
  `app_kind='agent'`, `run_kind='agent'`
- On agent run complete: also update `app_runs.status`, `finished_at`
- On LLM call: also write `llm_invocations`
- On tool call: also write `tool_invocations`

##### Step 6A-5: Backfill app_runs from chat_runs + agent_run_tasks

**Operational script: `scripts/backfill_app_runs.py`**

```python
# From chat_runs
async def backfill_chat_runs():
    """Insert app_runs for each chat_run, using chat_run.id as app_run.id."""
    # Keyset pagination on chat_runs.id
    # Map status values
    # Set app_kind='chat', run_kind='chat'

# From agent_run_tasks
async def backfill_agent_runs():
    """Insert app_runs for each agent_run_task."""
    # Map status values
    # Set app_kind='agent', run_kind='agent'
```

#### Phase 6B: Message Normalization

##### Step 6B-1: Create messages + message_parts

**Alembic revision: `create_messages_and_parts`**

Create both tables with DDL from Section 4.5.

##### Step 6B-2: Dual-write messages from chat flow

**Code change.** When writing `chat_messages`, also write to `messages` +
`message_parts`. Map:
- `chat_messages.content` JSONB array -> individual `message_parts` rows
- `chat_messages.role`, `model`, `finish_reason` -> `messages` columns
- Set `messages.run_id` to the corresponding `app_runs.id`

##### Step 6B-3: Dual-write messages from agent flow

**Code change.** When agent runs produce messages (stored in
`agent_run_messages.messages` JSONB), also write individual `messages` +
`message_parts` rows.

##### Step 6B-4: Backfill messages from chat_messages

**Operational script: `scripts/backfill_messages_from_chat.py`**

For each `chat_messages` row:
1. Create `messages` row preserving the same UUID
2. Parse `content` JSONB array -> create `message_parts` rows with
   sequential ordinals

Keyset pagination on `chat_messages.id`. Idempotent: skip if
`messages.id` already exists.

#### Phase 6C: Event & Summary Unification

##### Step 6C-1: Create event_log + session_summaries + run_steps

**Alembic revision: `create_event_log_summaries_steps`**

Create all three tables with DDL from Section 4.5.

##### Step 6C-2: Dual-write events

**Code change.** When writing `agent_events` or `agent_event_log`, also
write to `event_log`. Map:
- `agent_events.type` -> `event_log.event_type`, `scope='ui'`
- `agent_event_log.name` -> `event_log.event_type`,
  `scope=agent_event_log.group`

##### Step 6C-3: Dual-write summaries

**Code change.** When writing `chat_summaries` or `agent_summaries`, also
write to `session_summaries`. Map:
- `chat_summaries` -> `summary_type='chat'`
- `agent_summaries` -> `summary_type='agent'`

#### Phase 6D: Read Cutover

##### Step 6D-1: Switch read paths

**Code change.** One service/endpoint at a time:
1. Session message listing -> read from `messages` + `message_parts`
2. Run listing -> read from `app_runs`
3. Event stream -> read from `event_log`
4. Summary retrieval -> read from `session_summaries`

Each switch should be behind a feature flag or config toggle for rollback.

##### Step 6D-2: Verify data consistency

**Operational script: `scripts/verify_runtime_consistency.py`**

Compare row counts and spot-check content between old and new tables.
Run for at least one release cycle.

##### Step 6D-3: Stop writing to legacy tables

**Code change.** Remove dual-write code for:
- `chat_runs` (still write `app_runs`)
- `chat_messages` (still write `messages` + `message_parts`)
- `agent_events` (still write `event_log`)
- `agent_event_log` (still write `event_log`)
- `chat_summaries` (still write `session_summaries`)
- `agent_summaries` (still write `session_summaries`)

### P7: Agent-Specific State

#### Step 7-1: Create agent_run_snapshots

**Alembic revision: `create_agent_run_snapshots`**

Create table with DDL from Section 4.6. PK is `run_id` referencing
`app_runs(id)`.

#### Step 7-2: Backfill agent_run_snapshots

**Operational script: `scripts/backfill_agent_run_snapshots.py`**

For each `agent_run_messages` row, create an `agent_run_snapshots` row.
Map `agent_run_messages.run_id` to the corresponding `app_runs.id`.

#### Step 7-3: Create agent_plans + agent_milestones

**Alembic revision: `create_agent_plans_milestones`**

Create both tables with DDL from Section 4.6.

#### Step 7-4: Backfill plans from session_metadata

**Operational script: `scripts/backfill_agent_plans.py`**

```python
# For each session with session_metadata->>'plan' IS NOT NULL:
# 1. Parse plan JSON
# 2. Find the most recent app_run for this session
# 3. Create agent_plans row
# 4. Create agent_milestones rows for each step in the plan
```

#### Step 7-5: Tighten agent_sandboxes FK

**Alembic revision: `add_agent_sandboxes_run_fk`**

```python
def upgrade():
    op.add_column("agent_sandboxes",
        sa.Column("run_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key("fk_agent_sandboxes_run", "agent_sandboxes",
        "app_runs", ["run_id"], ["id"], ondelete="SET NULL")
```

#### Step 7-6: Update agent code

**Code change.** Update agent lifecycle code to:
- Write `agent_run_snapshots` instead of `agent_run_messages`
- Write `agent_plans` + `agent_milestones` instead of
  `sessions.session_metadata.plan`
- Read sandbox state from `agent_sandboxes` only (not `sessions.sandbox_id`)

### P8: Assets + File Normalization

#### Step 8-1: Create assets table

**Alembic revision: `create_assets`**

Create table with DDL from Section 4.8.

#### Step 8-2: Backfill assets from file_uploads

**Operational script: `scripts/backfill_assets_from_uploads.py`**

For each `file_uploads` row, create an `assets` row:
- `source_kind = 'upload'`
- `media_kind` = derive from `content_type`
- `object_path = storage_path`
- `size_bytes = file_size`
- `mime_type = content_type`

#### Step 8-3: Create message_attachments

**Alembic revision: `create_message_attachments`**

Create table with DDL from Section 4.5. Requires both `messages` and
`assets` tables to exist.

#### Step 8-4: Backfill message_attachments

**Operational script: `scripts/backfill_message_attachments.py`**

For each `chat_messages` row with non-null `file_ids`:
1. Look up or create `assets` row for each file_id
2. Create `message_attachments` row linking `messages.id` to `assets.id`

#### Step 8-5: Update provider_files to reference assets

**Code change.** Add `asset_id` column to `chat_provider_files`. On file
upload, create both `assets` row and `chat_provider_files` row with the
asset reference.

### P9: Structural Cleanup & Renames

#### Step 9-1: Create user_profiles

**Alembic revision: `create_user_profiles`**

Create table, backfill from `users.first_name`, `users.last_name`,
`users.avatar`, `users.language`, `users.metadata`.

#### Step 9-2: Rename tables

**Alembic revisions (one per rename):**
- `connectors` -> `integration_connections` (add encrypted columns if not done)
- `waitlist` -> `waitlist_entries`
- `application_configs` -> `system_configs`
- `project_custom_domains` -> `project_domains`
- `session_wishlists` -> `session_bookmarks` (change to composite PK)

Each rename: create new table, copy data, drop old, add redirecting view
temporarily if application code references old name.

#### Step 9-3: Drop deprecated columns from users

**Alembic revision: `drop_users_billing_columns`**

Only after verifying no code reads these columns:

```python
def upgrade():
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "subscription_plan")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "subscription_billing_cycle")
    op.drop_column("users", "subscription_current_period_end")
    op.drop_column("users", "credits")
    op.drop_column("users", "bonus_credits")
    op.drop_column("users", "first_name")
    op.drop_column("users", "last_name")
    op.drop_column("users", "avatar")
    op.drop_column("users", "language")
    op.drop_column("users", "metadata")
```

#### Step 9-4: Drop deprecated columns from projects

```python
def upgrade():
    op.drop_column("projects", "session_id")
    op.drop_column("projects", "database_json")
    op.drop_column("projects", "storage_json")
    op.drop_column("projects", "secrets_json")
    op.drop_column("projects", "current_build_status")
    op.drop_column("projects", "custom_domain_id")
```

#### Step 9-5: Drop deprecated columns from sessions

```python
def upgrade():
    op.drop_column("sessions", "sandbox_id")
    op.drop_column("sessions", "agent_state_path")
    op.drop_column("sessions", "agent_type")
    op.drop_column("sessions", "api_version")
    op.drop_column("sessions", "is_public")
    op.drop_column("sessions", "public_url")
    op.drop_column("sessions", "llm_setting_id")
```

#### Step 9-6: Drop subscription columns from billing_customers

```python
def upgrade():
    op.drop_column("billing_customers", "subscription_plan")
    op.drop_column("billing_customers", "subscription_status")
    op.drop_column("billing_customers", "subscription_billing_cycle")
    op.drop_column("billing_customers", "subscription_current_period_end")
```

### P10: Content Normalization + Final Cleanup

#### Step 10-1: Create presentations table

**Alembic revision: `create_presentations`**

Create table with DDL from Section 4.12.

Backfill by extracting distinct `(session_id, presentation_name)` pairs
from `slide_contents`.

#### Step 10-2: Rekey slide tables to presentation_id

Add `presentation_id` FK to `slide_contents` and `slide_versions`.
Backfill from the `presentations` table. Drop `session_id` +
`presentation_name` composite after cutover.

#### Step 10-3: Add asset FKs to content tables

Add `image_asset_id` to `slide_versions` (replacing `image_url`).
Add `image_asset_id` and `audio_asset_id` to `storybook_pages`
(replacing `image_url` and `audio_link`).
Add `preview_asset_id` to `media_templates` and `slide_templates`.

Backfill by creating `assets` rows from existing URLs.

#### Step 10-4: Normalize storybook_page_links

Rename to `storybook_version_pages`, add `position` column.

#### Step 10-5: Drop legacy tables

**Only after full read cutover verification (minimum one release cycle):**

```python
def upgrade():
    op.drop_table("session_metrics")
    op.drop_table("billing_transactions")
    op.drop_table("chat_runs")
    op.drop_table("chat_summaries")
    op.drop_table("chat_messages")
    op.drop_table("agent_run_messages")
    op.drop_table("agent_event_log")
    op.drop_table("agent_events")
    op.drop_table("agent_summaries")
    op.drop_table("agent_run_tasks")
    op.drop_table("file_uploads")
    op.drop_table("api_keys")
    op.drop_table("llm_settings")
    op.drop_table("mcp_settings")
    op.drop_table("apple_credentials")
```

**IMPORTANT:** Keep downgrade functions that recreate these tables from
backups for at least one quarter.

---

## 8. Migration Rules

1. **Add columns nullable first.** Backfill. Then enforce NOT NULL.
2. **Add FKs as NOT VALID.** Validate in a separate migration after
   orphan cleanup.
3. **Create indexes CONCURRENTLY** on tables with >100k rows.
4. **Never UPDATE millions of rows** in one Alembic transaction. Use
   batched operational scripts.
5. **Backfills belong in operational scripts**, not Alembic revisions.
   Alembic is for DDL only.
6. **Make all backfills idempotent.** Use keyset pagination
   (`WHERE id > last_id ORDER BY id LIMIT batch`), never OFFSET.
7. **Keep one release of dual-write** before cutting reads over.
8. **Keep one release of read cutover** before dropping old columns.
9. **One source of truth** per business concept.
10. **NUMERIC(18,6)** for money/credits, never Float.
11. **UUID** primary keys for root tables, **BIGINT identity** for
    append-heavy tables.
12. **TIMESTAMPTZ** for all timestamps.
13. **Feature flags** for read cutover switches where possible.
14. **Never drop tables in the same release** that stops writing them.

---

## Summary

| Priority | Migration | Risk | Value | Effort | New Tables | Modified |
|----------|-----------|------|-------|--------|------------|----------|
| **P0-A** | FK stabilization + idempotency | Low | **Critical** | Small | 0 | 8 |
| **P0-B** | Security (hash keys, encrypt tokens) | Medium | **Critical** | Medium | 0 | 2 |
| **P1** | usage_records + ChatRun expansion | Low | **High** | Medium | 1 | 1 |
| **P2** | billing_subscriptions + invoices + webhooks | Medium | **High** | Medium | 3 | 2 |
| **P3** | Project ownership + environments | Medium | **High** | Large | 4 | 2 |
| **P4** | Session shares + slim | Medium | High | Medium | 1 | 1 |
| **P5** | Settings split + apple split | Medium | Medium | Large | 5 | 1 |
| **P6A** | app_runs + invocation tables | Low | **High** | Medium | 3 | 0 |
| **P6B** | messages + message_parts | Medium | High | Large | 2 | 0 |
| **P6C** | event_log + summaries + run_steps | Medium | Medium | Large | 3 | 0 |
| **P6D** | Read cutover | High | High | Medium | 0 | 0 |
| **P7** | Agent snapshots + plans | Medium | Medium | Medium | 3 | 1 |
| **P8** | Assets + message_attachments | Low | Medium | Medium | 2 | 1 |
| **P9** | Renames + column drops | Medium | Low | Large | 1 | 6 |
| **P10** | Content normalization + final drops | Low | Low | Large | 1 | 5 |

**Current: 36 tables. Target: ~52 tables (22 new, several renames, 15 deprecated).**

**If you can only do three things:**
1. P0: Stabilize FKs + hash API keys + add billing idempotency
2. P1: Create usage_records for analytics
3. P2: Create billing_subscriptions for single subscription truth
