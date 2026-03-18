# Technical Debt Tracker

Known technical debt items, tracked so agents and engineers can prioritize cleanup work.

Last comprehensive review: 2026-03-17

---

## P0 — Critical (Security & Correctness)

### Project secrets can be persisted in plaintext
- **What:** `projects/service.py:141-154` writes `project.secrets_json = secrets` directly, while `projects/secrets/utils.py:7-27` supports encrypted payloads. Multiple agent tool paths merge raw secrets or `DATABASE_URL` into `project.secrets_json` and then call the project service instead of the secret service
- **Impact:** Secrets storage is mixed-mode. Some rows may be encrypted, others plaintext, depending on which code path last updated the project. This is a direct confidentiality risk for project secrets and database credentials
- **Fix:** Make `SecretService` the only persistence path for project secrets. Encrypt in the write service, reject plaintext payloads at the persistence boundary, and add a data migration to re-encrypt existing plaintext rows
- **Effort:** 1 day

### Production secret configuration is not fail-closed
- **What:** `core/secrets/encryption.py:107-128` falls back to hardcoded password/salt values when `ENCRYPTION_KEY` is unset, `core/config/settings.py:338-340` has a default JWT signing secret, and `core/config/oauth.py:132-135` auto-generates a session secret when not configured
- **Impact:** Production can boot with insecure or non-deterministic secrets. That weakens stored secret encryption, makes JWT signing misconfiguration easy to miss, and causes session invalidation/drift across restarts or multiple instances
- **Fix:** Add production-only config validation that requires explicit `ENCRYPTION_KEY`, `JWT_SECRET_KEY`, and `SESSION_SECRET_KEY`, and fail startup when any are missing or using placeholder values
- **Effort:** 4 hours

### Database TLS verification is effectively disabled
- **What:** `core/db/base.py:74-80` handles `sslmode=require`, `verify-ca`, and `verify-full` by building an SSL context with `check_hostname=False` and `verify_mode=CERT_NONE`
- **Impact:** The connection string can claim certificate verification semantics that the code does not actually enforce. This weakens database transport security and permits MITM-style trust failures
- **Fix:** Honor the requested verification mode correctly, or delegate TLS behavior to the driver defaults without overriding verification settings
- **Effort:** 4 hours

### CORS wildcard with credentials
- **What:** `app/middleware.py` sets `allow_origins=["*"]` with `allow_credentials=True`
- **Impact:** Violates CORS spec. Enables CSRF attacks — any malicious site can make authenticated requests on behalf of users
- **Fix:** Replace with explicit origin list from config (e.g., `settings.cors_allowed_origins`). Remove wildcard when `allow_credentials=True`
- **Effort:** 1 hour

### Session cookies transmitted over HTTP
- **What:** `app/middleware.py` sets `https_only=False` on `SessionMiddleware`
- **Impact:** OAuth state tokens and PKCE verifiers leak over unencrypted connections
- **Fix:** Set `https_only=True` for production, gate with `settings.environment != "local"`
- **Effort:** 1 hour

### Race condition in reservation idempotency retry
- **What:** `billing/reservations/service.py:112-161` — when a ledger insert fails due to idempotency conflict, the retry path fetches the existing reservation but does NOT re-verify credit sufficiency
- **Impact:** Between the first idempotency check and the ledger append, a concurrent transaction could exhaust the balance. Potential double-charging
- **Fix:** Re-lock and re-check balance after idempotency conflict before returning the existing reservation
- **Effort:** 4 hours

### Transaction scope issue in balance get_or_create
- **What:** `billing/credits/balance_repository.py:114-152` — pre-check `get_balance()` runs OUTSIDE the SAVEPOINT. Between check and insert, another request can insert first, causing `ON CONFLICT DO NOTHING` to succeed silently
- **Impact:** Could return incorrect `created` flag or cause duplicate ledger initialization
- **Fix:** Move the existence check inside the SAVEPOINT, or use `INSERT ... ON CONFLICT DO UPDATE SET ... RETURNING *` instead
- **Effort:** 4 hours

