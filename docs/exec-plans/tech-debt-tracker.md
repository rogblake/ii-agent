# Technical Debt Tracker

Known technical debt items, tracked so agents and engineers can prioritize cleanup work.

Last comprehensive review: 2026-03-17

---

## P0 — Critical (Security & Correctness)

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

---

## Resolved

| Item | Resolved Date | How |
|------|--------------|-----|
| God service split | Pre-2026 | Split into domain services (see `docs/design/god-service-split.md`) |
| Platform database redesign | Pre-2026 | Migrated to domain-driven schema (see `docs/design/platform-database-redesign.md`) |
