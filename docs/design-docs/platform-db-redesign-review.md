# Platform Database Redesign — Review & Findings

Related docs:

- [Platform Database Redesign](./platform-database-redesign.md) (source proposal)
- [Design Documents Index](./index.md)

## Purpose

This document reviews the platform database redesign proposal against the **actual current schema** (45 tables as of 2026-03-17) and provides:

- a gap analysis (what the proposal missed)
- prioritized assessment of each missing table
- recommended implementation order
- corrections to the proposal

## Current State vs. Proposal

The redesign proposal inventoried 37 tables. The actual codebase has **45 tables**. Many proposed changes have **already been implemented**:

### Already Implemented

| Proposed Table | Current Table | Status |
|----------------|---------------|--------|
| `billing_customers` | `billing_customers` | Exists |
| `credit_ledger` | `credit_ledger` | Exists (BIGINT IDENTITY PK, Decimal(18,6)) |
| `usage_records` | `usage_records` | Exists (BIGINT IDENTITY PK, full token breakdown) |
| `chat_runs` | `chat_runs` | Exists (lifecycle per chat turn) |
| `chat_summaries` | `chat_summaries` | Exists (renamed from `conversation_summaries`) |
| `chat_provider_containers` | `chat_provider_containers` | Exists (renamed from `provider_containers`) |
| `chat_provider_files` | `chat_provider_files` | Exists (renamed from `provider_files`) |
| `chat_provider_vector_stores` | `chat_provider_vector_stores` | Exists (renamed from `provider_vector_stores`) |
| `agent_event_log` | `agent_event_log` | Exists (renamed from `agent_run_events`) |
| `agent_summaries` | `agent_summaries` | Exists (renamed from `session_summaries`) |
| `agent_sandboxes` | `agent_sandboxes` | Exists (renamed from `sandboxes`) |
| `agent_ui_events` | `agent_events` | Exists (table name `agent_events`, model class `AgentUIEvent`) |

### Tables Missing From Proposal Inventory

These tables exist in the codebase but were not listed in the proposal's "Current Table Inventory":

| Table | Domain | Notes |
|-------|--------|-------|
| `credit_balances` | Billing | Materialized balance per user (Decimal(18,6)), replaces `users.credits` |
| `credit_reservations` | Billing | Reserve-settle-release state machine for all billable work |
| `billing_usage_facts` | Billing | Durable outbox for settlement recovery |
| `billing_customers` | Billing | Already exists, proposal treats it as new |
| `llm_invocations` | Telemetry | Append-only LLM call telemetry |
| `tool_invocations` | Telemetry | Append-only tool execution telemetry |
| `chat_runs` | Chat | Already exists, proposal treats it as new |
| `session_pins` | Sessions | User-to-session pin relationship (not mentioned in proposal at all) |

The proposal was written against a stale snapshot. Any implementation plan must reconcile against the actual 45-table schema.

## Missing Tables — Prioritized Assessment

### Tier 1: High Value, Do First

#### 1. `project_secrets` (split from `projects.secrets_json`)

**Priority: Critical.**

Storing secrets as embedded JSONB on the projects row prevents individual secret rotation, auditing, and ACL. This is the most concerning anti-pattern in the current schema.

Proposed fields are sensible. Recommendations:

- Prefer `secret_ref` (pointer to GCP Secret Manager) over `encrypted_value` in Postgres. The codebase already has `core/secrets/` for GCP SM — use the same pattern.
- Add `version` or `secret_version` for rotation tracking.
- `deleted_at` is appropriate here for audit trail.

```
project_secrets
├── id              UUID PK
├── project_id      FK → projects.id
├── environment     VARCHAR (production, staging, etc.)
├── secret_key      VARCHAR
├── secret_ref      VARCHAR (GCP SM path, not raw value)
├── version         INTEGER (rotation tracking)
├── created_by_user_id  FK → users.id
├── created_at
├── updated_at
└── deleted_at      (nullable, audit trail)
```

#### 2. `session_shares` (split from `sessions`)

**Priority: High.**

Currently `is_public`, `public_url` live on sessions. Sharing is a distinct concern from session lifecycle. Clean, low-risk split.

Proposed fields are good. Additions:

- Add `created_by_user_id` for audit.
- Consider `expires_at` for time-limited shares.

```
session_shares
├── id              UUID PK
├── session_id      FK → sessions.id
├── visibility      VARCHAR (public, unlisted, private)
├── share_token     VARCHAR UNIQUE
├── public_url      VARCHAR
├── created_by_user_id  FK → users.id
├── created_at
├── expires_at      (nullable)
└── revoked_at      (nullable)
```

#### 3. `llm_provider_credentials` + `llm_profiles` (split from `llm_settings`)

**Priority: High.**

`llm_settings` currently mixes provider auth (`encrypted_api_key`, `base_url`, `api_type`) with model preferences (`temperature`, `thinking_tokens`, `max_retries`). Splitting lets users have multiple profiles pointing to the same credential.