### No rate limiting on public endpoints
- **What:** `sessions/router.py:204-251`, `files/router.py:100-113` — public session and file download endpoints have no rate limiting
- **Impact:** Enables enumeration of public sessions and DoS against database
- **Fix:** Add `slowapi` or custom rate-limiting middleware keyed on IP
- **Effort:** 4 hours

### Public file download missing ownership validation
- **What:** `files/router.py:100-113` — only checks if session is public, not if `file_id` actually belongs to `session_id`
- **Impact:** If file IDs are guessable, attackers can download files from any public session
- **Fix:** Add `WHERE file_id = :file_id AND session_id = :session_id` to the query
- **Effort:** 2 hours

---

## P1 — High (Data Integrity & Performance)

### Project database source of truth is split across legacy JSON and normalized tables
- **What:** `projects/databases/service.py:92-119` still reads project database connections from `projects.database_json`, while tool flows also create and update rows in `project_databases` via `projects/databases/service.py:162-193`. `projects/service.py:33-79` also still writes `database_json`
- **Impact:** Two competing sources of truth can drift. Admin/dashboard queries become harder to trust, migrations remain partial, and operational fixes must know which storage path to inspect first
- **Fix:** Make `project_databases` the canonical store, migrate all reads to it, backfill fully, and retire `projects.database_json`
- **Effort:** 2-3 days

### Database resources are attached to sessions instead of projects
- **What:** `projects/databases/models.py:24-71` stores database resources under `session_id`, while `projects/models.py:85-89` enforces a unique `session_id` per project
- **Impact:** Durable infrastructure is coupled to a transient chat/workspace entity. This blocks cleaner project lifecycle management, future shared-project features, and long-lived admin operations
- **Fix:** Add `project_id` as the ownership FK for project databases and migrate the domain to treat sessions as activity containers rather than resource parents
- **Effort:** 3-5 days

### Backend database introspection is a network trust boundary risk
- **What:** `projects/databases/router.py:16-65` allows schema/record reads, and the service uses server-side `create_engine(connection_url)` against stored connection strings. Agent tooling also syncs user-provided `DATABASE_URL` values into project storage
- **Impact:** The app server can become a network pivot into arbitrary databases reachable from the backend plane. This is risky for production hardening and creates unclear trust boundaries
- **Fix:** Restrict introspection to platform-managed databases, or isolate it behind an allowlist / separate worker network with explicit egress controls
- **Effort:** 1-2 days

### App bootstrap is duplicated
- **What:** Both `ii_agent/app.py:67-225` and `ii_agent/app/__init__.py:22-88` implement overlapping application startup, while `ii_agent/ws_server.py:5-43` imports the package path
- **Impact:** Middleware, router registration, lifespan behavior, and startup side effects can drift between the two bootstraps. This increases regression risk and makes debugging startup behavior harder
- **Fix:** Keep a single canonical app factory and reduce the other path to a thin delegating shim or remove it entirely
- **Effort:** 1 day

### Missing database indexes
- **What:** Several FK columns lack indexes for efficient lookups
- **Tables affected:**
  - `file_uploads` — missing index on `user_id` and `session_id`
  - `sessions.deleted_at`, `projects.deleted_at` — no composite index for soft-delete filtering
  - `mcp_settings.user_id` — no explicit index
  - `media_templates.name` — no index, no unique constraint
- **Impact:** Full table scans on common queries as data grows
- **Fix:** Add indexes via Alembic migration
- **Effort:** 2 hours

### Error swallowing in outbox retry loop
- **What:** `billing/outbox/service.py:163-173` — exceptions in `_process_locked_fact()` are caught and logged, but `processed` counter still increments
- **Impact:** Failed facts counted as processed. Loss of billing visibility and incorrect retry metrics
- **Fix:** Only increment `processed` on success; track `failed` count separately
- **Effort:** 2 hours

### Stale read in shortfall settlement
- **What:** `billing/reservations/service.py:403-456` — `_mark_reconciliation_required()` is called BEFORE `db.flush()`. If flush fails, the reconciliation flag isn't persisted but reservation status was updated
- **Impact:** Reservation marked as `SETTLEMENT_FAILED` without the reconciliation flag being visible
- **Fix:** Reorder to flush before marking, or wrap both in the same SAVEPOINT
- **Effort:** 4 hours

