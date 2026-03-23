# II-Agent Project Guide

## Project Overview

II-Agent is an AI agent platform built with FastAPI and SQLAlchemy 2.0. The codebase follows a domain-driven architecture where business logic is organized into domain modules.

## Architecture

### Domain Structure

```
src/ii_agent/
├── app/                        # FastAPI bootstrap package (factory, lifespan, middleware, routers)
│
├── core/                       # Shared infrastructure & configuration
│   ├── config/                 # Pydantic settings (database, redis, storage, oauth, stripe)
│   ├── db/                     # SQLAlchemy base, session management
│   ├── llm/                    # LLM base client utilities
│   ├── redis/                  # Redis client, cache, pubsub, lock, cancel management
│   ├── secrets/                # Secrets management (GCP)
│   └── storage/                # File storage abstraction (GCS, local)
│
├── auth/                       # Authentication & authorization (OAuth, JWT, API keys)
│   └── users/                  # User profiles, waitlist, user CRUD
│
├── billing/                    # Credit ledger, reservations, usage, Stripe webhooks
│   ├── credits/                # Credit balance, ledger, pricing, service
│   ├── reservations/           # Reserve → settle → release state machine
│   └── usage/                  # Usage records, LLM/tool invocation telemetry
│
├── sessions/                   # Chat sessions management (CRUD, state, fork, validation)
│   └── wishlist/               # Session wishlist/bookmarks
│
├── chat/                       # Chat API & LLM providers
│   ├── llm/                    # LLM provider implementations
│   │   └── anthropic/          # Anthropic provider (client, tool handler)
│   ├── media/                  # Media processing in chat
│   │   ├── handlers/           # Media type handlers (image, video, text, default)
│   │   ├── modes/              # Processing modes (conversation, image gen, video gen, web)
│   │   ├── services/           # Media services (image gen, video gen, web search)
│   │   └── utils/              # Media utilities
│   ├── tools/                  # Chat tools (code interpreter, tool registry)
│   └── vectorstore/            # Vector store integration (OpenAI)
│
├── engine/                     # Agent execution framework
│   ├── agents/                 # Agent run management & execution
│   │   └── parser/             # Response parsers (Claude)
│   ├── prompts/                # System prompts & templates
│   ├── sandboxes/              # Sandbox environment management (E2B)
│   └── v1/                     # V1 agent architecture
│       ├── agent_sessions/     # V1 session management
│       ├── agents/             # V1 agent implementations
│       ├── api/                # V1 API endpoints
│       ├── db/                 # V1 database utilities
│       ├── factory/            # V1 agent factory
│       ├── hooks/              # V1 lifecycle hooks
│       ├── media/              # V1 media handling
│       ├── models/             # V1 LLM provider models
│       │   ├── anthropic/      # Anthropic provider
│       │   ├── cerebras/       # Cerebras provider
│       │   ├── custom/         # Custom provider
│       │   ├── google/         # Google provider
│       │   ├── openai/         # OpenAI provider
│       │   └── vertexai/       # Vertex AI provider
│       ├── run/                # V1 run management
│       ├── skills/             # V1 skills framework
│       │   ├── builtin/        # Built-in skills (docx, pdf, pptx, xlsx, research-to-website)
│       │   └── skills_ref/     # Skill reference data
│       ├── tools/              # V1 tool implementations
│       │   ├── a2a/            # Agent-to-Agent tools
│       │   ├── agent/          # Agent tools
│       │   ├── browser/        # Browser tools
│       │   ├── connectors/     # Connector tools
│       │   ├── dev/            # Dev tools
│       │   ├── file_system/    # File system tools
│       │   ├── mcp/            # MCP tools
│       │   ├── media/          # Media tools
│       │   ├── plan/           # Planning tools
│       │   ├── productivity/   # Productivity tools
│       │   ├── sandbox/        # Sandbox tools
│       │   ├── shell/          # Shell tools
│       │   ├── slide_system/   # Slide tools
│       │   └── web/            # Web tools
│       └── utils/              # V1 utilities
│
├── content/                    # Content generation
│   ├── media/                  # Media templates & tools (reference images)
│   │   └── config/             # Media configuration
│   ├── skills/                 # Custom skills management
│   ├── slides/                 # Slide/presentation generation
│   │   └── templates/          # Slide templates
│   └── storybook/              # Storybook generation
│
├── files/                      # File upload/download service
│
├── integrations/               # External integrations
│   ├── a2a/                    # Agent-to-Agent protocol support
│   ├── connectors/             # External connectors (GitHub, Google Drive)
│   │   └── composio/           # Composio integration
│
├── projects/                   # Project & deployment management
│   ├── cloud_run/              # Google Cloud Run deployment
│   │   └── assets/             # Deployment assets
│   ├── databases/              # Database provisioning
│   ├── deployments/            # Deployment management
│   ├── secrets/                # Project secrets management
│   └── subdomains/             # Subdomain management
│
├── realtime/                   # Real-time communication
│   ├── events/                 # Event handling & logging
│   ├── socket/                 # WebSocket/Socket.IO handlers
│   │   └── command/            # Socket command handlers (query, cancel, plan)
│   └── subscribers/            # Event subscribers (metrics, database)
│
├── settings/                   # User settings
│   ├── llm/                    # User LLM model configuration
│   │   └── store/              # Settings persistence (file store)
│   └── mcp/                    # MCP server configuration
│
├── utils/                      # Shared utilities
└── scripts/                    # Admin scripts (credit refresh, waitlist import)
```

