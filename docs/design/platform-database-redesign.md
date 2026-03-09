# Platform Database Redesign

Related docs:

- [Chat and Agent Application Design](./chat-agent-application-design.md)
- [Chat and Agent DB Ownership Design](./chat-agent-db-ownership.md)
- [Platform Target Schema](./platform-target-schema.md)

## Scope

This document proposes a full database redesign for the current application.

It covers the 37 current persisted tables and recommends:

- clearer ownership boundaries by domain
- a slimmer shared `sessions` shell
- separate chat and agent persistence
- removal of overloaded aggregate tables
- better integrity, naming, and migration rules

This is a logical redesign.

It does not require multiple PostgreSQL schemas.
I would keep one physical schema and use explicit domain prefixes:

- `chat_*`
- `agent_*`
- `project_*`
- `billing_*`
- `integration_*`

## Core Diagnosis

The biggest structural problem is not the number of tables.
It is that several root tables are carrying state they do not own.

The most overloaded tables are:

- `sessions`
- `users`
- `projects`
- `events`

### `sessions` Is Overloaded

Today `sessions` mixes:

- ownership
- visibility
- chat summary pointers
- agent workspace pointers
- sandbox pointers
- prompt/completion token counters
- cost accumulation

That is too much for a shared shell table.

### `users` Is Also Overloaded

Today `users` mixes:

- identity
- profile
- subscription state
- Stripe customer state
- credit balance
- bonus credit balance
- language/preferences

Identity and billing should not live in the same root row.

### `projects` Is Carrying Secret And Resource State Inline

Today `projects` stores:

- metadata
- database config JSON
- storage config JSON
- secrets JSON
- deployment pointer
- build status

Secrets and external resources should not be embedded JSON on the root project row.

### Generic Table Names Hide Ownership

These names are too generic for a multi-application product:

- `events`
- `session_summaries`
- `provider_files`
- `provider_containers`

In practice, most of these are app-specific.

## Design Principles

### 1. Keep Internal IDs Consistent

Use native `UUID` for internal identifiers.

Use `TEXT` or `VARCHAR` only for:

- external provider IDs
- human-entered identifiers
- short codes

### 2. Use Root Shell Tables Sparingly

A root table should hold:

- identity
- ownership
- lifecycle shell metadata

It should not hold every child workflow state.

### 3. Separate Application State From Shared State

Shared domains:

- identity
- sessions
- billing
- files
- settings
- integrations

Application domains:

- chat
- agent
- content
- projects
- mobile deployment

### 4. Prefer Explicit Child Tables Over Large JSONB Blobs

Use JSONB only when the shape is legitimately external or unstable:

- raw provider payloads
- tool/provider metadata
- schemaless content attributes

Do not use JSONB for:

- secrets
- relationships
- core workflow state

### 5. Do Not Store Money In `FLOAT`

Use `NUMERIC`, or integer micros/cents.

This applies to:

- credits
- price/cost
- billed amounts

### 6. Soft Delete Only For User-Visible Roots

Soft delete belongs on tables like:

- `sessions`
- `projects`
- maybe `file_uploads`

Do not soft-delete everything by default.

### 7. Use Projections Explicitly

If a table is only a UI projection, name it that way.

Example:

- `agent_ui_events`

Not:

- `events`

## Current Table Inventory

Current persisted tables found in the codebase:

### Auth / Identity

- `users`
- `api_keys`
- `waitlist`

### Billing

- `billing_transactions`
- `session_metrics`

### Settings

- `llm_settings`
- `mcp_settings`

### Sessions

- `sessions`
- `session_wishlists`

### Chat

- `chat_messages`
- `provider_containers`
- `provider_files`
- `provider_vector_stores`
- `conversation_summaries`

### Agent

- `agent_run_tasks`
- `agent_run_messages`
- `agent_run_events`
- `session_summaries`
- `sandboxes`
- `application_configs`
- `events`

### Files

- `file_uploads`

### Projects

- `projects`
- `project_deployments`
- `project_custom_domains`
- `project_databases`

### Content

- `storybooks`
- `storybook_page_links`
- `storybook_pages`
- `slide_contents`
- `slide_versions`
- `slide_templates`
- `media_templates`
- `skills`

