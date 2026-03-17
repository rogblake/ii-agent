# Production Migration Guide

## Branch: `feat/credit-ledger-pattern-v2` → `refactor/restructure-agent-chat`

This guide covers the full migration from `develop` to the restructured codebase with the credit ledger billing system.

---

## Pre-flight Checklist

- [ ] Database backup completed
- [ ] Application instances stopped (or in maintenance mode)
- [ ] Verify current alembic head matches `develop`: `alembic current`
- [ ] Confirm no in-flight Stripe webhooks (check Stripe dashboard for pending events)

---

## Migration Order

The migration chain runs in this order:

```
(existing develop head)
  → o7p8q9r0s1t2  Add chat_runs table + backfill from agent_run_tasks
  → p8q9r0s1t2u3  Rename tables (chat_*/agent_*) + add app_kind + drop legacy session columns
  → l5m6n7o8p9q0  Add session_pins table
  → b001a1a1a1a1  Schema integrity (Numeric precision, FK constraints, chat_run telemetry columns)
  → b002b2b2b2b2  Credit ledger billing system (8 new tables + backfill from users)
```

---

## Step 1: Run Alembic Migrations

```bash
# Dry-run: verify the migration plan
uv run alembic upgrade --sql b002b2b2b2b2 > /tmp/migration_preview.sql
# Review the SQL output

# Apply migrations
uv run alembic upgrade b002b2b2b2b2
```

### What each migration does:

| Migration | Tables Affected | Downtime Impact |
|-----------|----------------|-----------------|
| `o7p8q9r0s1t2` | Creates `chat_runs`, backfills from `agent_run_tasks` (originals kept) | None — additive only |
| `p8q9r0s1t2u3` | Renames 8 tables, adds `app_kind` column, drops 4 legacy session columns | Brief — table renames acquire ACCESS EXCLUSIVE lock |
| `l5m6n7o8p9q0` | Creates `session_pins` | None — additive only |
| `b001a1a1a1a1` | Alters column types (Float→Numeric), adds + validates FK constraints, adds chat_run columns | **Longest** — `VALIDATE CONSTRAINT` scans existing rows |
| `b002b2b2b2b2` | Creates 8 billing tables, backfills `billing_customers` + `credit_balances` + `credit_ledger` from `users` | Moderate — backfill INSERT scans `users` table |

### Expected duration

- `b001` (FK validation) is the slowest step — duration depends on table sizes:
  - `chat_messages`: ~1s per 100k rows
  - `agent_events`: ~1s per 100k rows
- `b002` backfill: ~1s per 10k users

---

## Step 2: Verify Migration