Migration concern: sessions currently FK to `llm_settings.id`. After the split, sessions should FK to `llm_profiles.id`, and each profile optionally FKs to `llm_provider_credentials.id`.

The `credential_id nullable for system models` design is correct — system-provided models don't need user-provided credentials.

```
llm_provider_credentials
├── id              UUID PK
├── user_id         FK → users.id
├── provider        VARCHAR (anthropic, openai, google, etc.)
├── api_type        VARCHAR
├── encrypted_api_key  VARCHAR
├── base_url        VARCHAR (nullable)
├── credential_metadata  JSONB (nullable)
├── is_active       BOOLEAN
├── created_at
└── updated_at

llm_profiles
├── id              UUID PK
├── user_id         FK → users.id
├── credential_id   FK → llm_provider_credentials.id (nullable for system models)
├── name            VARCHAR
├── model           VARCHAR
├── temperature     FLOAT
├── thinking_tokens BIGINT (nullable)
├── max_retries     BIGINT
├── max_message_chars  BIGINT
├── is_default      BOOLEAN
├── is_active       BOOLEAN
├── profile_metadata  JSONB (nullable)
├── created_at
└── updated_at
```

#### 4. `project_storage_resources` (split from `projects.storage_json`)

**Priority: High.**

Same rationale as `project_secrets`. GCS buckets and storage configs shouldn't be an opaque JSON blob on the project row.

Recommendation: make `resource_type` an enum (`gcs_bucket`, `cloud_sql`, etc.) for query filtering.

```
project_storage_resources
├── id              UUID PK
├── project_id      FK → projects.id
├── provider        VARCHAR (gcs, s3, etc.)
├── resource_type   VARCHAR ENUM (gcs_bucket, cloud_sql, etc.)
├── resource_identifier  VARCHAR
├── metadata        JSONB (nullable)
├── created_at
└── updated_at
```

### Tier 2: Medium Value, Good Design

#### 5. `presentations` (new root for slides)

**Priority: Medium.**

Currently `slide_contents` uses `presentation_name` as a string key with a unique constraint on `(session_id, presentation_name, slide_number)`. There's no root entity. This makes it hard to rename a presentation or query all presentations for a session without `DISTINCT presentation_name`.

Adding a `presentations` root table is correct normalization. Pairs with renaming `slide_contents` → `presentation_slides` and `slide_versions` → `presentation_slide_versions`.

```
presentations
├── id              UUID PK
├── session_id      FK → sessions.id
├── name            VARCHAR
├── created_at
└── updated_at
```

#### 6. `storybook_versions` (split from `storybooks`)

**Priority: Medium.**

Currently `storybooks` has `version`, `root_storybook_id`, `parent_storybook_id` — the version chain is self-referential on the root table. Splitting versions into a child table is cleaner.

The `storybook_version_pages` addition (replacing `storybook_page_links` with a `position` column) is also good — the current junction table has no ordering.

```
storybook_versions
├── id              UUID PK
├── storybook_id    FK → storybooks.id
├── version         BIGINT
├── parent_version_id  FK → storybook_versions.id (nullable)
├── style_json      JSONB (nullable)
└── created_at

storybook_version_pages
├── storybook_version_id  FK → storybook_versions.id  (composite PK)
├── page_id              FK → storybook_pages.id      (composite PK)
└── position             INTEGER
```

#### 7. `billing_events` (evolve from `billing_transactions`)

**Priority: Medium-Low.**

The rename from "transactions" to "events" is semantically correct — these are Stripe webhook events, not financial transactions. The proposed schema generalizes `provider` beyond Stripe, which is forward-looking.

Low risk. Schedule as a rename migration when convenient.

#### 8. `billing_subscriptions` (split from `billing_customers`)

**Priority: Conditional.**

`billing_customers` currently has `subscription_plan`, `subscription_status`, `subscription_billing_cycle`, `subscription_current_period_end` inline. The split is only valuable if:

- A customer can have multiple subscriptions (plan upgrade history, addon subscriptions)
- You need subscription lifecycle history

If subscriptions are always 1:1 with billing customers, keep them inline and add a `subscription_history` append-only table later if needed.

**Verdict: Defer unless multi-subscription support is planned.**

### Tier 3: Lower Value / Needs Product Direction

#### 9. `agent_plans`, `agent_milestones`, `agent_requirements`

**Priority: Product-dependent.**

These are entirely new product concepts, not schema restructuring.