### Integrations

- `connectors`
- `composio_profiles`

### Mobile

- `apple_credentials`

## Target Domain Layout

I would keep a single public schema, but redesign ownership like this:

```text
identity
├── users
├── user_profiles
├── user_api_keys
└── waitlist_entries

billing
├── billing_customers
├── billing_subscriptions
├── billing_events
├── credit_ledger
└── usage_records

settings
├── llm_provider_credentials
├── llm_profiles
└── mcp_server_configs

sessions
├── sessions
├── session_shares
└── session_bookmarks

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
├── agent_ui_events
├── agent_summaries
├── agent_sandboxes
├── agent_plans
├── agent_milestones
└── agent_requirements

files
└── file_uploads

projects
├── projects
├── project_deployments
├── project_domains
├── project_databases
├── project_secrets
└── project_storage_resources

content
├── presentations
├── presentation_slides
├── presentation_slide_versions
├── slide_templates
├── storybooks
├── storybook_versions
├── storybook_pages
├── storybook_version_pages
└── media_templates

skills
└── skills

integrations
├── integration_connections
└── composio_profiles

mobile
├── apple_accounts
└── apple_build_credentials

system
└── system_configs
```

## Global Standards

### Primary Keys

- use `UUID` primary keys for almost all new root tables
- use `BIGINT IDENTITY` only for append-heavy ledgers if you want locality

### Timestamps

Every mutable table should have:

- `created_at`
- `updated_at`

Optional where needed:

- `deleted_at`
- `started_at`
- `completed_at`
- `cancelled_at`
- `expired_at`

### Optimistic Locking

Use `version` only on high-contention rows:

- runs
- root session shell if multiple services mutate it
- configs

Do not put `version` everywhere by default.

### Naming

- root plural tables: `users`, `sessions`, `projects`
- app-prefixed state tables: `chat_runs`, `agent_runs`
- projection tables must say projection/UI in the name when relevant

## Domain Redesign

## Identity

### `users`

Keep `users`, but slim it to identity and account lifecycle.

Recommended fields:

- `id`
- `email`
- `password_hash`
- `role`
- `is_active`
- `email_verified`
- `login_provider`
- `organization`
- `created_at`
- `updated_at`
- `last_login_at`

Move out:

- `first_name`
- `last_name`
- `avatar`
- `language`
- `metadata`
- `stripe_customer_id`
- `subscription_plan`
- `subscription_status`
- `subscription_billing_cycle`
- `subscription_current_period_end`
- `credits`
- `bonus_credits`

### `user_profiles`

New table.

Purpose:

- display profile data
- user preferences that are not identity-critical

Suggested fields:

- `user_id` PK/FK
- `first_name`
- `last_name`
- `avatar_url`
- `language`
- `profile_metadata`
- `created_at`
- `updated_at`

### `user_api_keys`

Rename `api_keys` to `user_api_keys`.

Suggested improvements:

- store `api_key_hash`, not raw key if possible
- optional `name`
- optional `last_used_at`
- optional `expires_at`

### `waitlist_entries`

Rename `waitlist` to `waitlist_entries`.

Keep it simple:

- `email`
- `created_at`

## Billing

Billing is currently under-modeled and partly embedded in `users`.

### `billing_customers`

New table.

Purpose:

- provider customer mapping per user

Suggested fields:

- `id`
- `user_id`
- `provider`
- `external_customer_id`
- `customer_metadata`
- `created_at`
- `updated_at`

### `billing_subscriptions`

New table.

Purpose:

- subscription lifecycle

Suggested fields:

- `id`
- `billing_customer_id`
- `provider_subscription_id`
- `plan_code`
- `status`
- `billing_cycle`
- `current_period_start`
- `current_period_end`
- `cancel_at`
- `cancelled_at`
- `created_at`
- `updated_at`

### `billing_events`

Evolve `billing_transactions` into `billing_events`.

Reason:

The current row is really event-driven Stripe state, not a normalized financial
transaction ledger.

Suggested fields:

- `id`
- `user_id`, nullable when unknown
- `provider`
- `provider_event_id`
- `provider_object_id`
- `event_type`
- `amount_numeric`
- `currency`
- `raw_payload`
- `processed_at`
- `created_at`