```bash
# Confirm alembic is at the expected head
uv run alembic current
# Expected: b002b2b2b2b2 (head)

# Verify billing tables were created
psql $DATABASE_URL -c "
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN (
    'credit_ledger', 'credit_balances', 'credit_reservations',
    'billing_customers', 'billing_usage_facts',
    'usage_records', 'llm_invocations', 'tool_invocations'
  )
  ORDER BY table_name;
"
# Expected: 8 rows

# Verify backfill: credit_balances should match users count
psql $DATABASE_URL -c "
  SELECT
    (SELECT count(*) FROM users) AS total_users,
    (SELECT count(*) FROM credit_balances) AS total_balances,
    (SELECT count(*) FROM billing_customers) AS total_customers;
"
# total_balances MUST equal total_users
# total_customers = users with non-null stripe_customer_id

# Verify chat_runs backfill: count must match source rows
psql $DATABASE_URL -c "
  SELECT
    (SELECT count(*) FROM chat_runs) AS chat_runs_count,
    (SELECT count(*) FROM agent_run_tasks art
     JOIN sessions s ON s.id = art.session_id
     WHERE s.agent_type = 'chat') AS source_count;
"
# chat_runs_count MUST equal source_count (originals still intact)

# Verify chat_runs backfill: every row matches its source by id
psql $DATABASE_URL -c "
  SELECT count(*) AS orphaned_chat_runs
  FROM chat_runs cr
  WHERE NOT EXISTS (
    SELECT 1 FROM agent_run_tasks art WHERE art.id = cr.id
  );
"
# Expected: 0 — every chat_run has a matching agent_run_task

# Verify chat_runs backfill: no missing rows
psql $DATABASE_URL -c "
  SELECT count(*) AS missing_chat_runs
  FROM agent_run_tasks art
  JOIN sessions s ON s.id = art.session_id
  WHERE s.agent_type = 'chat'
  AND NOT EXISTS (
    SELECT 1 FROM chat_runs cr WHERE cr.id = art.id
  );
"
# Expected: 0 — every chat agent_run_task was copied

# Verify chat_runs backfill: status values match between tables
psql $DATABASE_URL -c "
  SELECT count(*) AS status_mismatches
  FROM chat_runs cr
  JOIN agent_run_tasks art ON art.id = cr.id
  WHERE cr.status != art.status;
"
# Expected: 0 — status is identical in both tables

# Verify table renames
psql $DATABASE_URL -c "
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN (
    'chat_summaries', 'chat_provider_containers',
    'chat_provider_files', 'chat_provider_vector_stores',
    'agent_events', 'agent_sandboxes', 'agent_summaries', 'agent_event_log'
  )
  ORDER BY table_name;
"
# Expected: 8 rows (old names like 'events', 'sandboxes' should not exist)

# Verify app_kind was backfilled
psql $DATABASE_URL -c "
  SELECT app_kind, count(*) FROM sessions GROUP BY app_kind;
"
# Expected: 'agent' and 'chat' rows
```

---

## Step 3: Backfill Usage Records

This populates `usage_records` from existing `credit_ledger` deduction entries. It is idempotent and safe to re-run.

```bash
uv run python scripts/backfill_usage_records.py
```

### Verify backfill

```bash
psql $DATABASE_URL -c "
  SELECT count(*) AS usage_records FROM usage_records;
"
# Should be > 0 if there are any existing ledger deductions

psql $DATABASE_URL -c "
  SELECT source_domain, count(*) FROM usage_records GROUP BY source_domain;
"
```

---

## Step 4: Start Application

```bash
# Start the application
./start.sh

# Health check
curl http://localhost:8000/health

# Verify billing endpoint works
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/credits/balance
```

---

## Step 5: Post-deploy Verification

```bash
# Verify session events return run_status for both app kinds
# For a chat session:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/sessions/<chat-session-id>/events \
  | jq '.run_status'

# For an agent session:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/sessions/<agent-session-id>/events \
  | jq '.run_status'

# Verify ledger page returns entries (was previously broken)
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/credits/ledger/<session-id>" \
  | jq '.total'
```

---

## Rollback Procedure

If issues are found, roll back in reverse order:

```bash
# Stop the application first

# Roll back to develop head
uv run alembic downgrade <develop-head-revision>

# Restart with the develop branch code
git checkout develop
./start.sh
```

### Rollback impacts

- `b002` downgrade: Drops all 8 billing tables. **Billing data created after migration is lost.**
- `b001` downgrade: Drops FK constraints, reverts Numeric→Float. No data loss.
- `p8q9r0s1t2u3` downgrade: Renames tables back, re-adds dropped session columns (with default values, not original data).
- `o7p8q9r0s1t2` downgrade: Drops `chat_runs` table. No data loss since originals remain in `agent_run_tasks`.

---

## Future Work (Phase 2)

After this migration is stable in production:

1. **Delete chat rows from `agent_run_tasks`** — create a new migration:
   ```sql
   DELETE FROM agent_run_tasks
   WHERE session_id IN (SELECT id FROM sessions WHERE app_kind = 'chat');
   ```
2. **Drop legacy columns from `users` table** — `credits`, `bonus_credits`, `stripe_customer_id`, `subscription_plan`, `subscription_status`, `subscription_billing_cycle`, `subscription_current_period_end` are now read from `credit_balances` and `billing_customers`.
