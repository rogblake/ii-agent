# Database Schema Reference

Generated from SQLAlchemy models. All tables use `TimestampColumn` (TIMESTAMP WITH TIME ZONE) for datetime fields.

## Core Tables

### `users`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK, UUID default |
| email | String | UNIQUE |
| password_hash | String | nullable |
| first_name | String | nullable |
| last_name | String | nullable |
| avatar | String | nullable |
| role | String | default="user" |
| is_active | Boolean | default=True |
| email_verified | Boolean | default=False |
| login_provider | String | nullable |
| organization | String | nullable |
| stripe_customer_id | String | nullable |
| subscription_plan | String | nullable |
| subscription_status | String | nullable |
| subscription_billing_cycle | String | nullable |
| subscription_current_period_end | DateTime | nullable |
| credits | Float | default=0.0 |
| bonus_credits | Float | default=0.0 |
| language | String | default="en" |
| user_metadata | JSONB | nullable, column="metadata" |
| last_login_at | DateTime | nullable |
| created_at | TimestampColumn | server default |
| updated_at | TimestampColumn | server default |

**Indexes:** `idx_users_email`
**Relationships:** sessions, llm_settings, mcp_settings, file_uploads, api_keys, connectors, billing_transactions, billing_customers, projects, skills

### `sessions`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK, UUID default |
| user_id | String | FK → users.id, CASCADE |
| sandbox_id | String | nullable |
| version | BigInteger | default=0 (optimistic lock) |
| llm_setting_id | String | FK → llm_settings.id, nullable |
| name | String | nullable |
| status | String | default="active" |
| agent_state_path | String | nullable |
| state_storage_url | String | nullable |
| agent_type | String | nullable |
| app_kind | String | default="agent" |
| public_url | String | nullable |
| is_public | Boolean | default=False |
| api_version | String | default="v0" |
| parent_session_id | String | FK → sessions.id, nullable |
| session_metadata | JSONB | nullable |
| last_message_at | DateTime | nullable |
| deleted_at | DateTime | nullable (soft delete) |
| created_at | TimestampColumn | server default |
| updated_at | TimestampColumn | server default |

**Indexes:** `idx_sessions_user_id`, `idx_sessions_status`, `idx_sessions_created_at`
**Enums:** SessionStateEnum (PENDING, ACTIVE, PAUSE), AppKind (AGENT, CHAT)

## Billing Tables

### `credit_balances`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK, UUID default |
| user_id | String | FK → users.id, UNIQUE, CASCADE |
| credits | Decimal(18,6) | >= 0, default=0 |
| bonus_credits | Decimal(18,6) | >= 0, default=0 |
| billing_status | String | default="ok" |
| billing_status_reason | String | nullable |
| billing_status_updated_at | DateTime | nullable |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Enums:** BillingStatus (OK, RECONCILIATION_REQUIRED)

### `credit_ledger`
| Column | Type | Constraints |
|--------|------|------------|
| id | BigInteger | PK, Identity always=True |
| user_id | String | FK → users.id, CASCADE |
| entry_type | String | |
| source_domain | String | nullable |
| source_id | String | nullable |
| idempotency_key | String | UNIQUE partial index, nullable |
| delta_credits | Decimal(18,6) | |
| delta_bonus_credits | Decimal(18,6) | default=0 |
| balance_after_credits | Decimal(18,6) | nullable |
| balance_after_bonus_credits | Decimal(18,6) | nullable |
| entry_metadata | JSONB | nullable |
| created_at | TimestampColumn | |

**Indexes:** `idx_credit_ledger_user_created`, `idx_credit_ledger_source`, `idx_credit_ledger_entry_type`, `uq_credit_ledger_idempotency_key`
**Enums:** LedgerEntryType (INITIAL_BALANCE, DEDUCTION, GRANT, BONUS_GRANT, PLAN_CHANGE, REFRESH, RESERVATION_HOLD, RESERVATION_RELEASE)