### Import Patterns

#### From Domain Module (Preferred)

```python
# Import from domain __init__.py - exports models, services, router, schemas
from ii_agent.sessions import Session, session_service, router, SessionInfo
from ii_agent.auth import CurrentUser, DBSession, get_current_user, router
from ii_agent.billing import BillingTransaction, router
from ii_agent.files import FileUpload, file_service
from ii_agent.projects import Project, project_service
```

#### Direct Imports (When Needed)

```python
# Models
from ii_agent.auth.users.models import User, LLMSetting, MCPSetting, APIKey
from ii_agent.sessions.models import Session, SessionStateEnum
from ii_agent.core.db.base import Base, TimestampColumn

# Services
from ii_agent.sessions.service import SessionService
from ii_agent.auth.users.service import UserService
from ii_agent.realtime.events.service import EventService

# Database utilities
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.agents.models import AgentRunTask
```

### Service Pattern

Services take `db: AsyncSession` as first parameter. Singleton initialized at module level:

```python
# In sessions/service.py:
class SessionService:
    def __init__(self, file_store: BaseStorage, config: Settings) -> None:
        self._file_store = file_store
        self._config = config

    async def get_session(self, db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

# Initialize singleton at end of file
session_service = SessionService(file_store=storage, config=get_settings())
```

### Dependency Injection Pattern (`dependencies.py`)

Each domain has a `dependencies.py` that defines factory functions and `Dep` type aliases using `Annotated`. **Always use Dep aliases** — both in routers and in other factory functions that compose dependencies.

#### Structure rules

1. **Define Dep aliases immediately after** the factory they wrap (before any factory that uses them).
2. **Use Dep aliases everywhere** — never use bare `= Depends(get_x)` in function signatures (exception: `credentials: HTTPAuthorizationCredentials = Depends(security)` in auth, which is a FastAPI security scheme).
3. **Import Dep aliases** from other domains instead of importing their factory functions.

```python
# In sessions/dependencies.py:
from typing import Annotated
from fastapi import Depends

from ii_agent.engine.agents.dependencies import AgentRunServiceDep      # Cross-domain Dep alias
from ii_agent.engine.sandboxes.dependencies import SandboxRepositoryDep
from ii_agent.realtime.events.dependencies import EventRepositoryDep
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService

# 1. Factory function
def get_session_repository() -> SessionRepository:
    return SessionRepository()

# 2. Dep alias defined IMMEDIATELY after its factory
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]

# 3. Downstream factories use Dep aliases, not Depends(get_x)
def get_session_service(
    session_repo: SessionRepositoryDep,          # <-- Dep alias (local)
    event_repo: EventRepositoryDep,              # <-- Dep alias (cross-domain)
    sandbox_repo: SandboxRepositoryDep,          # <-- Dep alias (cross-domain)
    agent_run_service: AgentRunServiceDep,        # <-- Dep alias (cross-domain)
) -> SessionService:
    return SessionService(...)

SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
```