### Missing null logging in billing quote
- **What:** `core/llm/billing_service.py:607-610` — if `get_balance()` returns `None`, silently treats balance as 0.0
- **Impact:** Data inconsistency goes undetected, user gets `InsufficientCreditsError` with no actionable log
- **Fix:** Log error-level message when balance is None, include user_id for investigation
- **Effort:** 1 hour

### No request correlation IDs
- **What:** No `X-Request-ID` header propagation or middleware
- **Impact:** Cannot trace a user request across logs, billing events, and external provider calls
- **Fix:** Add middleware that generates/propagates request ID, bind to loguru context
- **Effort:** 4 hours

---

## P2 — Medium (Consistency & Analytics)

### Telemetry tables rely on soft references instead of enforced relationships
- **What:** `billing/usage/models.py:67-128`, `billing/usage/llm_invocation_models.py:16-62`, `billing/usage/tool_invocation_models.py:15-47`, and `billing/outbox/models.py:16-44` store `session_id`, `run_id`, and `message_id` mostly as plain columns rather than foreign keys
- **Impact:** Orphan telemetry rows are easier to create, retention/backfill jobs are harder to validate, and admin dashboard aggregates have weaker integrity guarantees
- **Fix:** Add FKs where lifecycle rules allow them, and where they do not, add documented durable IDs plus reconciliation checks that detect orphaned telemetry
- **Effort:** 2-3 days

### Session-centric project model limits future admin and analytics work
- **What:** `projects/models.py:30-55` still keeps database, storage, and secret state on the `projects` row as JSON blobs, while `project_databases` and other project resources are not consistently normalized
- **Impact:** Building admin tooling requires custom JSON handling instead of relational joins. Analytics pipelines have to special-case project resources and cannot rely on a stable ownership model
- **Fix:** Normalize project resources around `project_id` with dedicated tables for databases, storage bindings, and secret metadata. Keep encrypted secret values separate from admin-listable metadata
- **Effort:** 3-5 days

### Inconsistent pagination patterns
- **What:** Three different pagination styles across routers:
  1. `page/per_page` (sessions, credits, skills)
  2. `limit/offset` (files, projects)
  3. Mixed (some endpoints have both)
- **Impact:** Clients must handle multiple pagination styles. Poor API consistency
- **Fix:** Standardize on one pattern with consistent response shape: `{"items": [...], "total": int, "page": int, "per_page": int}`
- **Effort:** 1-2 days

### Inconsistent error response format
- **What:** `IIAgentError` returns `{"error": "...", "detail": "..."}` but `HTTPException` returns `{"detail": "..."}`
- **Impact:** Clients can't reliably parse error responses
- **Fix:** Unify all errors to `{"error": "<code>", "detail": "<message>"}` in exception middleware
- **Effort:** 4 hours

### No API versioning strategy
- **What:** Endpoints use mixed versioning — `/v1/chat` vs `/sessions` vs `/credits`
- **Impact:** Hard to maintain backward compatibility during API evolution
- **Fix:** Standardize all endpoints under `/api/v1/*` prefix
- **Effort:** 1 day (breaking change, coordinate with frontend)

### Missing UUID validation on path parameters
- **What:** Most router endpoints accept `session_id: str` instead of `session_id: UUID`
- **Impact:** Invalid IDs hit database before failing. Unnecessary DB load
- **Fix:** Change path param types to `UUID` for automatic FastAPI validation
- **Effort:** 4 hours

### No pre-aggregated analytics tables
- **What:** All analytics queries scan raw `llm_invocations`, `tool_invocations`, `usage_records` tables
- **Impact:** Analytics queries compete with OLTP workload. Slow as tables grow
- **Fix:** Create `user_daily_usage`, `model_daily_usage`, `system_daily_metrics` tables with daily aggregation cron
- **Effort:** 2-3 days

### No Prometheus / APM metrics
- **What:** No metrics collection beyond logging. No request latency histograms, error rate counters, or provider latency tracking
- **Impact:** No visibility into system health. Incidents discovered by users, not monitors
- **Fix:** Add `prometheus-fastapi-instrumentator` or Datadog APM. Instrument billing and LLM provider calls
- **Effort:** 1 day