### `credit_reservations`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK, UUID default |
| user_id | String | FK → users.id, CASCADE |
| session_id | String | nullable |
| run_id | UUID | nullable |
| source_domain | String | |
| source_id | String | |
| billing_kind | String | |
| quote_strategy | String | |
| status | String | |
| model_id | String | nullable |
| tool_name | String | nullable |
| idempotency_key | String | UNIQUE partial index, nullable |
| reserve_ledger_entry_id | BigInteger | FK → credit_ledger.id, nullable |
| release_ledger_entry_id | BigInteger | nullable |
| shortfall_ledger_entry_id | BigInteger | nullable |
| usage_record_id | BigInteger | FK → usage_records.id, nullable |
| reserved_credits | Decimal(18,6) | default=0 |
| reserved_bonus_credits | Decimal(18,6) | default=0 |
| actual_credits | Decimal(18,6) | nullable |
| actual_bonus_credits | Decimal(18,6) | nullable |
| released_credits | Decimal(18,6) | nullable |
| released_bonus_credits | Decimal(18,6) | nullable |
| quoted_usd | Decimal(18,6) | default=0 |
| max_usd | Decimal(18,6) | default=0 |
| actual_usd | Decimal(18,6) | nullable |
| reservation_metadata | JSONB | nullable |
| expires_at | DateTime | nullable |
| last_error | Text | nullable |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Indexes:** `idx_credit_reservations_user_created`, `idx_credit_reservations_source`, `idx_credit_reservations_status_expires`, `uq_credit_reservations_idempotency_key`
**Enums:** ReservationStatus (RESERVED, SETTLED, RELEASED, EXPIRED, SETTLEMENT_FAILED), BillingKind (LLM_USAGE, TOOL_USAGE), SourceDomain (CHAT_LLM, AGENT_LLM, CHAT_TOOL, AGENT_TOOL, VOICE_GENERATION, IMAGE_GENERATION, WEBHOOK, CRON), QuoteStrategy (EXACT, BOUNDED, POST_FACTO)

## Telemetry Tables

### `llm_invocations`
| Column | Type | Constraints |
|--------|------|------------|
| id | BigInteger | PK, Identity always=True |
| run_id | UUID | nullable |
| session_id | String | |
| user_id | String | |
| message_id | UUID | nullable |
| provider | String | nullable |
| model | String | nullable |
| request_kind | String | |
| prompt_tokens | BigInteger | default=0 |
| completion_tokens | BigInteger | default=0 |
| cache_read_tokens | BigInteger | default=0 |
| cache_write_tokens | BigInteger | default=0 |
| reasoning_tokens | BigInteger | default=0 |
| latency_ms | BigInteger | nullable |
| cost_usd | Decimal(18,6) | nullable |
| credits_charged | Decimal(18,6) | nullable |
| success | Boolean | default=True |
| error_code | String | nullable |
| finish_reason | String | nullable |
| created_at | TimestampColumn | |

**Indexes:** `idx_llm_invocations_run`, `idx_llm_invocations_session`, `idx_llm_invocations_model`, `idx_llm_invocations_user`

### `tool_invocations`
| Column | Type | Constraints |
|--------|------|------------|
| id | BigInteger | PK, Identity always=True |
| run_id | UUID | nullable |
| session_id | String | |
| user_id | String | |
| message_id | UUID | nullable |
| provider_tool_call_id | String | nullable |
| tool_name | String | |
| tool_namespace | String | nullable |
| status | String | |
| started_at | DateTime | nullable |
| finished_at | DateTime | nullable |
| latency_ms | BigInteger | nullable |
| input_summary | String | nullable |
| output_summary | String | nullable |
| is_error | Boolean | default=False |
| error_message | String | nullable |
| cost_usd | Numeric(18,6) | nullable |
| credits_charged | Numeric(18,6) | nullable |
| created_at | TimestampColumn | |

**Indexes:** `idx_tool_invocations_run`, `idx_tool_invocations_session`, `idx_tool_invocations_tool`

## Agent Tables

### `agent_run_tasks`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| session_id | String | FK → sessions.id |
| user_message_id | UUID | nullable |
| status | String | |
| error_message | String | nullable |
| version | BigInteger | optimistic lock |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Indexes:** `ix_agent_run_tasks_session_id`, `ix_agent_run_tasks_status`, `ix_agent_run_tasks_session_status`, `ix_agent_run_tasks_created_at`
**Status values:** PENDING, RUNNING, COMPLETED, PAUSED, ABORTING, ABORTED, FAILED, ERROR, SYSTEM_INTERRUPTED