#### Anti-patterns (DO NOT)

```python
# BAD: bare Depends(get_x) — use the Dep alias instead
def get_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),
) -> SessionService: ...

# BAD: importing factory functions from other domains for Depends()
from ii_agent.engine.agents.dependencies import get_agent_run_service
# GOOD: import the Dep alias
from ii_agent.engine.agents.dependencies import AgentRunServiceDep

# BAD: defining Dep aliases at the bottom of the file, after factories that need them
def get_session_service(session_repo: SessionRepositoryDep): ...  # NameError!
SessionRepositoryDep = Annotated[...]  # Too late

# BAD: creating local Dep aliases that duplicate core ones
DefaultStorageDep = Annotated[BaseStorage, Depends(get_storage)]  # Use StorageDep from core.storage.dependencies
```

### Router Pattern

Use Dep aliases for auth, database, and all service dependencies:

```python
# In sessions/router.py:
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.sessions.dependencies import SessionServiceDep

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession,
    session_service: SessionServiceDep,
):
    return await session_service.get_session(db, session_id)
```

### Domain `__init__.py` Pattern

Export all public APIs from domain module:

```python
# In sessions/__init__.py:
from .models import Session, SessionStateEnum, ConversationSummary
from .service import SessionService, session_service, Sessions
from .router import router
from .schemas import SessionCreate, SessionInfo, SessionList

__all__ = [
    "Session", "SessionStateEnum", "ConversationSummary",
    "SessionService", "session_service", "Sessions",
    "router",
    "SessionCreate", "SessionInfo", "SessionList",
]
```

### SQLAlchemy 2.0 Models

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ii_agent.core.db.base import Base, TimestampColumn

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    state: Mapped[SessionStateEnum] = mapped_column(default=SessionStateEnum.IDLE)

    user: Mapped["User"] = relationship(back_populates="sessions")
```

## Development Guidelines

### Adding a New Domain

1. Create domain folder: `src/ii_agent/{domain_name}/`
2. Create files:
   - `__init__.py` - Export all public APIs
   - `models.py` - SQLAlchemy models
   - `repository.py` - Data access layer
   - `service.py` - Business logic
   - `dependencies.py` - Factory functions & Dep aliases
   - `router.py` - FastAPI endpoints
   - `schemas.py` - Pydantic request/response DTOs
   - `exceptions.py` - Domain-specific exceptions
3. Register router in `app/routers.py`

### Verification

```bash
# Verify imports
python -c "from ii_agent.sessions import Session, session_service; print('OK')"

# Start server
./scripts/start.sh

