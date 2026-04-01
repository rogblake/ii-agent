# Query Handler Refactoring Design

**Date:** 2026-03-29
**Branch:** refactor/support-application-features-options
**Status:** Approved

## Goal

Extract domain logic from `realtime/handlers/query.py` into proper domain services following DDD and SOLID principles. The handler should become pure orchestration with zero business logic.

## Changes

### 1. New `plans/` Domain

**Location:** `src/ii_agent/plans/`

```
src/ii_agent/plans/
├── __init__.py       # Exports: PlanService, MilestoneStatus
├── types.py          # MilestoneStatus(StrEnum)
├── service.py        # PlanService
├── schemas.py        # PlanContext, MilestoneInfo (Pydantic)
└── exceptions.py     # MilestoneNotFoundError
```

**PlanService public API:**

- `get_milestone_context(plan_context: dict[str, Any], milestone_ids: list[str]) -> str | None` — generates AI prompt context for milestone execution
- `update_milestones_after_run(db, session_id, milestone_ids, status) -> None` — updates milestone statuses based on run outcome, publishes events
- `reset_milestones_to_pending(db, session_id, milestone_ids) -> None` — resets milestones on error

**Storage:** Milestones remain in `session.session_metadata["plan"]` (no schema migration). PlanService reads/writes via SessionService + direct session access.

**Dependencies:** `SessionService`, `EventRepository`, `AsyncIOPubSub`

### 2. Move `agents/media/` to `files/media/`

**From:** `src/ii_agent/agents/media/` (Image, File, Video, Audio)
**To:** `src/ii_agent/files/media/`

- Move `media.py` and update `__init__.py`
- Delete `src/ii_agent/agents/media/` entirely
- Update ALL imports across codebase: `from ii_agent.files.media import Image, File, Video, Audio`
- No backward compatibility shims
- Update `files/__init__.py` to re-export media types

### 3. Update FileService

- Update `prepare_agent_files()` to return `tuple[list[Image], list[File]]` instead of `tuple[list[dict], list[dict]]`
- This eliminates the dict-to-model conversion in the handler

### 4. Refactored `query.py`

Handler becomes pure orchestration:

1. Validate session + credits (existing base handler method)
2. Claim task (existing run_task_service)
3. Get milestone context via `plan_service.get_milestone_context()`
4. Create agent via `agent_factory`
5. Prepare files via `file_service.prepare_agent_files()`
6. Upload to sandbox (existing sandbox utility)
7. Run agent + stream events
8. Update milestones via `plan_service.update_milestones_after_run()`
9. On error: `plan_service.reset_milestones_to_pending()`

**Deleted from handler:** `_handle_file_upload()`, `_get_milestone_context()`, `_update_milestones_after_run()`, `_update_milestones_status()`

### 5. Container Wiring

```python
# core/container.py
self.plan_service = PlanService(
    session_service=session_svc,
    event_repo=event_repo,
    pubsub=pubsub,
)
```

## Testing Strategy

- TDD: Write tests first for PlanService, then implement
- Unit tests for PlanService (mock SessionService, EventRepository)
- Unit tests for updated FileService.prepare_agent_files()
- Verify all moved imports compile correctly
- Existing handler tests should still pass after refactoring

## Files Created

- `src/ii_agent/plans/__init__.py`
- `src/ii_agent/plans/types.py`
- `src/ii_agent/plans/service.py`
- `src/ii_agent/plans/schemas.py`
- `src/ii_agent/plans/exceptions.py`
- `src/ii_agent/files/media/__init__.py`
- `src/ii_agent/files/media/media.py`
- `tests/unit/plans/test_service.py`
- `tests/unit/files/test_prepare_agent_files.py`

## Files Modified

- `src/ii_agent/realtime/handlers/query.py` — remove domain logic, delegate to services
- `src/ii_agent/files/__init__.py` — re-export media types
- `src/ii_agent/files/service.py` — update prepare_agent_files return type
- `src/ii_agent/core/container.py` — wire PlanService
- All files importing from `ii_agent.agents.media` — update to `ii_agent.files.media`

## Files Deleted

- `src/ii_agent/agents/media/media.py`
- `src/ii_agent/agents/media/__init__.py`
