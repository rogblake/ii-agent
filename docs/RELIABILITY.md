# Reliability

## Billing Reliability: Reserve → Settle → Release

All billable work (LLM calls, tool executions) follows a three-phase lifecycle managed by `core/llm/billing_service.py` (`LLMBillingService`) and `billing/reservations/service.py` (`CreditReservationService`).

### Phase 1: Reserve (Before Work Starts)

```
LLMBillingService.reserve_*_llm_call()
  → estimate_tokens(messages) — tiktoken or len/4 fallback
  → ModelPricing lookup (billing/credits/pricing.py)
  → _quote_llm_call():
      input_cost + cache_reserve(25%) + estimated_output_cost(output_cap) + safety_margin($0.001)
      → if current balance > 0, the output cap is budgeted against current balance + 50 controlled-shortfall credits
      → reserve_usd capped at the USD value of 15 credits
      → max_usd stores the uncapped upper bound for later settlement
      → affordable output cap from remaining balance
      → if output_cap < 128 tokens → InsufficientCreditsError
  → CreditReservationService.reserve():
      → SELECT credit_balances FOR UPDATE (row lock)
      → require current balance > 0 and current balance + 50 credits >= quoted max
      → INSERT credit_ledger (idempotent via idempotency_key)
      → UPDATE credit_balances (deduct only the currently available balance, not future shortfall debt)
  → Returns ReservationHold with output_token_cap
```

The output cap is enforced at the LLM provider level. The initial hold is only the prepaid portion of the request. When the user has a positive balance but cannot fully cover the quoted hold, the system reserves the remaining balance and allows up to 50 credits of controlled shortfall beyond that. `credit_balances` never go negative.

### Phase 2: Settle (After Work Completes)

```
LLMBillingService.settle_*_llm_call()
  → _settle_llm_direct()
  → CreditReservationService.settle()
  → Charges actual cost, refunds overage to balance
  → If actual > held and remaining balance cannot cover the shortfall:
      reservation → SETTLEMENT_FAILED
      last_error  → settlement_shortfall_unreconciled
      balance     → stays non-negative
      exact settle inputs remain captured on the reservation for replay
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
                                       exact usage remains on the reservation
                                       for manual or payment-time replay)
```

Terminal states (SETTLED, RELEASED, EXPIRED) block further transitions.

### Two Runtime Paths

| Path | Used By | Billing Location |
|------|---------|-----------------|
| **Agent Runtime** (`agent/runtime/`) | Socket command handlers (query, plan) | Per-call inside agent streaming loop |
| **LLMExecutionService** (`core/llm/execution_service.py`) | Chat, storybook, content generation | `send_once()` or `run_tool_loop_until_final()` |

Both follow identical reserve → settle → release. Never add post-run billing.

### Billing Identity Fields

The billing system now tracks several separate identity dimensions. Do not overload one field to do another field's job.

- `subject_kind` / `subject_id` — who owns the charge
- `billing_context` — which product/workflow surface produced it
- `source_domain` — which billing subsystem emitted it
- `run_id` — which higher-level execution/run it belongs to
- `source_id` / operation id — which exact billable action it was

Example:

- Storybook AI rewrite:
  - `subject = session`
  - `billing_context = storybook`
  - `source_domain = chat_llm`

- Storybook voice generation:
  - `subject = session`
  - `billing_context = storybook`
  - `source_domain = voice_generation`

- Future Factory node LLM call:
  - `subject = factory_project`
  - `billing_context = factory`
  - `source_domain = factory_llm`
  - `run_id = factory_run_id`
  - `source_id = node_execution_id`

For new subjects like Factory, prefer the top-level business object as the subject (`factory_project`) and put node-level identity in `run_id`, `source_id`, and metadata. Do not make each node the subject unless per-node billing history is the primary read path.

### Tool Billing

Tools with external costs set `max_cost_usd` and optionally override `quote_cost()`. The `Function` wrapper handles `_reserve_tool_billing()` → execute → `_finalize_tool_billing()` automatically.

### Direct Sync Billing For Non-LLM Work

For non-LLM operations that are billed outside `LLMExecutionService`, use the
shared helper in `billing/operations.py`:

1. Build a `BillingScope`
2. Build a `BillingReservationRequest`
3. Call `run_billed_operation(...)`
4. Return a `BillingResult(...)` from the provider function