# Health check
curl http://localhost:8000/health
```

## Billing & Credit System

### Overview

All paid work (LLM calls, tool executions) is billed through a **credit ledger** with a **reserve → settle → release** lifecycle. Credits are the internal unit of account; USD costs are converted via `usd_to_credits()` / `credits_to_usd()` in `billing/credits/utils.py`.

### Domain Structure

```
billing/
├── credits/
│   ├── balance_models.py       # credit_balances table (one row per user)
│   ├── balance_repository.py   # Atomic balance mutations with FOR UPDATE locks
│   ├── ledger_models.py        # credit_ledger table (append-only audit trail)
│   ├── ledger_repository.py    # Idempotent ledger appends (ON CONFLICT DO NOTHING)
│   ├── service.py              # CreditService — lock → ledger → balance in SAVEPOINT
│   ├── pricing.py              # ModelPricing — per-model token prices
│   ├── utils.py                # usd_to_credits / credits_to_usd conversion
│   └── constants.py            # Default credit allocations
├── reservations/
│   ├── models.py               # credit_reservations table
│   ├── repository.py           # Reservation CRUD with row locking
│   ├── service.py              # CreditReservationService — reserve/settle/release state machine
│   └── types.py                # BillingQuote, ReservationHold, BillingSettlementResult
├── usage/
│   ├── service.py              # UsageService — usage_records + session_metrics accumulation
│   ├── llm_invocation_models.py    # llm_invocations telemetry table
│   └── tool_invocation_models.py   # tool_invocations telemetry table
├── exceptions.py               # InsufficientCreditsError, BillingReconciliationRequiredError
└── webhook_handler.py          # Stripe webhook → credit grants on invoice.payment_succeeded
```

### Credit Lifecycle: Reserve → Settle → Release

Every billable operation follows this three-phase pattern. **Never call `CreditService.deduct()` directly for LLM or tool billing** — always go through the reservation system.

```
1. RESERVE   — Before work starts, hold credits from the user's balance
2. SETTLE    — After work completes, finalize to actual cost (refund overage or charge shortfall)
3. RELEASE   — If work fails/cancels before completion, refund the full hold
```

#### Reservation State Machine

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
                                       requires reconciliation)
```

#### Atomicity Guarantees

All credit mutations use this pattern inside `CreditReservationService` and `CreditService`:

```python
async with db.begin_nested():           # SAVEPOINT
    balance = lock_balance_state(...)    # SELECT ... FOR UPDATE
    ledger_entry = ledger.append(...)    # INSERT with idempotency_key
    if ledger_entry is None:             # Duplicate → skip balance mutation
        return existing
    apply_delta_locked(...)              # UPDATE balance
```

- **Row lock** serializes concurrent operations for the same user
- **SAVEPOINT** ensures ledger and balance are atomic (both succeed or both roll back)
- **Idempotency key** on the ledger prevents double-charging on retries

### Billing Identity Model

Billing is keyed by a normalized identity, not by `session_id` alone.

- `subject_kind` / `subject_id` — the business object that owns the charge
- `billing_context` — the product/workflow surface (`chatloop`, `agentloop`, `storybook`, `factory`)
- `source_domain` — the billing-producing subsystem (`chat_llm`, `agent_tool`, future `factory_llm`)
- `run_id` — correlation id for one higher-level execution/run
- `operation_id` — one exact billable step inside that run; used to build the idempotency key

Use these rules:

- `subject` answers "who owns this cost?"
- `billing_context` answers "where in the product did this come from?"
- `source_domain` answers "which billing pipeline emitted this record?"
- `run_id` groups many charges from the same execution
- `operation_id` must uniquely identify one billable action

Do not collapse `billing_context` and `source_domain` into one field. One context can contain multiple source domains. Example: Storybook can emit `chat_llm`, `voice_generation`, and `image_generation`.

### LLM Billing Integration

#### Orchestration Layer: `LLMBillingService` (`core/llm/billing_service.py`)

This is the **single entry point** for all LLM and tool billing. It sits between the runtime layers and the reservation system.

```python
class LLMBillingService:
    # LLM calls
    reserve_chat_llm_call()    / reserve_agent_llm_call()
    settle_chat_llm_call()     / settle_agent_llm_call()
    release_llm_call()
    mark_settlement_failed()

    # Tool calls
    reserve_tool_call()
    settle_tool_call()         / settle_tool_call_by_reservation_id()
    release_tool_call()        / release_tool_call_by_reservation_id()
```

#### How LLM Quoting Works (`_quote_llm_call`)

