# Unit Test Plan: `celery`

## Scope

- Celery app config and broker URL resolution
- task context decorator behavior
- async bridge helpers (`celery/utils.py`)
- pure task helper functions in `celery/tasks.py`

## Priority test suites

1. Broker/backend URL resolution.
- explicit env values take priority
- fallback maps Redis DB index correctly
- final default is stable

2. Decorator context propagation.
- `with_task_context` attaches request/session/user/run IDs
- missing headers do not crash the task wrapper

3. Task utility wrappers.
- `queue_task()` passes routing/countdown/expires/headers correctly
- `get_task_status()` returns expected schema for ready/progress/error
- `revoke_task()` emits expected response payload

4. Task-loop helpers.
- `_get_celery_loop()` reuses loop in-process
- page mapping helpers produce expected numbers across modes
- credit estimation helper math is deterministic

5. Worker container singleton.
- `get_celery_container()` memoizes one `ServiceContainer` per process

## Fixtures / mocks

- fake Celery `AsyncResult`
- fake `Task.request` object with headers
- monkeypatched environment and `get_settings()`

## Proposed test layout

- `src/tests/unit/celery/test_app_config.py`
- `src/tests/unit/celery/test_decorators.py`
- `src/tests/unit/celery/test_utils.py`
- `src/tests/unit/celery/test_task_helpers.py`
- `src/tests/unit/celery/test_manager_singleton.py`

## Exit criteria

- no hidden event-loop leaks
- queueing/status helpers stable for API consumers
