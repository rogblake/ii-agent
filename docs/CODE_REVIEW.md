# Code Review — `refactor/support-application-features-options`

**Date:** 2026-03-29
**Branch:** `refactor/support-application-features-options`
**Scope:** 261 files changed, +2750 / -2315 lines
**Verdict:** BLOCK

---

## CRITICAL (11 issues — must fix before merge)

### C1. Deleted `billing.usage.*` / `billing.customers.*` modules — 12+ broken imports

**Files importing deleted modules:**
- `chat/llm/custom.py`, `chat/llm/gemini.py`, `chat/llm/openai.py`, `chat/llm/anthropic/provider.py`, `chat/messages/service.py`, `chat/messages/history_service.py`, `chat/types.py`, `chat/api/schemas.py` — `from ii_agent.billing.usage.models import TokenUsage`
- `content/storybook/voice_service.py`, `content/storybook/ai_edit_service.py` — `from ii_agent.billing.usage.service import UsageService`
- `content/storybook/router.py` — `from ii_agent.billing.usage.dependencies import UsageServiceDep`
- `workers/cron/refresh_annual_subscription_credits.py`, `workers/cron/refresh_free_user_credits.py` — `from ii_agent.billing.credit_repository import CreditRepository`, `from ii_agent.billing.customers.repository import BillingCustomerRepository`, `from ii_agent.billing.customers.service import BillingCustomerService`

**Impact:** `ModuleNotFoundError` at startup or at cron execution time.
**Fix:** Migrate these modules to their new locations or create thin re-export shims.

---

### C2. Deleted `core/llm/` directory — 5 broken imports

**Files importing from deleted `core/llm/`:**
- `sessions/title_service.py:14`
- `integrations/enhance_prompt/client.py:16`
- `content/slides/nano_banana/service.py:25`
- `content/storybook/ai_edit_service.py:30`
- `projects/design/service.py:36`

All import `LLMExecutionService` and/or `LLMBillingContext` from `ii_agent.core.llm.execution_service`.

**Impact:** `ModuleNotFoundError` at startup.
**Fix:** Locate where `LLMExecutionService` / `LLMBillingService` now live and update all import sites.

---

### C3. `sessions/models.py:88-93` — `viewonly=True` + `cascade="all, delete-orphan"`

```python
events: Mapped[list["ApplicationEvent"]] = relationship(
    "ApplicationEvent",
    primaryjoin="Session.id == foreign(ApplicationEvent.session_id)",
    cascade="all, delete-orphan",
    viewonly=True,  # CONFLICT
)
```

**Impact:** SQLAlchemy raises `InvalidRequestError` at mapper configuration time — startup crash.
**Fix:** Remove `viewonly=True` (and add `back_populates`), or remove `cascade="all, delete-orphan"` and rely on DB-level `ON DELETE CASCADE`.

---

### C4. `agents/runs/agent.py:484` — Broken `RunEvent` type alias

```python
RunEvent = type[BaseRunOutputEvent]
```

Used as `RunEvent.run_content_delta`, `RunEvent.reasoning_delta`, `RunEvent.custom_event` — none of these attributes exist on `type[BaseRunOutputEvent]`.

**Impact:** `AttributeError` on every agent initialization (`IIAgent.__post_init__`).
**Fix:** Restore `RunEvent` as a `StrEnum`:

```python
class RunEvent(str, Enum):
    run_content_delta = "RunContentDelta"
    reasoning_delta = "ReasoningDelta"
    custom_event = "CustomEvent"
    # ... remaining values
```

---

### C5. `agents/tools/task.py:2` — Runtime `IIAgent` import (circular import risk)

```python
from ii_agent.agents.agent import IIAgent  # runtime, not TYPE_CHECKING
```

**Impact:** Circular import crash depending on module load order.
**Fix:** Move under `if TYPE_CHECKING:` and use string annotation.

---

### C6. `agents/tools/connectors/github.py:7` — Same as C5

**Fix:** Guard under `TYPE_CHECKING`.

---

### C7. `content/storybook/dependencies.py:86,94` — Zero-arg construction of services requiring mandatory kwargs

```python
def _get_storybook_voice_service(container: ContainerDep) -> StorybookVoiceService:
    return getattr(container, "storybook_voice_service", None) or StorybookVoiceService()
```

`StorybookVoiceService()` and `StorybookAIEditService()` require mandatory keyword arguments (`repo`, `storybook_service`, `config`, etc.).