```
1. Estimate input tokens (tiktoken or len/4 fallback)
2. Look up ModelPricing for the model
3. Compute:
   - input_cost       = input_tokens × input_price_per_million
   - cache_reserve    = 25% of input_tokens × cache_write_price
   - if current balance > 0, use current balance + 50 controlled-shortfall credits as the output-cap budget
   - affordable_cap   = remaining budget after input/cache reserve
   - output_estimate  = min(output_cap, ceil(input_tokens / 10))
   - reserve_estimate = input + cache + estimated output + $0.001
   - uncapped_max_usd = input + cache + full output_cap + $0.001
   - reserve_usd      = min(reserve_estimate, USD value of 15 credits)
4. If output_cap < 128 tokens → raise InsufficientCreditsError
5. Return BillingQuote(reserve_usd=estimated hold, max_usd=uncapped max) + output_token_cap
```

The output cap is enforced on the provider via `_apply_reserved_output_cap()` (agent) or `provider_options` (chat). The initial hold is only the prepaid portion of the request. If the user has a positive balance but cannot fully cover the hold, reserve drains the remaining balance, leaves `credit_balances` non-negative, and any unpaid overrun is reflected later as a reservation shortfall.

#### Controlled Shortfall Policy

- `credit_balances` is always the spendable prepaid balance and never goes negative.
- Reservation admission requires:
  - current spendable balance `> 0`
  - current spendable balance `+ 50 credits >= quoted max`
- Reserve deducts only what is actually available at that moment.
- If settlement cannot collect the overrun immediately, the reservation stays `SETTLEMENT_FAILED` with `last_error = settlement_shortfall_unreconciled`.
- The exact settle input is already captured on the reservation, so payment-time replay can resolve the shortfall when new credits arrive.
- `invoice.payment_succeeded` must replay replayable shortfalls before clearing `billing_status`.

### Two Runtime Paths

There are two runtime paths that invoke LLM billing. Both follow the same reserve → settle → release pattern.

#### Path 1: Agent Runtime (`agent/runtime/models/base.py`)

Used by socket command handlers (query, continue, plan). Billing happens **per LLM call** inside the agent's streaming loop.

```python
# In Model.aprocess_response_stream():
reservation = await self._reserve_llm_billing(messages, assistant_message, run_response)
self._apply_reserved_output_cap(reservation)
try:
    async for delta in self._ainvoke_stream_with_retry(...):
        yield delta
    await self._settle_llm_billing(reservation, run_response, metrics)
except Exception:
    if metrics and metrics.total_tokens > 0:
        await self._settle_llm_billing(...)    # Charge for partial usage
    else:
        await self._release_llm_billing(...)   # Full refund
    raise
```

Key points:
- Each LLM call in the agent loop gets its own reservation
- Reserve and settle use separate DB sessions (reserve must commit before provider call)
- Idempotency key: `agent-llm:{run_id}:{message_id}`
- Tool billing follows the same pattern in `Function._reserve_tool_billing()` / `_finalize_tool_billing()`

#### Path 2: `LLMExecutionService` (`core/llm/execution_service.py`)

Used for **single LLM invocations** outside the agent loop (e.g., storybook AI edits, content generation, any service that needs one LLM call with billing).

```python
# Single call:
response = await execution_service.send_once(
    client=client,
    messages=messages,
    tools=tools,
    billing_context=LLMBillingContext(
        db=db,
        scope=BillingScope.for_session(
            user_id=user.id,
            app_kind="chat",
            session_id=session_id,
        ),
        llm_config=llm_config,
    ),
    usage_key="my_feature:unique_key",
)

# Multi-step tool loop:
result = await execution_service.run_tool_loop_until_final(
    client=client,
    messages=messages,
    tools=tools,
    final_tool_name="submit_result",
    tool_registry=registry,
    max_loops=5,
    billing_context=billing_context,
)
```

`LLMExecutionService` handles the full reserve → settle → release lifecycle internally:
- `_reserve_if_needed()` → `LLMBillingService.reserve_chat_llm_call()`
- `_settle_if_needed()` → `LLMBillingService.settle_chat_llm_call()`
- `_release_reservation()` → `LLMBillingService.release_llm_call()`
- `_mark_settlement_failed()` on settle exceptions
- Records `llm_invocations` telemetry for each call

### Rules for New Code

#### Adding a new feature that calls an LLM