### `credit_ledger`

New table.

Purpose:

- authoritative balance changes

Suggested fields:

- `id`
- `user_id`
- `entry_type`
- `source_domain`
- `source_id`
- `delta_credits NUMERIC`
- `balance_after`, optional
- `metadata`
- `created_at`

This replaces the idea that balance should live as a mutable float on `users`.

### `usage_records`

New table.

Purpose:

- normalized usage per billable unit

Suggested fields:

- `id`
- `user_id`
- `session_id`
- `app_kind`
- `run_id`
- `source_table`
- `model_id`
- `provider`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `cost_usd NUMERIC`
- `credits_delta NUMERIC`
- `created_at`

This replaces `session_metrics` as the authoritative usage store.

`session_metrics` can become a derived summary or disappear entirely.

## Settings

### `llm_provider_credentials`

Split from `llm_settings`.

Purpose:

- provider credential storage

Suggested fields:

- `id`
- `user_id`
- `provider`
- `api_type`
- `encrypted_api_key`
- `base_url`
- `credential_metadata`
- `is_active`
- `created_at`
- `updated_at`

### `llm_profiles`

Split from `llm_settings`.

Purpose:

- reusable model/profile presets

Suggested fields:

- `id`
- `user_id`
- `credential_id`, nullable for system models
- `name`
- `model`
- `temperature`
- `thinking_tokens`
- `max_retries`
- `max_message_chars`
- `is_default`
- `is_active`
- `profile_metadata`
- `created_at`
- `updated_at`

Sessions should reference `llm_profile_id`, not a mixed credential/config row.

### `mcp_server_configs`

Rename `mcp_settings`.

Purpose:

- user-owned MCP server definitions

Suggested fields:

- `id`
- `user_id`
- `name`
- `config_json`
- `metadata`
- `is_active`
- `created_at`
- `updated_at`

## Sessions

### `sessions`

Keep this table, but reduce it to the session shell.

Suggested fields:

- `id`
- `user_id`
- `app_kind`
- `name`
- `status`
- `llm_profile_id`
- `parent_session_id`, nullable
- `session_metadata`
- `last_message_at`
- `created_at`
- `updated_at`
- `deleted_at`

Move out:

- `sandbox_id`
- `agent_state_path`
- `state_storage_url`
- `public_url`
- `is_public`
- `summary_message_id`
- `prompt_tokens`
- `completion_tokens`
- `cost`
- `agent_type` as app discriminator

If agent subtype is still needed, keep it in agent-owned tables.

### `session_shares`

New table.

Purpose:

- public/session-sharing state

Suggested fields:

- `id`
- `session_id`
- `visibility`
- `share_token`
- `public_url`
- `created_at`
- `revoked_at`

This is cleaner than embedding `is_public` and `public_url` on `sessions`.

### `session_bookmarks`

Rename `session_wishlists`.

Purpose:

- user-to-session bookmark relationship

Suggested fields:

- `user_id`
- `session_id`
- `created_at`

## Chat

### `chat_runs`

New table and the missing boundary in the current model.

Purpose:

- lifecycle of a single chat turn

Suggested fields:

- `id`
- `session_id`
- `user_message_id`
- `assistant_message_id`
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

### `chat_messages`

Keep this table.

Suggested improvements:

- `session_id` as real FK
- `run_id` FK -> `chat_runs.id`
- `parent_message_id` FK -> `chat_messages.id`
- `role`
- `content`
- `usage`
- `tokens`
- `model`
- `tools`
- `metadata`
- `provider_metadata`
- `file_ids`
- `is_finished`
- `finish_reason`
- timestamps

### `chat_summaries`

Rename `conversation_summaries`.

Purpose:

- rolling chat context compression

Suggested fields:

- `id`
- `session_id`
- `end_message_id`
- `summary_text`
- `original_tokens`
- `summary_tokens`
- `compression_ratio`
- `model_id`
- `parent_summary_id`
- `created_at`

### `chat_provider_containers`

Rename `provider_containers`.

Purpose:

- provider-side code interpreter or container session state

### `chat_provider_files`

Rename `provider_files`.