### Missing file upload validation
- **What:** `files/schemas.py:22-26` — `file_name` has no length limit or sanitization, `content_type` accepts arbitrary MIME types, `file_size` not validated against max
- **Impact:** Path traversal risk in filenames, unlimited file sizes bypassing config
- **Fix:** Add `Field(max_length=1024)`, filename sanitization, content_type whitelist, file_size range validation
- **Effort:** 4 hours

### Empty domain `__init__.py` files
- **What:** `agent/__init__.py` is empty, `chat/__init__.py` only exports `ModelNotFoundError`
- **Impact:** Forces deep import paths instead of clean domain-level imports
- **Fix:** Add public API exports following the pattern in `auth/__init__.py` and `sessions/__init__.py`
- **Effort:** 2 hours

### Content domain documentation
- **What:** `content/slides/`, `content/storybook/`, `content/media/` have minimal documentation
- **Impact:** Agents cannot reason about these domains without reading full source
- **Effort:** Medium — document key services, models, and flows

### Integrations domain consistency
- **What:** `integrations/a2a/`, `integrations/connectors/`, `integrations/mcp_sse/` have inconsistent DI patterns
- **Impact:** New code in these domains may not follow project conventions
- **Effort:** Medium — standardize on Dep alias pattern

### Chat media pipeline documentation
- **What:** `chat/media/` has complex orchestration (handlers, modes, services) with no documentation
- **Impact:** Hard to extend or debug media generation
- **Effort:** Medium

---

## P3 — Low (Cleanup & Future-Proofing)

### User model legacy credit columns
- **What:** `users.credits` and `users.bonus_credits` (Float) coexist with `credit_balances` table (Decimal(18,6))
- **Impact:** Potential confusion about source of truth (`credit_balances` is canonical)
- **Fix:** Deprecate `User.credits` / `User.bonus_credits` columns, migrate reads to `credit_balances`
- **Effort:** Low

### Unused imports (~115 instances)
- **What:** Across auth, agent, chat modules. Examples: `datetime`, `timedelta`, `Optional` in `auth/utils.py`; `dataclasses.field` in `agent/application/execution_service.py`
- **Impact:** Code noise, misleading about actual dependencies
- **Fix:** `autoflake --in-place --remove-all-unused-imports --recursive src/ii_agent`
- **Effort:** 1 hour

### String enums instead of Postgres ENUMs
- **What:** All enum columns stored as VARCHAR strings rather than PostgreSQL ENUM types
- **Impact:** No database-level type safety. Invalid values can be inserted
- **Fix:** Migrate to native Postgres ENUMs via Alembic. Requires careful migration with `CREATE TYPE`
- **Effort:** Medium — need downtime or blue-green migration per table

### No table partitioning for high-growth tables
- **What:** `llm_invocations`, `tool_invocations`, `agent_events`, `credit_ledger` will grow unbounded
- **Impact:** Query performance degrades as tables reach 50M+ rows
- **Fix:** Add range partitioning by `created_at` month. Consider moving old data to cold storage
- **Effort:** 1 week

### MemorySessionStore won't survive restarts
- **What:** `agent/socket/session_store.py` stores agent sessions in-memory
- **Impact:** Process restart loses all active agent sessions. Not viable for multi-instance deployment
- **Fix:** Back with Redis using the existing Redis infrastructure
- **Effort:** 1-2 days

### Resource leak in MemorySessionStore TTL tasks
- **What:** `agent/socket/session_store.py:160-167` — if `_cleanup_after_ttl()` raises an exception other than `CancelledError`, the session remains in `_sessions` indefinitely
- **Impact:** Memory leak under error conditions
- **Fix:** Add exception handler in `_cleanup_after_ttl()` that removes the session on any failure
- **Effort:** 1 hour

### Agent socket handler test coverage
- **What:** `agent/socket/command/` handlers have complex orchestration logic with limited test coverage
- **Impact:** Regressions possible during refactoring
- **Effort:** High — requires mocking Socket.IO, agent runtime, and billing