**Always use `LLMExecutionService`** for any new code that needs to make LLM calls outside the agent runtime loop. Do NOT call LLM providers directly or use `CreditService.deduct()`.

```python
from ii_agent.billing.types import BillingScope
from ii_agent.core.llm.execution_service import LLMExecutionService, LLMBillingContext

# 1. Get the execution service from the container
execution_service = container.llm_execution_service

# 2. Create billing context
billing_context = LLMBillingContext(
    db=db,
    scope=BillingScope.for_session(
        user_id=str(user.id),
        app_kind="chat",
        session_id=session_id,
    ),
    llm_config=llm_config,
    model_id=llm_config.model,
)

# 3. Call send_once (single LLM call) or run_tool_loop_until_final (multi-turn)
response = await execution_service.send_once(
    client=LLMExecutionService.create_client(llm_config),
    messages=messages,
    billing_context=billing_context,
    usage_key="my_feature:unique_operation_id",
)
```

#### Adding a new agent flow

New agent flows (new socket command handlers, new agent types) must follow the same pattern as `query_handler` / `plan_handler`:

1. **Pre-validation**: Call `validate_and_update_session()` to check `BillingStatus == OK` (account health only — do not check credit balance here)
2. **Agent creation**: Wire `llm_billing_service` into the model via `ToolDependencies` / factory
3. **Execution**: The agent's `arun()` / `aresponse_stream()` loop handles per-call billing automatically through `Model.aprocess_response_stream()`
4. **No post-run billing**: Do NOT add billing logic after the agent loop — all billing is handled per-call inside the loop

#### Adding a new billable tool

Tools that incur external costs must:

1. Set `max_cost_usd` on the tool class (upper bound for reservation)
2. Override `quote_cost()` if the cost depends on input parameters
3. Return the actual cost in `ToolResult(cost=actual_usd)`

```python
class MyTool(BaseAgentTool):
    max_cost_usd: float = 0.10

    async def quote_cost(self, tool_input: dict) -> BillingQuote | None:
        estimated = calculate_cost(tool_input)
        return BillingQuote(strategy="bounded", reserve_usd=estimated, max_usd=estimated)

    async def arun(self, ...) -> ToolResult:
        result = await external_api(...)
        return ToolResult(llm_content="done", cost=result.actual_cost)
```

The `Function` wrapper handles `_reserve_tool_billing()` → execute → `_finalize_tool_billing()` automatically.

#### Adding a new billing subject (Factory example)

If you add Factory billing, keep the subject and the node execution separate:

- `subject_kind = factory_project` (or `factory_run` if run-level history is primary)
- `subject_id = factory_id`
- `billing_context = factory`
- `run_id = factory_run_id`
- `operation_id = node_execution_id` or `f"{node_id}:{attempt}"`

Recommended shape:

1. Add a new `SubjectKind` and a scope builder like `BillingScope.for_factory_project(...)`
2. Keep `app_kind` as the actual launcher (`chat` or `agent`) until Factory becomes a first-class app surface
3. Use `billing_context = BillingContextValue.FACTORY` to distinguish Factory from chatloop/agentloop
4. Use `source_domain` for the billing-producing subsystem, not for the product surface:
   - good: `factory_llm`, `factory_tool`, `factory_render`
   - avoid: using `factory` as both `billing_context` and `source_domain`
5. Use `scope.build_operation_key(namespace, operation_id)` for idempotency
6. Put `node_id`, `node_type`, and `factory_run_id` into billing metadata for query/debugging

Why this split matters:

- query all billing for one Factory: filter by `subject_kind/subject_id`
- query all billing for one Factory run: filter by `run_id`
- dedupe one node execution: use `operation_id`
- distinguish LLM vs tool vs render inside Factory: use `source_domain`

Use the existing billing layers:

- `LLMExecutionService.send_once(...)` for node-local LLM calls
- `run_billed_operation(...)` for bounded synchronous non-LLM work
- `reserve_billing_operation(...)` + `finalize_billing_operation(...)` for async/background non-LLM work
- `CreditReservationService.reserve()` / `capture_settlement_input()` / `settle()` / `release()` only when the shared helpers do not fit the flow shape

