# God Service Split Design

## Problem

Four services exceed 700+ lines and violate the Single Responsibility Principle:

| Service | Lines | Concerns Mixed |
|---------|-------|---------------|
| `ChatService` | ~1200 | sessions, streaming, tools, files, credits, LLM config |
| `StorybookService` | ~850 | CRUD, versioning, voice-over, PDF/PNG export, progress |
| `SessionService` | ~700 | CRUD, state, forking, validation, events, plans |
| `BillingService` | ~700 | checkout, webhooks, subscriptions, credits |

## ChatService Split (~1200 → 5 focused services)

### Current Structure

```
ChatService.__init__(
    message_service, chat_repo, config, user_service,
    llm_setting_service, agent_run_service, session_repo,
    file_repo, connector_repo
)
```

9 dependencies — a strong signal of SRP violation.

### Proposed Structure

```
chat/
├── service.py              # ChatService (orchestrator, ~200 lines)
├── llm_loop_service.py     # LLMTurnLoopService (~250 lines)
├── tool_service.py         # ChatToolService (~200 lines)
├── file_processing.py      # ChatFileProcessor (~150 lines)
├── message_history.py      # ChatMessageHistoryService (~100 lines)
```

### Service Responsibilities

#### ChatService (orchestrator) — `service.py`
- `create_chat_session()` — session creation
- `stream_chat_response()` — thin orchestration only (delegates to sub-services)
- `stop_conversation()` — cancellation
- `clear_messages()` — message cleanup

Dependencies: `ChatFileProcessor`, `ChatToolService`, `LLMTurnLoopService`, `ChatMessageHistoryService`, `session_repo`, `agent_run_service`

#### LLMTurnLoopService — `llm_loop_service.py`
- `run()` — main LLM execution loop with tool calling
- `_get_conversation_history()` — recent history retrieval
- `_deduct_credits_for_llm_usage()` — per-turn credit deduction

Dependencies: `message_service`, `config`, `llm_setting_service`

#### ChatToolService — `tool_service.py`
- `build_tool_registry()` — builds tool registry + OpenAI-format definitions
- `load_connector_tools()` — loads connector-based tools dynamically
- `execute_tool()` — executes a single tool call

Dependencies: `user_service`, `connector_repo`, `config`

#### ChatFileProcessor — `file_processing.py`
- `process_uploads()` — processes file uploads, mutates message parts
- Vector store integration (OpenAI)

Dependencies: `file_repo`, `config`

#### ChatMessageHistoryService — `message_history.py`
- `get_message_history()` — paginated history
- `build_message_history_response()` — API response with file attachments
- `_fetch_file_attachments()` — file attachment resolution

Dependencies: `chat_repo`, `file_repo`

### Composition

```python
# chat/service.py — thin orchestrator
class ChatService:
    def __init__(
        self,
        *,
        file_processor: ChatFileProcessor,
        tool_service: ChatToolService,
        llm_loop: LLMTurnLoopService,
        message_history: ChatMessageHistoryService,
        session_repo: SessionRepository,
        agent_run_service: AgentRunService,
    ): ...

    async def stream_chat_response(self, db, user, session, query, ...):
        # Step 1: files
        vector_store = await self._file_processor.process_uploads(db, ...)
        # Step 2: tools
        tools, tool_defs = await self._tool_service.build_registry(db, ...)
        # Step 3: LLM loop
        async for event in self._llm_loop.run(db, messages, tools, ...):
            yield event
```

---

## SessionService Split (~700 → 3 services)

### Current Structure

```
SessionService.__init__(
    session_repo, event_repo, agent_run_service,
    file_store, sandbox_repo, config
)
```

### Proposed Structure

```
sessions/
├── service.py              # SessionService (CRUD + queries, ~300 lines)
├── fork_service.py         # SessionForkService (~120 lines)
├── validation_service.py   # SessionValidationService (~150 lines)
```

### Service Responsibilities

#### SessionService (CRUD) — `service.py`
- `create_session()`, `get_session_by_id()`, `get_session_details()`
- `get_user_sessions()`, `soft_delete_session()`, `bulk_soft_delete_sessions()`
- `update_*()` field methods
- `get_or_create_session()`, `ensure_session_exists()`
- `set_session_public()`
- `get_sessions_with_running_status()`
- `get_session_events_with_details()`, `update_session_plan()`
- `_build_session_info()`, `_session_to_dict()` helpers

Dependencies: `session_repo`, `event_repo`, `agent_run_service`, `file_store`

#### SessionForkService — `fork_service.py`
- `fork_session()` — validates parent, resolves sandbox sharing, inherits LLM settings, creates child

Dependencies: `session_repo`, `sandbox_repo`, `config`

#### SessionValidationService — `validation_service.py`
- `validate_and_prepare_session()` — validates session, resolves LLM config, checks credits
- `SessionValidationResult` dataclass

Dependencies: `session_repo`, `llm_setting_service`, `credit_service`, `config`