Purpose:

- provider-side file mapping for chat

Suggested change:

- `file_id` should FK `file_uploads.id` where possible

### `chat_provider_vector_stores`

Rename `provider_vector_stores`.

Purpose:

- provider-side retrieval/vector handles for chat

## Agent

### `agent_runs`

Rename `agent_run_tasks`.

Purpose:

- canonical lifecycle of agent runs

Suggested fields:

- `id`
- `session_id`
- `parent_run_id`
- `origin_message_id`
- `status`
- `error_message`
- `started_at`
- `completed_at`
- `created_at`
- `updated_at`
- `version`

### `agent_run_snapshots`

Rename `agent_run_messages`.

Purpose:

- resumable runtime state, not visible chat messages

Suggested fields:

- `id`
- `run_id`
- `session_id`
- `parent_run_id`
- `model_id`
- `status`
- `run_input`
- `messages`
- `metrics`
- `additional_info`
- `tools`
- `created_at`
- `updated_at`
- `version`

### `agent_event_log`

Rename `agent_run_events`.

Purpose:

- append-only audit log

Suggested fields:

- `id`
- `session_id`
- `run_id`
- `event_group`
- `event_name`
- `payload`
- `created_at`

### `agent_ui_events`

Evolve `events` into an explicitly agent-owned projection table, or remove it.

Use it only if the frontend still needs a filtered, transport-friendly event
projection distinct from the audit log.

### `agent_summaries`

Rename `session_summaries`.

Purpose:

- agent memory / summary state

Suggested fields:

- `id`
- `session_id`
- `run_id`
- `content`
- `topics`
- `metrics`
- `created_at`
- `updated_at`
- `version`

### `agent_sandboxes`

Rename `sandboxes`.

Purpose:

- sandbox allocation and lifecycle

Suggested fields:

- `id`
- `session_id`
- `provider`
- `provider_sandbox_id`
- `status`
- `provider_data`
- `created_at`
- `updated_at`
- `expired_at`
- `version`

### `agent_plans`

New table if plans are now a real product object.

Suggested fields:

- `id`
- `run_id`
- `session_id`
- `revision`
- `plan_json`
- `created_at`
- `updated_at`

### `agent_milestones`

New table if milestone tracking is first-class.

Suggested fields:

- `id`
- `plan_id`
- `run_id`
- `position`
- `status`
- `title`
- `details`
- `created_at`
- `updated_at`

### `agent_requirements`

New table for HITL and waiting states.

Suggested fields:

- `id`
- `run_id`
- `requirement_type`
- `status`
- `payload`
- `resolved_at`
- `created_at`
- `updated_at`

### `system_configs`

Rename `application_configs`.

Purpose:

- global feature toggles and system config

This should belong to system/core, not `engine.v1`.

## Files

### `file_uploads`

Keep this table, but strengthen it.

Suggested fields:

- `id`
- `user_id`
- `session_id`, nullable
- `file_name`
- `file_size`
- `content_type`
- `storage_provider`
- `storage_path`
- `checksum`
- `source_app_kind`
- `created_at`
- `deleted_at`, optional

This table should represent the platform file, not provider-side copies.

## Projects

### `projects`

Keep `projects`, but reduce it to project identity and root metadata.

Suggested fields:

- `id`
- `user_id`
- `session_id`
- `name`
- `description`
- `status`
- `framework`
- `project_path`
- `production_url`
- `current_production_deployment_id`
- `created_at`
- `updated_at`
- `deleted_at`

Move out:

- `database_json`
- `storage_json`
- `secrets_json`
- most build/runtime detail

### `project_deployments`

Keep this table.

It is one of the better current tables.

Suggested improvements:

- keep `project_id`
- keep deployment lifecycle fields
- keep provider/version/snapshot
- keep metadata and error details
- add explicit unique constraint on `(project_id, version)` if version is canonical

### `project_domains`

Rename `project_custom_domains`.

Purpose:

- domain assignment and DNS/SSL state

Suggested fields:

- `id`
- `project_id`
- `deployment_id`, nullable
- `domain_kind`
- `subdomain`
- `full_domain`
- `dns_status`
- `ssl_status`
- `provider_record_id`
- `claimed_by_user_id`
- `claimed_at`
- `created_at`
- `updated_at`