**Impact:** `TypeError` on every request using these deps.
**Fix:** Wire both services into `ApplicationContainer`, or raise `NotImplementedError`. Remove `getattr` fallback (violates project rules).

---

### C8. `projects/design/service.py:1565` — `emit_event` called on `EventRepository`

```python
from ii_agent.realtime.events.repository import EventRepository as EventService  # TYPE_CHECKING alias
self._event_service.emit_event(progress_event)  # EventRepository has no emit_event method
```

**Impact:** `AttributeError` at runtime on any design session progress event.
**Fix:** Replace with correct pub/sub mechanism or restore a proper `EventService` wrapper.

---

### C9. Tests — `EventType` enum values don't exist in new module

**Files:** `test_subscribers_r4.py`, `test_socket_handlers_r4.py`, `test_a2a_event_stream.py`, `test_handler_billing.py`

Tests reference `EventType.TOOL_CALL_STARTED`, `.TOOL_CALL_COMPLETED`, `.RUN_CONTENT`, `.RUN_CONTENT_DELTA`, `.SUB_AGENT_COMPLETED`, `.RUN_INTERRUPTED`, `.REASONING_DELTA`, `.REASONING_COMPLETED`, `.AGENT_INITIALIZED`, `.WORKSPACE_INFO`, `.SANDBOX_STATUS` — none exist in the new `EventType` enum.

**Impact:** `AttributeError` at test collection.
**Fix:** Add missing members to `EventType` or update tests to use new typed event classes.

---

### C10. Tests — `EventGroup` sub-values don't exist

**Files:** `test_subscribers_r4.py`, `test_socket_handlers_r4.py`

Tests use `EventGroup.AGENT_TOOL`, `.AGENT_RUN`, `.AGENT_REASONING`, `.USER` — collapsed into `AGENT`/`SESSION` in the new enum.

**Impact:** `AttributeError` at test collection.
**Fix:** Update to `EventGroup.AGENT` / `EventGroup.SESSION`.

---

### C11. Tests — `agents.models.builder.MessageBuilder` module doesn't exist

**File:** `test_v1_agent_main_r4.py`

`from ii_agent.agents.models.builder import MessageBuilder` — no such file.

**Impact:** `ModuleNotFoundError` at test collection.
**Fix:** Locate where `MessageBuilder` lives now or remove test class.

---

## HIGH (14 issues — should fix before merge)

### H1. `users/models.py:141` — `WaitlistEntry` dual primary key

`WaitlistEntry` inherits `Base` (UUID `id` PK) but also declares `email` as `primary_key=True` — creates composite PK. Also shadows `Base.created_at`.

**Fix:** Don't inherit from `Base`, or remove `primary_key=True` from `email` and use `UniqueConstraint`.

---

### H2. `billing/__init__.py` — Removed lazy `__getattr__` import guard

Removed deliberate circular-import safety for `router` import. Now a direct top-level import.

**Fix:** Acceptable if import graph validated. Add comment or reinstate lazy pattern.

---

### H3. `files/types.py` — `AssetType.MEDIA` removed without data migration

Replaced by `IMAGE/VIDEO/AUDIO`. Existing DB rows with `"media"` will crash on load.

**Fix:** Add Alembic migration to backfill `"media"` values, or validate no such data exists.

---

### H4. `agents/sessions/__init__.py` — `AgentSummary` not exported

`AgentSummary = SessionSummary` alias defined in `summary.py` but not re-exported from `__init__.py`.

**Fix:** Add `from .summary import AgentSummary` to `__init__.py`.

---

### H5. 9 locations across `agents/` — Local imports inside functions

Violates project rule: "NEVER use local imports inside functions/methods."

Files: `runs/base.py:215,221`, `models/base.py:1424,1479`, `runs/events.py:557`, `tools/function.py:36`, `models/anthropic/claude.py:203,220`, `models/google/gemini.py:118`, `models/google/interactions.py:104`, `tools/web/read_remote_image.py:78,90`

---

### H6. `content/storybook/models.py:75` — `remote_side` as string

```python
remote_side="Storybook.id"  # SQLAlchemy expects column objects, not strings
```

**Impact:** `ArgumentError` at startup.
**Fix:** Revert to `remote_side=[id]`.

---

### H7. `projects/dependencies.py:82-94` — Silent no-op stub for sandbox env sync