---

## BillingService Split (~700 → 2 services + shared config)

### Proposed Structure

```
billing/
├── service.py              # BillingService (checkout + portal, ~200 lines)
├── webhook_handler.py      # StripeWebhookHandler (~450 lines)
├── stripe_config.py        # StripeConfig (shared utilities, ~80 lines)
```

### Service Responsibilities

#### StripeConfig — `stripe_config.py`
- `ensure_api_key()` — validates Stripe key
- `get_price_id(plan, cycle)` — plan → Stripe price mapping
- `plan_cycle_from_price(price_id)` — reverse mapping
- `plan_credits(plan)` — credits per plan
- `resolve_return_urls()` — success/cancel URL resolution
- `to_datetime()`, `as_dict()` static helpers

Dependencies: `config`

#### BillingService — `service.py`
- `create_checkout_session()` — user-initiated checkout
- `create_portal_session()` — billing portal access

Dependencies: `stripe_config`, `user_repo`

#### StripeWebhookHandler — `webhook_handler.py`
- `construct_webhook_event()` — payload verification
- `handle_webhook_event()` — dispatcher
- `_handle_checkout_session_completed()`
- `_handle_invoice_payment_succeeded()`
- `_handle_subscription_deleted()`
- `_handle_subscription_updated()`
- `_resolve_subscription_context()` — shared by all handlers
- `_record_transaction()` — shared by all handlers

Dependencies: `stripe_config`, `billing_repo`, `user_repo`

---

## StorybookService Split (~850 → 4 services)

### Proposed Structure

```
content/storybook/
├── service.py              # StorybookService (CRUD + queries, ~250 lines)
├── version_service.py      # StorybookVersionService (~200 lines)
├── export_service.py       # StorybookExportService (~150 lines)
├── voice_service.py        # StorybookVoiceService (~200 lines)
```

### Service Responsibilities

#### StorybookService (CRUD) — `service.py`
- `create_storybook()`, `create_storybook_page()`
- `get_session_storybooks()`, `get_storybook_detail()`
- `create_storybook_with_info()`, `create_page_with_html()`
- Serialization helpers (`_page_to_info`, `_storybook_to_info`, `_storybook_to_detail`)

Dependencies: `repo`, `config`

#### StorybookVersionService — `version_service.py`
- `create_storybook_version()` — clones pages into new version
- `update_page_text()` — updates text + creates new version
- `regenerate_page_image()` — regenerates image + creates new version

Dependencies: `repo`, `storybook_service` (for `get_storybook_detail`), `config`

#### StorybookExportService — `export_service.py`
- `download_storybook_as_pdf()` / `_with_progress()`
- `download_storybook_page_as_pdf()`
- `download_storybook_as_png_zip()` / `_with_progress()`
- `download_storybook_page_as_png()`
- Owns `_pdf_exporter` and `_png_exporter` instances

Dependencies: `storybook_service` (for `get_storybook_detail`), `config`

#### StorybookVoiceService — `voice_service.py`
- `generate_voiceover()` — voice generation for pages
- `generate_voiceover_and_deduct_credits()` — voice + billing
- `get_generation_status()`, `cancel_generation()`
- `_get_voice_service()`, `_generate_voice_audio()`
- `_extract_plain_text()`, `_resolve_language_code()`

Dependencies: `repo`, `storybook_service` (for queries), `config`

---

## Container & DI Wiring

`ServiceContainer.create()` in `container.py` wires sub-services into parent services:

```python
# In container.py create():
chat_file_processor = ChatFileProcessor(file_repo=file_repo, config=cfg)
chat_tool_svc = ChatToolService(user_service=user_svc, connector_repo=connector_repo, config=cfg)
chat_msg_history = ChatMessageHistoryService(chat_repo=chat_repo, file_repo=file_repo)
llm_loop_svc = LLMTurnLoopService(message_service=msg_svc, config=cfg, llm_setting_service=llm_setting_svc)
chat_svc = ChatService(
    file_processor=chat_file_processor,
    tool_service=chat_tool_svc,
    llm_loop=llm_loop_svc,
    message_history=chat_msg_history,
    session_repo=session_repo,
    agent_run_service=agent_run_svc,
)
```

Similarly, `dependencies.py` files compose via `Depends()` chains.

---

## Migration Strategy

1. Extract one service at a time (start with the most isolated: `ChatFileProcessor`)
2. Keep the old method signatures as thin wrappers during migration
3. Update `dependencies.py` and `container.py` to wire new sub-services
4. Remove wrappers once all callers are updated
5. Repeat for each extraction

## Summary

| Service | Before | After | Max Size |
|---------|--------|-------|----------|
| `ChatService` | 1200 lines, 9 deps | 5 services | ~250 lines each |
| `SessionService` | 700 lines | 3 services | ~300 lines each |
| `BillingService` | 700 lines | 2 services + config util | ~450 lines max |
| `StorybookService` | 850 lines | 4 services | ~250 lines each |