### `project_databases`

Keep the concept, but rekey it.

Current problem:

- it hangs off `session_id`

Target:

- `project_id` FK -> `projects.id`

Suggested fields:

- `id`
- `project_id`
- `environment`
- `source`
- `connection_string`
- `host`
- `database_name`
- `role_name`
- `branch_name`
- `is_active`
- `metadata`
- `created_at`
- `updated_at`

### `project_secrets`

New table.

Purpose:

- replace `projects.secrets_json`

Suggested fields:

- `id`
- `project_id`
- `environment`
- `secret_key`
- `secret_ref` or `encrypted_value`
- `created_by_user_id`
- `created_at`
- `updated_at`
- `deleted_at`, optional

### `project_storage_resources`

New table.

Purpose:

- replace `projects.storage_json`

Suggested fields:

- `id`
- `project_id`
- `provider`
- `resource_type`
- `resource_identifier`
- `metadata`
- `created_at`
- `updated_at`

## Content

## Presentations / Slides

The current slides schema is not normalized enough because presentation
identity is embedded in `presentation_name` strings.

### `presentations`

New root table.

Suggested fields:

- `id`
- `session_id`
- `name`
- `created_at`
- `updated_at`

### `presentation_slides`

Replaces `slide_contents`.

Suggested fields:

- `id`
- `presentation_id`
- `slide_number`
- `title`
- `content_html`
- `metadata`
- `created_at`
- `updated_at`

### `presentation_slide_versions`

Replaces `slide_versions`.

Suggested fields:

- `id`
- `presentation_slide_id`
- `version`
- `root_version_id`
- `parent_version_id`
- `image_url`
- `thumbnail_url`
- `edit_summary`
- `instructions_applied`
- `created_at`

### `slide_templates`

Keep this table.

It already behaves like a template catalog.

## Storybooks

Current `storybooks` mixes root storybook identity with version chain data.

### `storybooks`

Keep as the root aggregate only.

Suggested fields:

- `id`
- `session_id`
- `name`
- `aspect_ratio`
- `resolution`
- `created_at`
- `updated_at`

### `storybook_versions`

New table.

Suggested fields:

- `id`
- `storybook_id`
- `version`
- `parent_version_id`
- `style_json`
- `created_at`

### `storybook_pages`

Keep this table.

Suggested fields:

- `id`
- `page_number`
- `image_url`
- `html_content`
- `text_content`
- `audio_url`
- `metadata`
- `created_at`
- `updated_at`

### `storybook_version_pages`

Rename `storybook_page_links`.

Purpose:

- attach ordered pages to a storybook version

Suggested fields:

- `storybook_version_id`
- `page_id`
- `position`

## Templates

### `media_templates`

Keep this table.

It already behaves like a content/template catalog.

## Skills

### `skills`

Keep this table, but move ownership out of `content`.

Skills are not content products.
They are agent capabilities.

Suggested improvements:

- keep builtin vs user-owned distinction
- keep source metadata
- keep `skill_md_content`
- consider extracting `skill_versions` later if editing/versioning matters

## Integrations

### `integration_connections`

Rename `connectors`.

Suggested improvements:

- encrypt `access_token`
- encrypt `refresh_token`
- keep provider metadata separately
- keep unique constraint on `(user_id, integration_type)`

Suggested fields:

- `id`
- `user_id`
- `integration_type`
- `encrypted_access_token`
- `encrypted_refresh_token`
- `token_expiry`
- `metadata`
- `created_at`
- `updated_at`

### `composio_profiles`

Keep the concept, but keep it under integrations.

Suggested improvements:

- make status enum explicit
- keep default profile constraints
- continue to store encrypted MCP URL only

## Mobile

### `apple_accounts`

Split from `apple_credentials`.

Purpose:

- Apple auth/session state per user/account

Suggested fields:

- `id`
- `user_id`
- `apple_id`
- `auth_state`
- `encrypted_session_data`
- `selected_team_id`
- `team_name`
- `available_teams`
- `session_expiry`
- `created_at`
- `updated_at`

### `apple_build_credentials`