For bounded synchronous non-LLM work, use this shape:

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
        usage_payload={**scope.billing_metadata(), **render_result.usage_payload},
    )
```

For async/background work, reserve before enqueueing the job and persist the
`reservation_id` with the job payload. In the worker:

1. Reserve with `reserve_billing_operation(...)`
2. Persist `reservation_id` with the job payload or owner record
3. In the worker, call `finalize_billing_operation(...)`

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

Keep reserve and finalize in separate DB sessions. Do not hold the reservation
transaction open across provider work.

#### Anti-patterns (DO NOT)

```python
# BAD: Direct credit deduction for LLM/tool work
await credit_service.deduct(db, user_id, amount, ...)
# No reservation hold, no refund on failure, no idempotency

# BAD: Calling LLM providers without billing
response = await client.send(messages=messages)
# No credit check, no cost tracking, no usage record

# BAD: Building custom reserve/settle logic outside the billing services
reservation = await reservation_service.reserve(db, ...)
response = await provider.send(...)
await reservation_service.settle(db, ...)
# Use LLMBillingService or LLMExecutionService instead — they handle
# quoting, token estimation, output cap, error paths, and telemetry

# BAD: Post-run bulk billing in handlers
total_cost = sum(metrics)
await credit_service.deduct(db, user_id, total_cost)
# Billing is per-call inside the agent loop, not post-run
```

### Settlement Recovery

Settlement is synchronous. Before the final `settle()` call, the exact settlement input is captured onto the reservation metadata. If provider work completes but final settlement raises, the reservation is moved to `SETTLEMENT_FAILED` so stale-expiry does not refund delivered work and ops can replay settlement manually from the captured payload.

Cron jobs in `workers/cron/billing_recovery.py`:
- `expire_stale_reservations` (every 15 min) — releases RESERVED holds past `expires_at`
- `alert_settlement_failures` (every 5 min) — logs SETTLEMENT_FAILED reservations

### Validation Flow

Pre-execution validation (`agent/application/validation_service.py`) checks **account health only** — whether `billing_status == OK`. It does NOT check credit balance sufficiency. The actual credit gate is the first `_reserve_llm_billing()` call inside the agent loop, which raises `InsufficientCreditsError` if the user can't afford at least 128 output tokens.

### Key Files

| File | Purpose |
|------|---------|
| `core/llm/billing_service.py` | `LLMBillingService` — quoting, reserve/settle/release orchestration |
| `core/llm/execution_service.py` | `LLMExecutionService` — single LLM calls & tool loops with billing |
| `billing/reservations/service.py` | `CreditReservationService` — reservation state machine |
| `billing/credits/service.py` | `CreditService` — ledger + balance mutations |
| `billing/credits/pricing.py` | `ModelPricing` — per-model token prices |
| `agent/runtime/models/base.py` | Agent runtime billing hooks (`_reserve/_settle/_release_llm_billing`) |
| `agent/runtime/tools/function.py` | Agent tool billing hooks |
| `billing/usage/service.py` | `UsageService` — usage_records + session_metrics |
| `workers/cron/billing_recovery.py` | Cron jobs for stale reservation cleanup and settlement failure alerting |

## Key Files

| File | Purpose |
|------|---------|
| `app/` | FastAPI bootstrap package: app factory, router registration, lifespan, middleware |
| `core/config/settings.py` | Pydantic settings (get_settings singleton) |
| `core/db/base.py` | SQLAlchemy Base, TimestampColumn |
| `core/db/manager.py` | get_db_session_local, SessionLocal |
| `core/redis/` | Redis client, cache, pubsub, lock, cancel management |
| `core/storage/` | File storage abstraction (GCS, local) |
| `core/secrets/` | Secrets management (GCP Secret Manager) |
| `auth/dependencies.py` | CurrentUser, DBSession, get_current_user |
| `engine/v1/` | V1 agent architecture with tools, skills, and multi-provider LLM support |