- `agent_plans`: Only valuable if plans are user-visible, editable, or need version history. If plans are ephemeral in-memory state, use `agent_event_log` payloads instead.
- `agent_milestones`: Same question — product feature or internal telemetry? If telemetry, `agent_event_log` already covers it.
- `agent_requirements`: The schema (`requirement_type`, `status`, `payload`) is too generic — essentially a key-value store. If HITL is a real product need, model it more specifically (e.g., `agent_user_approvals` with typed fields for what's being approved).

**Verdict: Only implement when these become product features. Don't create empty tables speculatively.**

#### 10. `user_profiles` (split from `users`)

**Priority: Defer.**

Moving `first_name`, `last_name`, `avatar_url`, `language` to a 1:1 extension table is textbook identity/profile separation. However:

- **High migration cost, low immediate benefit.** Every query that renders a user's name now needs a join.
- The real problem on `users` is the **redundant billing columns** (`credits`, `bonus_credits`, `stripe_customer_id`, `subscription_*`), which are already duplicated in `credit_balances` and `billing_customers`.
- The remaining profile columns aren't heavy enough to justify a separate table.

**Verdict: Drop the redundant billing columns from `users` instead. Defer the profile split.**

#### 11. `apple_accounts` + `apple_build_credentials` (split from `apple_credentials`)

**Priority: Feature-dependent.**

The split is clean: auth/session state vs. build/deploy credentials. Only matters if the mobile feature is actively used. If experimental/low-usage, the migration cost outweighs the benefit.

#### 12. Renames Only (Low Priority)

These are cosmetic improvements that can be batched:

| Current | Target | Notes |
|---------|--------|-------|
| `mcp_settings` | `mcp_server_configs` | Pure rename |
| `session_wishlists` | `session_bookmarks` | Pure rename |
| `project_custom_domains` | `project_domains` | Pure rename |
| `connectors` | `integration_connections` | Rename + encrypt tokens |
| `application_configs` | `system_configs` | Pure rename |
| `agent_run_tasks` | `agent_runs` | Pure rename |
| `agent_run_messages` | `agent_run_snapshots` | Pure rename |
| `waitlist` | `waitlist_entries` | Pure rename |
| `api_keys` | `user_api_keys` | Rename + add `api_key_hash`, `name`, `last_used_at`, `expires_at` |

## What the Redesign Gets Right

1. **Slimming `sessions`** — removing `sandbox_id`, `agent_state_path`, `state_storage_url`, `is_public`, `public_url`, token counters. The session should be a shell.
2. **Domain prefixing** — `chat_*`, `agent_*`, `project_*` naming is already mostly in place. Finishing the remaining renames is good hygiene.
3. **NUMERIC over FLOAT** — the billing system already uses `Numeric(18,6)`. The remaining `Float` on `users.credits` and `users.bonus_credits` should be dropped (they're redundant with `credit_balances`).
4. **FK fix** — `project_databases` should FK to `projects.id` not `sessions.id`. This is a real bug in the current schema.
5. **Presentation root table** — correct normalization for slides.
6. **Storybook version split** — removes confusing self-referential version chain.

## What the Redesign Misses or Gets Wrong

1. **Stale inventory.** The proposal lists 37 tables but 45 exist. 8 tables (`credit_balances`, `credit_reservations`, `billing_usage_facts`, `billing_customers`, `llm_invocations`, `tool_invocations`, `chat_runs`, `session_pins`) are not accounted for.
2. **`user_profiles` is over-splitting.** The real fix is dropping redundant billing columns from `users`, not extracting profile columns.
3. **`session_pins` is unaddressed.** This table exists but isn't in the redesign. Decision needed: keep, merge into `session_bookmarks`, or drop.
4. **`billing_subscriptions` may be premature** if subscriptions are always 1:1 with billing customers.
5. **`agent_requirements` is too generic.** A `(requirement_type, status, payload)` schema is a key-value store. Model HITL more specifically if it's a real product need.
6. **No mention of `credit_reservations`** — this is a core billing table with a complex state machine. The redesign should acknowledge it.
7. **No mention of `billing_usage_facts`** — the durable outbox is a critical reliability mechanism. The redesign should acknowledge it.

## Recommended Implementation Order

| Phase | Tables | Effort | Impact |
|-------|--------|--------|--------|
| 1 | Drop redundant billing columns from `users` | 1 day | Eliminates source-of-truth confusion |
| 2 | Fix `project_databases` FK → `projects.id` | 1 day | Corrects broken domain boundary |
| 3 | `project_secrets` | 2 days | Eliminates secrets-in-JSONB anti-pattern |
| 4 | `session_shares` | 1 day | Clean split, low risk |
| 5 | `llm_provider_credentials` + `llm_profiles` | 3 days | Highest-impact split for user-facing config |
| 6 | `presentations` | 2 days | Normalizes slide domain |
| 7 | `storybook_versions` + `storybook_version_pages` | 2 days | Removes self-referential version chain |
| 8 | `project_storage_resources` | 1 day | Extracts from JSONB blob |
| 9 | Batch renames (connectors, mcp_settings, etc.) | 2 days | Cosmetic consistency |
| 10 | `agent_plans` / `agent_milestones` / `agent_requirements` | TBD | Only when product direction is clear |

## Open Questions

1. What should happen to `session_pins`? Keep, merge into `session_bookmarks`, or drop?
2. Is multi-subscription support planned? (Determines whether `billing_subscriptions` split is needed.)
3. Are agent plans/milestones becoming user-facing features? (Determines whether Tier 3 tables are needed.)
4. Should `project_databases` migration also add a `project_id` column, or replace `session_id` entirely? (The project can be looked up via `sessions.id → projects.session_id`, but a direct FK is cleaner.)