Split from `apple_credentials`.

Purpose:

- deploy/build credentials and certificates

Suggested fields:

- `id`
- `apple_account_id`
- `encrypted_expo_token`
- `encrypted_app_specific_password`
- `encrypted_ios_p12`
- `encrypted_ios_p12_password`
- `encrypted_ios_provisioning_profile`
- `ios_bundle_identifier`
- `ios_certificate_id`
- `ios_certificate_expiry`
- `created_at`
- `updated_at`

## Current To Target Mapping

| Current Table | Target Table(s) | Action |
| --- | --- | --- |
| `users` | `users`, `user_profiles`, `billing_customers`, `billing_subscriptions`, `credit_ledger` | split |
| `api_keys` | `user_api_keys` | rename + harden |
| `waitlist` | `waitlist_entries` | rename |
| `billing_transactions` | `billing_events` | rename/evolve |
| `session_metrics` | `usage_records` | replace |
| `llm_settings` | `llm_provider_credentials`, `llm_profiles` | split |
| `mcp_settings` | `mcp_server_configs` | rename/evolve |
| `sessions` | `sessions`, `session_shares` | slim + split |
| `session_wishlists` | `session_bookmarks` | rename |
| `chat_messages` | `chat_messages` | keep + strengthen |
| `provider_containers` | `chat_provider_containers` | rename |
| `provider_files` | `chat_provider_files` | rename |
| `provider_vector_stores` | `chat_provider_vector_stores` | rename |
| `conversation_summaries` | `chat_summaries` | rename |
| `agent_run_tasks` | `agent_runs` | rename |
| `agent_run_messages` | `agent_run_snapshots` | rename |
| `agent_run_events` | `agent_event_log` | rename |
| `session_summaries` | `agent_summaries` | rename |
| `sandboxes` | `agent_sandboxes` | rename |
| `events` | `agent_ui_events` or remove | rename/remove |
| `application_configs` | `system_configs` | rename |
| `file_uploads` | `file_uploads` | keep + strengthen |
| `projects` | `projects`, `project_secrets`, `project_storage_resources` | slim + split |
| `project_deployments` | `project_deployments` | keep |
| `project_custom_domains` | `project_domains` | rename |
| `project_databases` | `project_databases` | keep + rekey to `project_id` |
| `storybooks` | `storybooks`, `storybook_versions` | split |
| `storybook_page_links` | `storybook_version_pages` | rename/evolve |
| `storybook_pages` | `storybook_pages` | keep |
| `slide_contents` | `presentations`, `presentation_slides` | replace |
| `slide_versions` | `presentation_slide_versions` | rename/evolve |
| `slide_templates` | `slide_templates` | keep |
| `media_templates` | `media_templates` | keep |
| `skills` | `skills` | keep, move ownership |
| `connectors` | `integration_connections` | rename + harden |
| `composio_profiles` | `composio_profiles` | keep/evolve |
| `apple_credentials` | `apple_accounts`, `apple_build_credentials` | split |

## Foreign Key Rules

Minimum target rules:

- every app run points to `sessions.id`
- every session points to `users.id`
- every project child points to `projects.id`
- every content artifact that is session-scoped points to `sessions.id`
- provider mapping tables point to both the local owning row and the external ID when possible
- `project_databases` must point to `projects.id`, not `sessions.id`
- `chat_messages.run_id` points to `chat_runs.id`
- `agent_run_snapshots.run_id` points to `agent_runs.id`

## What I Would Implement First

If this redesign is done incrementally, the highest-value order is:

1. split `sessions` from chat/agent state
2. split chat from agent tables
3. move billing state out of `users`
4. move secrets/storage/database config out of `projects`
5. normalize slides around `presentations`
6. rename generic projection tables to explicit owners

## Final Recommendation

The database should move from:

- a mixed session-centric schema with app-specific leakage

to:

- a domain-owned schema with a small shared session shell and explicit
  app-prefixed runtime tables

The most important changes are:

- `sessions` becomes a shell
- `chat` gets its own lifecycle tables
- `agent` keeps its own run/event/snapshot tables
- `users` loses billing state
- `projects` loses inline secrets/resources
- `slides` gain a real presentation root table