### `agent_ui_events`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| session_id | String | FK → sessions.id |
| run_id | UUID | FK → agent_run_tasks.id, nullable |
| type | String | |
| content | JSONB | |
| source | String | nullable |
| created_at | TimestampColumn | |

**Indexes:** `idx_agent_events_session_id`, `idx_agent_events_created_at`, `idx_agent_events_type`

### `chat_runs`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| session_id | String | FK → sessions.id |
| user_message_id | UUID | nullable |
| assistant_message_id | UUID | nullable |
| model_id | String | nullable |
| provider | String | nullable |
| finish_reason | String | nullable |
| error_code | String | nullable |
| status | String | |
| error_message | String | nullable |
| started_at | DateTime | nullable |
| completed_at | DateTime | nullable |
| version | BigInteger | optimistic lock |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Status values:** RUNNING, COMPLETED, FAILED, ABORTED

### `chat_messages`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| session_id | String | FK → sessions.id |
| role | String | user/assistant/system/tool |
| content | JSONB | List of ContentPart |
| usage | JSONB | nullable, token stats |
| tokens | Integer | nullable, accumulated total |
| model | JSONB | nullable |
| tools | JSONB | nullable |
| message_metadata | JSONB | nullable |
| provider_metadata | JSONB | nullable |
| file_ids | ARRAY(UUID) | nullable |
| parent_message_id | UUID | FK → self, nullable |
| is_finished | Boolean | nullable |
| finish_reason | String | nullable |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Indexes:** `idx_chat_messages_session`, `idx_chat_messages_created`, `idx_chat_messages_parent`, `idx_chat_messages_session_created`

## Content Tables

### `slide_contents`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| session_id | String | FK → sessions.id |
| presentation_name | String | |
| slide_number | Integer | |
| slide_title | String | nullable |
| slide_content | Text | HTML content |
| slide_metadata | JSONB | nullable |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Unique:** `(session_id, presentation_name, slide_number)`

### `skills`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| user_id | String | FK → users.id, nullable (NULL = builtin) |
| name | String | |
| description | String | nullable |
| source | String | BUILTIN/GITHUB/CUSTOM |
| skill_md_content | Text | nullable |
| sandbox_path | String | nullable |
| storage_uri | String | nullable |
| allowed_tools | JSONB | nullable |
| license | String | nullable |
| compatibility | String | nullable |
| is_enabled | Boolean | default=True |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Unique:** `(user_id, name)` for user skills; partial unique on `name` WHERE `user_id IS NULL`

## Infrastructure Tables

### `api_keys`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK, UUID default |
| user_id | String | FK → users.id, CASCADE |
| api_key | String | UNIQUE |
| is_active | Boolean | default=True |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

### `file_uploads`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| user_id | String | FK → users.id |
| file_name | String | |
| file_size | Integer | |
| storage_path | String | |
| content_type | String | |
| session_id | String | FK → sessions.id, nullable |
| created_at | TimestampColumn | |

### `projects`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| user_id | String | FK → users.id |
| session_id | String | FK → sessions.id, UNIQUE |
| name | String | |
| description | String | nullable |
| status | String | |
| current_build_status | String | nullable |
| framework | String | nullable |
| project_path | String | nullable |
| production_url | String | nullable |
| database_json | JSONB | nullable |
| storage_json | JSONB | nullable |
| secrets_json | JSONB | nullable (encrypted) |
| custom_domain_id | String | FK → project_custom_domains.id, nullable |
| current_production_deployment_id | String | FK → project_deployments.id, nullable |
| deleted_at | DateTime | nullable (soft delete) |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

### `connectors`
| Column | Type | Constraints |
|--------|------|------------|
| id | String | PK |
| user_id | String | FK → users.id |
| connector_type | String | |
| access_token | String | nullable |
| refresh_token | String | nullable |
| token_expiry | DateTime | nullable |
| connector_metadata | JSONB | nullable |
| created_at | TimestampColumn | |
| updated_at | TimestampColumn | |

**Unique:** `(user_id, connector_type)`
**Enums:** ConnectorTypeEnum (GOOGLE_DRIVE, GITHUB, REVENUECAT, CHATGPT_MCP, COMPOSIO)

### `waitlist`
| Column | Type | Constraints |
|--------|------|------------|
| email | String | PK |
| created_at | TimestampColumn | |
