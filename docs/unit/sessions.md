# Unit Test Plan: `sessions`

## Scope

- session lifecycle and metadata updates (`sessions/service.py`)
- forking logic (`sessions/fork_service.py`)
- pre-execution validation (`sessions/validation_service.py`)

## Priority test suites

1. CRUD and lifecycle behavior.
- create/get session roundtrip with expected defaults
- soft delete and bulk soft delete semantics
- public/private visibility toggle behavior

2. Session metadata and plan handling.
- `update_session_plan()` normalizes missing details/dependencies
- plan event creation vs existing-event update path

3. Event retrieval enrichment.
- ignored event types are filtered out
- tool-result file URLs are replaced with signed URLs

4. Forking behavior.
- parent ownership validation
- invalid fork-type source raises `SessionValidationError`
- sandbox share mode reuses parent sandbox ID when available
- inherited `llm_setting_id` behavior

5. Validation service behavior.
- missing session returns typed invalid result
- LLM config resolution for user/system source
- credit check bypass for user-provided model keys

## Fixtures / mocks

- fake session/event/sandbox repositories
- fake credit and llm-setting services
- frozen timestamps for update assertions

## Proposed test layout

- `src/tests/unit/sessions/test_session_service.py`
- `src/tests/unit/sessions/test_session_plan_updates.py`
- `src/tests/unit/sessions/test_fork_service.py`
- `src/tests/unit/sessions/test_validation_service.py`

## Exit criteria

- session ownership and fork safety invariants covered
- plan metadata update flow protected against regressions
