# Reliability

## Billing Reliability: Reserve → Settle → Release

All billable work (LLM calls, tool executions) follows a three-phase lifecycle managed by `core/llm/billing_service.py` (`LLMBillingService`) and `billing/reservations/service.py` (`CreditReservationService`).

### Phase 1: Reserve (Before Work Starts)

```
LLMBillingService.reserve_*_llm_call()
  → estimate_tokens(messages) — tiktoken or len/4 fallback
  → ModelPricing lookup (billing/credits/pricing.py)
  → _quote_llm_call():
      input_cost + cache_reserve(75%) + estimated_output_cost(input / 10) + safety_margin($0.001)
      → max_usd capped at $10
      → reserve_usd clamped to max_usd when needed
      → affordable output cap from remaining balance
      → if output_cap < 128 tokens → InsufficientCreditsError
  → CreditReservationService.reserve():
      → SELECT credit_balances FOR UPDATE (row lock)
      → INSERT credit_ledger (idempotent via idempotency_key)
      → UPDATE credit_balances (deduct hold)
  → Returns ReservationHold with output_token_cap
```

The output cap is enforced at the LLM provider level. The initial hold is an estimate, so settlement can still detect and charge a shortfall up to the capped response.

### Phase 2: Settle (After Work Completes)

```
LLMBillingService.settle_*_llm_call()
  → If outbox enabled (production):
      → capture_llm_fact() → INSERT billing_usage_facts (status=captured)
      → process_fact() → settle reservation + mark processed
  → If outbox disabled (dev):
      → _settle_llm_direct()
      → CreditReservationService.settle()
  → Charges actual cost, refunds overage to balance
```

### Phase 3: Release (On Failure/Cancellation)

```
LLMBillingService.release_llm_call()
  → CreditReservationService.release()
  → Full refund of reserved amount back to balance
```

### Reservation State Machine

```
RESERVED ──settle()──→ SETTLED       (actual cost charged, overage refunded)
    │
    ├──release()──→ RELEASED          (full refund, no work delivered)
    │
    ├──expire_stale()──→ EXPIRED      (cron refund after 30 min timeout)
    │
    └──mark_settlement_failed()──→ SETTLEMENT_FAILED
                                      (work delivered but settle threw;
                                       blocks auto-expiry refund;
                                       outbox retries later)
```

Terminal states (SETTLED, RELEASED, EXPIRED) block further transitions.

### Two Runtime Paths

| Path | Used By | Billing Location |
|------|---------|-----------------|
| **Agent Runtime** (`agent/runtime/`) | Socket command handlers (query, plan) | Per-call inside agent streaming loop |
| **LLMExecutionService** (`core/llm/execution_service.py`) | Chat, storybook, content generation | `send_once()` or `run_tool_loop_until_final()` |

Both follow identical reserve → settle → release. Never add post-run billing.

### Tool Billing

Tools with external costs set `max_cost_usd` and optionally override `quote_cost()`. The `Function` wrapper handles `_reserve_tool_billing()` → execute → `_finalize_tool_billing()` automatically.

## Durable Outbox Pattern

`billing/outbox/service.py` (`BillingUsageFactService`) ensures no billing data is lost even if the process crashes between LLM completion and settlement.

```
1. capture_llm_fact() / capture_tool_fact()
   → INSERT INTO billing_usage_facts (status=captured)

2. process_fact()
   → settle reservation + mark processed

3. On exception:
   → mark retryable (up to 5 attempts)
   → then manual_review
```

### Fact Lifecycle

```
captured → processing → processed (success)
                     → retryable → processing (retry, max 5)
                                → manual_review (exhausted)
```

## Cron Recovery Jobs

Three background jobs in `workers/cron/billing_recovery.py`:

| Job | Frequency | What it does |
|-----|-----------|-------------|
| `expire_stale_reservations` | Every 15 min | Releases RESERVED holds past `expires_at` (batch limit: 200). Skips SETTLEMENT_FAILED. |
| `retry_billing_usage_facts` | Every 1 min | Retries captured/stale facts (batch limit: 50, max 5 attempts per fact). |
| `alert_settlement_failures` | Every 5 min | Logs SETTLEMENT_FAILED reservations for operator visibility. |

## Redis Resilience

Redis is **optional** throughout the codebase. Every Redis-dependent feature has an in-memory fallback:

| Feature | Redis Implementation | Fallback |
|---------|---------------------|----------|
| Entity cache | `RedisEntityCache` (distributed, TTL) | `MemoryEntityCache` (OrderedDict, LRU eviction) |
| Pub/sub | Redis pub/sub | `AsyncIOPubSub` (asyncio queues, single-worker only) |
| Socket.IO sessions | `AsyncRedisManager` | In-memory (single-worker only) |
| Cancellation tokens | Redis keys | In-memory dict |
| Distributed locks | Redis locks | No-op / in-memory |

**Initialization:** `is_redis_enabled()` checks availability. Clients created lazily on first use. `close_redis()` called on app shutdown.

## Database Resilience

- **Connection pooling:** `pool_size`, `max_overflow`, `pool_timeout` configurable via `DatabaseSettings`
- **Pool recycling:** `pool_recycle=3600` prevents stale connections
- **Pre-ping:** `pool_pre_ping=True` validates connections before use
- **SSL:** asyncpg SSL context created for Cloud SQL connections
- **Optimistic locking:** `version` column on `Session`, `AgentRunTask`, `ChatRun` prevents concurrent mutation conflicts

## Agent Run Reliability

- **Task locking:** `create_task_with_lock()` uses session lock to prevent concurrent agent runs on the same session
- **Run states:** PENDING → RUNNING → COMPLETED/PAUSED/ABORTING → ABORTED/FAILED/ERROR
- **Cancellation:** Redis-based `cancel.cancel_run(run_id)` signals the agent loop to stop
- **Partial billing:** If an LLM call produces tokens before failing, those tokens are settled (not released)
- **Event persistence:** `DatabaseSubscriber` persists agent events to `agent_ui_events` table, skipping transient streaming events

## Storage Resilience

- **Multiple storage instances:** `storage` (uploads), `media_storage` (media), `slide_storage` (slides) — each independently configured
- **Signed URLs:** Time-limited (default 1 hour) for both upload and download
- **Resource cleanup:** `close_all_storage_clients()` on app shutdown
- **Lazy initialization:** Storage clients created on first access, not at import