Pseudo-flow for a new synchronous flow:

```python
from ii_agent.billing.operations import run_billed_operation
from ii_agent.billing.types import BillingReservationRequest, BillingResult
from ii_agent.billing.reservations.types import BillingKind, BillingQuote

request = BillingReservationRequest(
    source_domain="factory_render",
    source_id=operation_id,
    billing_kind=BillingKind.TOOL_USAGE,
    quote=BillingQuote(
        strategy="bounded",
        reserve_usd=quote.reserve_usd,
        max_usd=quote.max_usd,
    ),
    tool_name="factory_render",
    idempotency_key=scope.build_operation_key("factory_render", operation_id),
    metadata={**scope.billing_metadata(), "node_id": node_id},
)

result = await run_billed_operation(
    reservation_service=reservation_service,
    scope=scope,
    request=request,
    release_reason="factory_render_failed",
    settlement_error="factory_render_settle_exception",
    execute_fn=render_node_with_billing,
)

async def render_node_with_billing() -> BillingResult[RenderResult]:
    render_result = await render_node()
    return BillingResult(
        value=render_result,
        actual_usd=render_result.actual_usd,
        actual_credits=render_result.actual_credits,
        usage_payload={
            **scope.billing_metadata(),
            **render_result.usage_payload,
        },
    )
```

The helper owns reserve -> release/capture -> settle. Use the lower-level
reservation service only when the flow shape genuinely does not fit this
wrapper.

Merge `BillingScope.billing_metadata()` into request metadata and usage
payload when the caller uses `BillingScope`.

### Direct Async Billing For Background Work

For queued or background work, split the lifecycle across the enqueueing path
and the worker using `reserve_billing_operation(...)` and
`finalize_billing_operation(...)`:

1. Build a `BillingScope` and `BillingReservationRequest`
2. Reserve before enqueueing and commit the hold
3. Persist `reservation_id` with the job payload or owner record
4. In the worker, call `finalize_billing_operation(...)`

Pseudo-flow for a new async flow:

```python
from ii_agent.billing.operations import (
    finalize_billing_operation,
    reserve_billing_operation,
)

async with get_db_session_local() as reserve_db:
    hold = await reserve_billing_operation(
        reserve_db,
        reservation_service=reservation_service,
        scope=scope,
        request=request,
    )
    await reserve_db.commit()

await enqueue_job(
    ...,
    reservation_id=hold.reservation_id if hold is not None else None,
)

# In the worker:
await finalize_billing_operation(
    reservation_service=reservation_service,
    scope=scope,
    reservation_id=reservation_id,
    result=(
        None
        if no_billable_result
        else BillingResult(
            value=None,
            actual_usd=actual_usd,
            actual_credits=actual_credits,
            usage_payload={**scope.billing_metadata(), **usage_payload},
        )
    ),
    release_reason="factory_render_failed",
    settlement_error="factory_render_settle_exception",
)
```

This is required so a worker crash between capture and settle can be recovered
from the captured metadata instead of refunding delivered work.

### Manual Settlement Replay

Before final settlement, the billing layer stores the exact `actual_credits`, `actual_usd`, and `usage_payload` inside `credit_reservations.reservation_metadata`. If settlement later throws, operators can replay it manually from that captured snapshot instead of reconstructing usage from best-effort telemetry.

### Controlled Shortfall Design

- `credit_balances` remains the spendable prepaid balance and never goes negative.
- Unpaid overrun is represented as a shortfall on the reservation (`SETTLEMENT_FAILED` with `settlement_shortfall_unreconciled`), not as a negative balance row.
- Reservation admission requires:
  - current balance `> 0`
  - current balance `+ 50 credits >= quoted max`
- The hold only deducts the currently available balance. The unpaid remainder is recovered later.
- `invoice.payment_succeeded` resets the plan balance, then replays replayable shortfall settlements before clearing `billing_status`.
- Billing stays blocked until all replayable shortfalls for that user are resolved.

## Cron Recovery Jobs

Two background jobs in `workers/cron/billing_recovery.py`:

| Job | Frequency | What it does |
|-----|-----------|-------------|
| `expire_stale_reservations` | Every 15 min | Releases RESERVED holds past `expires_at` (batch limit: 200). Skips SETTLEMENT_FAILED. |
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