`_SandboxEnvSyncServiceStub.sync_env_files` is a no-op. Users saving secrets get 200 but sandbox never updated.

**Fix:** Add `logger.warning()` and create tracking issue.

---

### H8. `realtime/schemas.py:129-137` — Dead backward-compat re-exports

`EventInfo`, `EventResponse`, `SessionInfo`, `SessionResponse` re-exported but zero callers found.

**Fix:** Remove dead re-exports.

---

### H9. Frontend — `srcDoc` iframe sandbox defeated (pre-existing)

`sandbox="allow-scripts allow-same-origin"` on `srcDoc` iframes allows sandbox escape.

**Files:** `storybook-edit-wrapper.tsx`, `design-mode-wrapper.tsx`, `use-design-mode.ts`, `slide-design-mode-view.tsx`

**Fix:** Remove `allow-same-origin` from `srcDoc` iframes.

---

### H10. Frontend — `postMessage` to `'*'` wildcard (pre-existing)

Same 4 files send `postMessage` with `'*'` target origin.

**Fix:** Replace with `window.location.origin`.

---

### H11. `upload.service.ts:41-79` — 5 upload methods not migrated

`uploadFromUrl`, `getUploadedFiles`, `checkFileExists`, `validateFile`, `uploadWithFormData` still use `/api/upload/…` instead of `/v1/…`.

**Fix:** Migrate to `/v1/…` paths or confirm old routes still exist.

---

### H12. Tests — `agents.subscribers.*` modules don't exist

**File:** `test_subscribers_r4.py`

Imports from `ii_agent.agents.subscribers.subscriber`, `database_subscriber`, `socketio_subscriber` — modules were moved to `realtime.pubsub.callbacks`.

**Fix:** Update import paths.

---

### H13. Tests — Mock paths target non-existent agent internals

**File:** `test_v1_agent_main_r4.py`

Patches target `ii_agent.agents.agent.ServiceContainer`, `.SandboxProvider`, `.ToolManager`, `.ResponseHandler`, `.HookExecutor`, `.HITLHandler`, `.DelegationManager` — none exist in `agents/agent.py` namespace.

**Fix:** Trace each class to its actual import location and update patch targets.

---

### H14. Tests — Deleted `TestGetLLMLoopService` coverage

**File:** `test_chat_dependencies.py`

`LLMTurnLoopService` DI wiring has zero test coverage after test class deletion.

**Fix:** Add container-based test for `LLMTurnLoopService` dependency injection.

---

## MEDIUM (8 issues — fix when possible)

| # | File | Issue |
|---|------|-------|
| M1 | `sessions/schemas.py` | `model_config = {"extra": "allow"}` — use `ConfigDict(extra="allow")` |
| M2 | `core/config/session_title.py` | Uses deprecated `class Config` instead of `model_config = SettingsConfigDict(...)` |
| M3 | `core/config/session_title.py:8` | Default model `"gpt-5-mini"` doesn't exist — should be `"gpt-4o-mini"` |
| M4 | Frontend service files | Interpolated path segments not URL-encoded |
| M5 | `session.service.ts` | `session_id` in hand-built query string — use `params` object |
| M6 | `content/media/service.py` | Imports private `_get_client` across domain boundary |
| M7 | `projects/__init__.py` | Lazy `__getattr__` inconsistent with other domains' eager exports |
| M8 | Frontend service files | `console.warn`/`console.error` in production code (pre-existing) |

---

## Suggested Fix Priority

1. **Restore deleted module shims** or update all import paths for `billing.usage.*`, `billing.customers.*`, `core/llm/*` (C1, C2)
2. **Fix `RunEvent`** as `StrEnum` in `agents/runs/agent.py` (C4)
3. **Fix `sessions/models.py`** — remove `viewonly=True` or `cascade` (C3)
4. **Fix `storybook/dependencies.py`** — wire into container or raise `NotImplementedError` (C7)
5. **Fix `storybook/models.py`** — revert `remote_side` to `[id]` (H6)
6. **Fix `projects/design/service.py`** — replace `emit_event` with correct pub/sub (C8)
7. **Guard `IIAgent` imports** under `TYPE_CHECKING` in `task.py` and `github.py` (C5, C6)
8. **Update test mock paths** and event type references (C9-C11, H12-H14)
9. **Migrate `upload.service.ts`** endpoints to `/v1/` paths (H11)
10. **Address remaining HIGH** (H1-H5, H7-H10)