### Deployment pipeline documentation
- **What:** Cloud Run deployment (`projects/cloud_run/`) and deployment orchestration lack reliability docs
- **Impact:** Deployment failures hard to debug
- **Effort:** Low — document the flow

### Custom architectural linters
- **What:** No custom linters for dependency direction, layer boundary, or naming convention enforcement
- **Impact:** Architecture drift detected only in code review
- **Effort:** High — build custom ruff rules or structural tests

### Generated docs automation
- **What:** `docs/generated/db-schema.md` is manually maintained
- **Impact:** Schema docs can drift from actual models
- **Effort:** Medium — build a script to auto-generate from SQLAlchemy models

---

## Analytics & Admin Dashboard Roadmap

### What exists today
- 8 billing tables with full credit lifecycle telemetry
- Per-call `llm_invocations` and `tool_invocations` telemetry
- 6 user-facing credit/usage API endpoints
- 3 billing recovery cron jobs
- Structured logging (loguru + GCP Cloud Logging format)

### What's needed for production analytics

**Phase 1 — Observability foundation (2 weeks):**
- Request correlation IDs (middleware + loguru context binding)
- Prometheus metrics (`prometheus-fastapi-instrumentator`)
- Add missing analytics indexes on `llm_invocations` and `tool_invocations`
- Billing recovery alerts (webhook/Slack on settlement failures)

**Phase 2 — Pre-aggregated analytics (4 weeks):**
- Create `user_daily_usage`, `model_daily_usage`, `system_daily_metrics` tables
- Daily aggregation cron job (Celery beat, 1 AM UTC)
- Cost anomaly detection (compare daily vs 7-day rolling average)

**Phase 3 — Admin dashboard (8 weeks):**
- Admin role + admin-only middleware
- Admin API endpoints: user management, billing overview, credit grants, system health
- Revenue dashboard: MRR, ARR, churn rate
- Billing health: stuck settlements, refund rates, outbox backlog
- User management: active users, credit balances, last activity

**Phase 4 — Analytics warehouse (12+ weeks):**
- OpenTelemetry integration for distributed tracing
- Table partitioning for high-growth tables
- Consider ClickHouse/BigQuery as read-only analytics warehouse when raw tables exceed ~50M rows
- Cohort analysis, feature usage tracking, cost forecasting

### Recommended new tables

```sql
-- Daily per-user aggregation (populated by cron)
user_daily_usage (user_id, date, llm_calls, tool_calls, input_tokens,
                  output_tokens, cost_usd, credits_charged, models_used JSONB,
                  tools_used JSONB, sessions_active)

-- Daily per-model aggregation
model_daily_usage (date, model_id, provider, total_calls, input_tokens,
                   output_tokens, cost_usd, avg_latency_ms, p95_latency_ms,
                   error_count, unique_users)

-- Daily system-wide metrics
system_daily_metrics (date, active_users, new_signups, sessions_created,
                      revenue_usd, cost_usd, gross_margin_pct, deployments,
                      sandbox_hours)

-- Admin audit trail
admin_actions (admin_user_id, action, target_user_id, details JSONB, created_at)
```

### Recommended database strategy from 2026-03-17 repo review
- Keep **PostgreSQL** as the primary OLTP store. Do not add another transactional database before cleaning up the project/resource ownership model
- For the admin dashboard, prefer a **Postgres read replica** plus materialized views / rollup tables before introducing a new serving database
- For future product analytics, add a **warehouse** rather than another app database. On GCP, prefer **BigQuery**. If self-hosted low-latency analytics becomes necessary, evaluate **ClickHouse**
- Normalize project resources first: move away from `projects.database_json`, `storage_json`, and mixed secret handling before building serious admin/reporting surfaces on top
- Treat `billing_usage_facts`, `usage_records`, `llm_invocations`, `tool_invocations`, and curated event streams as warehouse feeds, not as the final dashboard query layer

---

## Resolved

| Item | Resolved Date | How |
|------|--------------|-----|
| God service split | Pre-2026 | Split into domain services (see `docs/design/god-service-split.md`) |
| Platform database redesign | Pre-2026 | Migrated to domain-driven schema (see `docs/design/platform-database-redesign.md`) |
