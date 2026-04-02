# II-Agent Architecture Design Flaws Report

> Generated: 2026-02-21
> Scope: Full deep review of `src/ii_agent/*`

---

## Table of Contents

- [1. Critical Issues](#1-critical-issues)
- [2. High Issues](#2-high-issues)
- [3. Medium Issues](#3-medium-issues)
- [4. Low Issues](#4-low-issues)
- [5. Domain Health Summary](#5-domain-health-summary)
- [6. Recommended Refactoring Priority](#6-recommended-refactoring-priority)

---

## 1. Critical Issues

### 1.1 ~~Socket Command Handlers Contain Full Service Logic~~ ✅ FIXED

Business logic extracted from all socket command handlers into dedicated services:

- **`agents/execution_service.py`** (`ExecutionService`): Task creation with locking (`create_task_with_lock`), milestone context generation (`get_milestone_context`), milestone status updates (`update_milestones_after_run`) — extracted from `query_handler.py` and `plan_handler.py`
- **`agents/plan_service.py`** (`PlanService`): Plan existence checking (`has_existing_plan`), plan data retrieval (`get_plan_data`), plan persistence (`save_and_emit_plan`), task failure handling (`fail_task`) — extracted from `plan_handler.py`
- **`projects/deployment_orchestration_service.py`** (`DeploymentOrchestrationService`): Project path/name resolution, deployment context creation, deployment status updates, successful deployment finalization, shell quoting, output cleanup/redaction, URL extraction — extracted from `publish_handler.py` and `cloud_run_publish_handler.py`
- **`sessions/service.py`** (`SessionValidationResult`, `validate_and_prepare_session`): Session validation, credit checking, LLM config retrieval — extracted from `command_handler.py`
- **`files/service.py`** (`prepare_agent_files`, `get_files_by_ids_and_update_session`): File preparation for agents — extracted from `query_handler.py` and `plan_handler.py`
- **`sandboxes/service.py`** (`resolve_sandbox_for_session`): Shared sandbox lookup with forked-session fallback — extracted from 4 handlers

Handlers now delegate to services and retain only transport concerns (event emission, agent creation, streaming). All 3 new services registered in `ServiceContainer`.

---

### 1.2 User Creation Logic in Auth Router (Not Users Domain)

`auth/router.py:270-299, 506-541` -- Auth router directly creates `User()` and `APIKey()` objects on login instead of delegating to `UserService`.

- Lines 271-288: Direct `User()` instantiation in `ii_callback`
- Lines 290-298: Direct `APIKey()` creation
- Lines 508-529: **Duplicate** user creation in `google_callback`
- Lines 532-540: **Duplicate** API key creation
- Lines 286-288: Direct `db.add()` and `db.commit()` without proper error handling

`auth/router.py:558-589` -- User profile endpoints are in auth router instead of users router:
- `PATCH /auth/me/language` (lines 563-578)
- `DELETE /auth/me` (lines 581-589)

**Meanwhile `users/router.py` is empty with just a TODO comment.**

**Fix:** Create `UserService.create_user()`, `UserService.update_language()`, `UserService.delete_user()`. Move profile endpoints to `users/router.py`.

---

### 1.3 Chat Service Manages Sessions and Agent Runs Directly

`chat/service.py` crosses multiple domain boundaries:

- **Lines 105-146:** `create_chat_session()` -- Creates `Session` model directly (`db.add(session); await db.commit()`) instead of delegating to `SessionService`
- **Lines 148-180:** `update_session_name_if_untitled()` -- Performs SQL UPDATE on Session table directly
- **Lines 20-21:** Imports `AgentRunTask`, `RunStatus`, `AgentRunTaskRepository`
- **Lines 407-414:** Creates `AgentRunTask` in the middle of chat streaming logic
- **Lines 776-810:** Updates `AgentRunTask` status directly
- **Lines 1020-1077:** `_load_connector_tools()` queries Connector table and instantiates tool classes directly

**Fix:** Delegate session creation to `SessionService`, agent run lifecycle to `AgentRunService`, tool loading to a `ToolOrchestrationService`.

---

### 1.4 Billing/Credits Directly Modify User Model Fields

`billing/service.py` directly sets User model fields across 4+ webhook handlers:

- Line 375: `user.subscription_plan = plan_id`
- Line 376: `user.subscription_status = status`
- Line 377-378: `user.subscription_billing_cycle = resolved_billing_cycle`
- Line 379-380: `user.stripe_customer_id = customer_id`
- Line 382: `user.subscription_current_period_end = ...`
- Line 384: `user.credits = credits`

Same pattern in:
- `_handle_checkout_session_completed()` (lines 316-406)
- `_handle_invoice_payment_succeeded()` (lines 408-498)
- `_handle_subscription_deleted()` (lines 500-560)
- `_handle_subscription_updated()` (lines 562-648)

`credits/service.py` directly updates `User.credits` and `User.bonus_credits`:

- Lines 110-134: SQL update on User.credits and User.bonus_credits
- Lines 200-215: Direct User model updates
- Lines 261-265: Direct User model field assignment

**Root cause:** Billing fields (`stripe_customer_id`, `subscription_plan`, `subscription_status`, `subscription_billing_cycle`, `subscription_current_period_end`) and credit fields (`credits`, `bonus_credits`) are on the `User` model (`users/models.py:71-83`) instead of separate models.

**Fix:** Inject User Repository in Billing service and add methods inside user repo

---

### 1.5 ~~Business Logic Leaked into `core/db/manager.py`~~ ✅ FIXED

Business logic extracted to domain modules:
- `seed_admin_llm_settings()` → `llm_settings/seeding.py`
- `ensure_builtin_skills_synced()` → `skills/seeding.py`
- Initialization called from `app.py` lifespan handler instead of module load time

---

### 1.6 Google Drive File Operations in Connectors Router

`connectors/router.py:225-429` -- The `download_google_drive_files` endpoint contains 200+ lines of business logic:

- Line 244: `from ii_agent.files import FileUpload` (importing files model in connectors)
- Lines 370-376: Direct `FileUpload` model instantiation
- Line 368: Direct `storage.write()` call in router
- Lines 366-421: All file creation/storage logic

**Fix:** Extract to `FileService.store_from_connector()`.

---

### 1.7 ~~Project Secrets Service Coupled to Sandboxes~~ ✅ RESOLVED

~~`projects/secrets/service.py` has deep coupling to the sandboxes domain:~~

- ~~Lines 17-19: Imports `SandboxRepository`, `SessionRepository`, `E2BSandboxManager`~~
- ~~Lines 192-245: `update_sandbox_env_files()` directly manages `.env` and `.user_env.sh` files in sandbox environments~~
- ~~Lines 76-101: `add_secrets_and_sync` -- mixes secret persistence with sandbox file sync~~
- ~~Lines 103-128: `save_secrets_and_sync` -- same pattern~~
- ~~Lines 247-301: Sandbox-specific file parsing and formatting methods~~

**Resolution:** `SecretService` now handles DB persistence only -- all sandbox imports removed. Sandbox env file syncing extracted to `sandboxes/env_sync_service.py` (`SandboxEnvSyncService.sync_env_files()`). Secrets router calls both services separately via DI (`SecretServiceDep` + `SandboxEnvSyncServiceDep`).

---

## 2. High Issues

### 2.1 Session Model is a God Object

`sessions/models.py` -- Session has relationships to **every domain**:

- `events` (events domain)
- `file_uploads` (files domain)
- `slide_contents`, `slide_versions` (slides domain)
- `storybooks` (storybook domain)
- `wishlisted_by` (wishlist domain)
- `databases` (projects domain)

All with `cascade="all, delete-orphan"` -- deleting a session deletes all events, files, slides, etc.

**Decision:** Backward relationships **kept intentionally** — ORM-level cascade ensures proper cleanup when sessions are deleted. DB-level `ondelete="CASCADE"` alone is insufficient when the ORM session has objects loaded in the identity map.

---

### 2.2 ~~Sessions Import Agents (Reverse Dependency)~~ ✅ FIXED

Sessions now use `AgentRunService` (injected) instead of importing `AgentRunTaskRepository` directly. Chat service also updated to use `AgentRunService`.

---

### 2.3 ~~Sandbox Lookup Duplicated 4 Times~~ ✅ FIXED

Consolidated into `SandboxService.resolve_sandbox_for_session()` — handles direct lookup by session_id with forked-session fallback via `session.sandbox_id`. All 4 handlers (`sandbox_status_handler`, `awake_sandbox_handler`, `publish_handler`, `cloud_run_publish_handler`) updated to use the single service method.

---

### 2.4 ~~Duplicate `load_connector_tools` Function~~ ✅ FIXED

Duplicate removed from `connectors/service.py`. Canonical version kept in `connectors/tools_loader.py`.

---

### 2.5 ~~`core/config/agent_config.py` Imports from Domain~~ ✅ FIXED

File deleted entirely — was broken (referenced non-existent `agents.beta.llm.base` module) and unused by any module.

---

### 2.6 `SlideContentProcessor` Misplaced in Slides Domain

`slides/content_processor.py:18-282` -- Complex utility class mixing:

- File path resolution (lines 168-199)
- Storage operations (lines 94-166)
- Cache management (lines 29-30, 133-148)
- URL generation
- Direct import from sandboxes: `from ii_agent.sandboxes.base import SandboxManager` (line 13)

**Fix:** Move to `tools/content_processing/` or inject `SandboxManager` via dependency injection.

---

### 2.7 Incomplete Users Domain

- `users/router.py` -- Empty with just a TODO
- `users/service.py` -- Only 3 methods, missing `create_user()`, `update_user()`, `delete_user()`, `create_api_key()`
- `users/repository.py` -- No `create()` or `update()` methods
- `users/repository.py:28-34` -- `lookup_by_customer_id()` is billing-specific but in users repo

---

### 2.8 Database Access in SandboxManager Base Class

`sandboxes/base.py:87-121` -- `_update_sandbox_db()` opens its own DB session and creates `SandboxService` instance inside the method, creating circular dependency (base.py imports from service.py).

**Fix:** DB updates should be called by `SandboxService`, not the manager.

---

## 3. Medium Issues

### 3.1 Router Contains Business Logic (Multiple Domains) — Partially Resolved

| Location | What | Status |
|----------|------|--------|
| ~~`chat/router.py:55-106`~~ | ~~`_fetch_file_attachments_for_messages()` -- data access in router~~ | ✅ Moved to `ChatService._fetch_file_attachments()` |
| ~~`chat/router.py:109-160`~~ | ~~`_build_message_history_response()` -- message formatting in router~~ | ✅ Moved to `ChatService.build_message_history_response()` |
| ~~`mcp_settings/router.py:48-134`~~ | ~~`configure_codex_mcp()`, `configure_claude_code_mcp()` -- complex business logic~~ | ✅ Moved to `MCPSettingService.configure_codex()` / `configure_claude_code()` |
| ~~`mcp_settings/router.py:157-186`~~ | ~~`exchange_code_for_tokens()` -- OAuth token exchange logic~~ | ✅ Moved to `mcp_settings/service.py::_exchange_code_for_tokens()` |
| `storybook/router.py:23` | Imports and calls `_generate_image` from tools | Kept (callback injection pattern is acceptable) |
| ~~`storybook/router.py` voiceover~~ | ~~Credit deduction logic inline in router~~ | ✅ Moved to `StorybookService.generate_voiceover_and_deduct_credits()` |
| ~~`storybook/router.py` cancel~~ | ~~Generation status parsing inline in router~~ | ✅ Moved to `StorybookService.get_generation_status()` |
| ~~`media/router.py:91-92,122-138`~~ | ~~Cache management (`_media_tools_cache`) in router layer~~ | ✅ Moved to `MediaTemplateService.list_media_tools()` / `get_media_tool()` |
| ~~`media/router.py` reference image~~ | ~~File creation/storage ops in router~~ | ✅ Moved to `MediaTemplateService.generate_reference_image()` |
| `projects/schemas.py:31-36` | Decryption logic inside Pydantic validator | Open |

---

### 3.2 Deployment Service Modifies Project State

`projects/deployments/service.py:150-170` -- `set_active_deployment()` directly modifies `project.production_url`. Creates bidirectional coupling: Projects <-> Deployments.

**Fix:** Use event pattern -- deployment service emits "deployment_activated", project service listens and updates.

---

### 3.3 ~~Cross-Domain Service Injection in LLM Settings~~ ✅ FIXED

Heavy `SessionService` dependency replaced with lightweight `SessionRepository` injection. `LLMSettingService` now takes `session_repo: SessionRepository` (required, injected via `SessionRepositoryDep` in DI). `get_llm_settings()` accepts `session: SessionInfo` and resolves `llm_setting_id` via the repository internally.

---

### 3.4 Chat Tools Import Session Service

- `chat/tools/storybook_generate.py:15` -- `from ii_agent.sessions.service import SessionService`
- `chat/tools/image_generate.py:21` -- same import
- `chat/media/utils/state_manager.py:8` -- `from ii_agent.sessions.models import Session`

**Fix:** Chat tools should receive necessary data as parameters, not import session service.

---

### 3.5 Slides Service Imports Session Repository

`slides/service.py:15` -- `from ii_agent.sessions.repository import SessionRepository`

**Fix:** Use `SessionService` instead, or create `SessionGateway` abstraction.

---

### 3.6 MCP SSE Module Mixes Too Many Concerns

`mcp_sse/widgets.py` imports from 5+ domains:
- `ii_agent.sessions.service` (line 23)
- `ii_agent.events.repository` (line 24)
- `ii_agent.connectors.service` (line 25)
- `ii_agent.users.service` (line 26)
- `ii_agent.auth.jwt_handler` (line 27)

`mcp_sse/oauth.py:43-52` -- In-memory dictionaries for OAuth tokens and authorization codes (no Redis, breaks in distributed deployment).

`mcp_sse/agent.py:14-27` -- Mixes MCP SSE protocol handling with agent execution logic.

---

### 3.7 All `tools/` Depend on V1 Base Classes

- `tools/a2a_agent_tool.py:15` -- `from ii_agent.v1.tools.base import BaseAgentTool`
- `tools/milestone_tool.py:4` -- `from ii_agent.v1.tools.base import BaseAgentTool`
- `tools/image_generation/service.py:6` -- `from ii_agent.v1.tools.clients import _get_client`

**Fix:** Create modern base class for tools independent of V1.

---

### 3.8 Skills Service Depends on V1

`skills/service.py:22-27`:
```python
from ii_agent.v1.skills.github import GitHubDownloadService, GitHubSkillError
from ii_agent.v1.skills.skills_ref.errors import ParseError, ValidationError
from ii_agent.v1.skills.storage import upload_skill_to_gcs
```

**Fix:** Migrate these utilities to a dedicated module within skills.

---

### 3.9 Business Logic in DatabaseSubscriber

`subscribers/database_subscriber.py:48-65` -- File processing logic that detects result types, calls storage service, and mutates event content:

```python
if isinstance(tool_result, dict) and tool_result.get("type") == "file_url":
    async with get_db_session_local() as db:
        file_data = await self._container.file_service.write_file_from_url(...)
    event.content["result"]["file_id"] = file_data.id
```

`subscribers/database_subscriber.py:29-43` -- Event filtering logic with comments like "manually saved in query_handler.py" revealing duplication.

`subscribers/subscriber.py:28-37` -- Base class opens database session to check run status in `should_handle()`.

---

### 3.10 A2A Server Tight Coupling

`a2a/as_server.py:14-41` -- Imports `AgentController`, `EventRepository`, `AgentRunTaskRepository`
`a2a/as_server.py:62-74` -- Lazy initialization of dependencies (implicit dependency injection)

**Fix:** Use proper dependency injection from container.

---

### 3.11 Project Model Architecture Issues

`projects/models.py:42-43` -- Database/storage/secrets stored as JSON blobs:
```python
database_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
storage_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
secrets_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
```

`ProjectDatabase` exists separately in `databases/models.py` but is not connected to Project via relationship.

---

### 3.12 ~~File Preparation Logic Duplicated~~ ✅ FIXED

Extracted to `FileService.prepare_agent_files()` and `FileService.get_files_by_ids_and_update_session()`. Both `query_handler.py` and `plan_handler.py` now call the shared service methods via thin `_prepare_files()` wrappers that convert dicts to v1 `Image`/`UrlFile` types.

---

### 3.13 Handler-to-Handler Dependencies

`socket/command/start_fork_handler.py:32-41` -- Constructor injection of `UserQueryHandler`
`socket/command/start_fork_handler.py:95` -- Direct delegation: `await self._query_handler.handle(...)`

**Fix:** Delegate to a service, not another handler.

---

## 4. Low Issues

### 4.1 V1 is Mislabeled "Legacy"

`v1/legacy/__init__.py` says "Backward compatibility tools from V0, will remove it later" -- but V1 is the **active agent execution framework** used by socket handlers, with 50+ tools, LLM providers, and active development. It is NOT legacy.

Two parallel sandbox implementations exist:
- Main: `sandboxes/` (lifecycle management via HTTP API)
- V1: `v1/sandboxes/` (execution-time management)

V1 credits has its own `ModelPricing` model (`v1/credits/models.py`) separate from main credits module.

---

### 4.2 Incomplete Domain Exports

- `skills/__init__.py` -- Only exports `router`, missing `Skill`, `SkillService`
- `files/__init__.py` -- Empty
- `users/router.py` -- Empty with TODO

---

### 4.3 Empty Placeholder Files

- `projects/constants.py` -- empty
- `projects/utils.py` -- empty
- `connectors/schemas.py` -- empty
- `connectors/constants.py` -- empty
- `media/config/__init__.py` -- empty directory

---

### 4.4 Vectorstore is a Backward-Compat Shim

`vectorstore/base.py` and `vectorstore/openai.py` just re-export from `ii_agent.chat.vectorstore`. Should be removed once all imports are updated.

---

### 4.5 Multiple Storage Singletons Without Lock

`storage/client.py` -- Three lazy singletons (`_storage`, `_media_storage`, `_slide_storage`) without `asyncio.Lock()`. Potential race conditions.

---

### 4.6 Hardcoded Storage Bucket Logic

`storage/gcs.py:188-192`:
```python
if path.startswith("sessions/"):
    url = f"https://storage.googleapis.com/ii-agent-public/{path}"
```

Hardcoded bucket name and path-based routing.

---

### 4.7 Circular Dependency Risks in Config

- `core/config/settings.py:376-380` -- `storage_client` property lazy-imports from domain
- `core/config/settings.py:279-293` -- Validator uses lazy import for `LLMConfig`
- `core/config/__init__.py:39-41` -- Lazy imports to avoid circular dependencies

---

### 4.8 Minor Issues

- `utils/openai.py:8` -- `from ii_agent.v1.media import Image` (utility depends on V1)
- `utils/prompt_generator.py:4` -- `from ii_agent.agents.beta.llm.base import TextPrompt, TextResult, LLMClient` (tight coupling)
- `utils/error_handling.py:6` -- `from fastapi import WebSocket` (utils shouldn't depend on framework types)
- `cron/extend_sandbox_timeout.py:31` -- Lazy initialization of SandboxService (should use container)
- `app.py:165-183` -- Hardcoded middleware settings should be in `core/config/`
- `app.py:238` -- `max_http_buffer_size=10 * 1024 * 1024` magic number

---

## 5. Domain Health Summary

| Domain | Health | Key Issues |
|--------|--------|------------|
| **`core/`** | 9/10 | Business logic extracted from `db/manager.py` ✅; `agent_config.py` deleted ✅; minor lazy-import workarounds remain |
| **`auth/`** | 9/10 | Clean OAuth flow via `UserServiceDep` DI; no singleton imports; no raw SQL in router; HTML template extracted; duplicate logic eliminated |
| **`users/`** | 9/10 | Full service via DI (`UserServiceDep`); no singleton; repository with subscription/profile methods; router with profile endpoints |
| **`billing/`** | 9/10 | Subscription updates via `UserRepository`; consistent webhook error handling (log + return) |
| **`credits/`** | 9/10 | Class-based `CreditService` with DI (`CreditServiceDep`); no singleton; no explicit commits (caller manages tx); cross-domain imports lazy-loaded; thin compat shims for non-router callers |
| **`sessions/`** | 8/10 | `SessionValidationResult` + `validate_and_prepare_session()` added ✅; reverse dependency on agents fixed via `AgentRunService` ✅; backward relationships kept intentionally for cascade deletes; event filtering logic remains |
| **`chat/`** | 7/10 | Uses `AgentRunService` ✅; data access + message formatting moved from router to `ChatService.build_message_history_response()` ✅; still creates sessions directly |
| **`agents/`** | 9/10 | `AgentRunService` provides clean interface for socket/chat/sessions ✅; `ExecutionService` for task creation/milestones ✅; `PlanService` for plan-mode logic ✅ |
| **`projects/`** | 8/10 | Secrets decoupled from sandboxes ✅; `DeploymentOrchestrationService` for shared deployment logic ✅; deployment still modifies project state; JSON blobs remain |
| **`files/`** | 9/10 | `prepare_agent_files()` + `get_files_by_ids_and_update_session()` added ✅; file logic in connectors router still present |
| **`connectors/`** | 7/10 | Duplicate `load_connector_tools` removed ✅; file ops in router still present |
| **`socket/`** | 7/10 | Handlers refactored to thin transport layer ✅; business logic extracted to `ExecutionService`, `PlanService`, `DeploymentOrchestrationService`, `SessionService`, `FileService`, `SandboxService` ✅; handlers retain only agent creation, streaming, and event emission |
| **`subscribers/`** | 7/10 | Minor file processing logic in DatabaseSubscriber |
| **`storage/`** | 9/10 | Well-abstracted, minor hardcoded bucket paths |
| **`sandboxes/`** | 9/10 | Clean structure; `resolve_sandbox_for_session()` consolidates 4x duplicated lookup ✅; `SandboxEnvSyncService` for env file syncing ✅; base class still opens DB sessions |
| **`skills/`** | 7/10 | V1 dependencies, incomplete exports |
| **`slides/`** | 7/10 | ContentProcessor misplaced, sandbox coupling |
| **`storybook/`** | 7/10 | Credit deduction + generation status check moved to service ✅; `_generate_image` callback pattern acceptable |
| **`media/`** | 9/10 | Cache, media tools, and reference image logic moved to `MediaTemplateService` ✅; clean thin router |
| **`llm_settings/`** | 8/10 | Heavy `SessionService` dep replaced with lightweight `SessionRepository` injection ✅; still has cross-domain session import (acceptable) |
| **`mcp_settings/`** | 9/10 | Codex/Claude Code config + OAuth token exchange moved to `MCPSettingService` ✅; router is now a thin HTTP layer |
| **`mcp_sse/`** | 5/10 | Mixed concerns, in-memory OAuth state, cross-domain widgets |
| **`a2a/`** | 6/10 | Tight agent coupling, lazy DI |
| **`v1/`** | 6/10 | Mislabeled "legacy", parallel sandbox impl, used everywhere |
| **`tools/`** | 5/10 | All depend on V1 base classes |
| **`utils/`** | 7/10 | Minor V1 and framework dependencies |
| **`prompts/`** | 9/10 | Clean, no issues |
| **`wishlist/`** | 9/10 | Clean, well-structured |
| **`cron/`** | 8/10 | Minor DI improvement needed |
| **`vectorstore/`** | 6/10 | Backward-compat shim, should be removed |

---

## 6. Recommended Refactoring Priority

### Phase 1: Extract Socket Handler Logic (Highest Impact) ✅ COMPLETED

1. ~~Create `agents/execution_service.py` -- extract from `query_handler.py`~~ ✅ `ExecutionService` with `create_task_with_lock()`, `get_milestone_context()`, `update_milestones_after_run()`
2. ~~Create `agents/plan_service.py` -- extract from `plan_handler.py`~~ ✅ `PlanService` with `has_existing_plan()`, `get_plan_data()`, `save_and_emit_plan()`, `fail_task()`
3. ~~Create `projects/deployment_orchestration_service.py` -- extract from `publish_handler.py` and `cloud_run_publish_handler.py`~~ ✅ `DeploymentOrchestrationService` with project resolution, deployment context, status updates, utility methods
4. ~~Move session validation from `command_handler.py` to `sessions/service.py`~~ ✅ `SessionValidationResult` + `validate_and_prepare_session()`
5. ~~Consolidate sandbox lookup into `SandboxService.resolve_sandbox_for_session()`~~ ✅ Updated 4 handlers
6. ~~Extract file preparation from handlers into `files/service.py`~~ ✅ `prepare_agent_files()` + `get_files_by_ids_and_update_session()`

### Phase 2: Fix Auth/Users Domain Boundary ✅ COMPLETED

7. ~~Create `UserService.create_user()` with proper initialization~~
8. ~~Move user creation from `auth/router.py` to `users/service.py`~~
9. ~~Move profile endpoints (`/auth/me/language`, `/auth/me` DELETE) to `users/router.py`~~
10. ~~Create `UserService.create_api_key()`, `update_language()`, `delete_user()`~~

### Phase 3: Decouple User Model ✅ COMPLETED

11. ~~Inject User Repository in Billing service and add methods inside user repo~~

### Phase 4: Fix Cross-Domain Dependencies ✅ COMPLETED

15. ~~Create `AgentRunService` interface so chat/sessions don't import agent repos directly~~
16. ~~Remove backward relationships from Session model~~ — **KEPT**: backward relationships retained intentionally for ORM-level cascade deletes on session deletion
17. ~~Extract business logic from `core/db/manager.py` to domain initialization hooks~~ (`llm_settings/seeding.py`, `skills/seeding.py`)
18. ~~Delete `core/config/agent_config.py`~~ (was broken — referenced non-existent `agents.beta.llm.base`, and unused by any module)
19. ~~Remove duplicate `connectors/tools_loader.py`~~ (removed duplicate from `connectors/service.py`, kept canonical in `connectors/tools_loader.py`)
20. ~~Replace heavy `SessionService` dep in `llm_settings/service.py` with lightweight `SessionRepository` injection via DI~~

### Phase 5: Service Layer Cleanup — Partially Completed

21. ~~Move business logic from routers to services (mcp_settings, storybook, chat, media)~~ ✅
    - `mcp_settings`: Codex/Claude Code config, OAuth token exchange → `MCPSettingService.configure_codex()`, `configure_claude_code()`, `_exchange_code_for_tokens()`
    - `storybook`: Credit deduction → `StorybookService.generate_voiceover_and_deduct_credits()`; generation status → `get_generation_status()`
    - `chat`: `_fetch_file_attachments_for_messages()` + `_build_message_history_response()` → `ChatService.build_message_history_response()` + `_fetch_file_attachments()`
    - `media`: Cache management, media tools, reference image generation → `MediaTemplateService.list_media_tools()`, `get_media_tool()`, `generate_reference_image()`
22. ~~Decouple `projects/secrets/service.py` from sandboxes~~ ✅ — `SecretService` is now DB-only; sandbox env syncing extracted to `sandboxes/env_sync_service.py` (`SandboxEnvSyncService`)
23. Create modern base class for tools (remove V1 dependency)
24. Extract MCP SSE widget orchestration into separate service
25. Use Redis for MCP SSE OAuth state management

### Phase 6: Housekeeping

26. Remove `vectorstore/` backward-compat shim
27. Complete domain `__init__.py` exports (skills, files)
28. Remove empty placeholder files
29. Document V1's actual role (not legacy -- active agent execution framework)
30. Parameterize hardcoded storage bucket paths
31. Add `asyncio.Lock()` to storage singleton initialization
