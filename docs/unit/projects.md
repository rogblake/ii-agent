# Unit Test Plan: `projects`

## Scope

- project CRUD service (`projects/service.py`)
- deployment orchestration helpers (`projects/deployment_orchestration_service.py`)
- deployment context and output parsing utilities

## Priority test suites

1. Project service CRUD behavior.
- missing session during create returns `None` with warning path
- access-controlled getters raise/return as expected
- production URL and secrets updates persist correctly

2. Deployment path/name resolution.
- relative/absolute path normalization
- project-name sanitization and Cloud Run constraints
- service-name generation includes deterministic hash suffix

3. Deployment context creation.
- creates deployment record when project exists
- tolerates DB failure without crashing caller
- provider-specific naming (`vercel` vs `cloud_run`)

4. Deployment status/finalization.
- no-op when `deployment_id` absent
- successful finalize updates deployment + active deployment + project URL

5. Output utilities.
- success marker append/detection/cleanup
- token redaction patterns (`--token`, `VERCEL_TOKEN`)
- deployment URL extraction precedence

## Fixtures / mocks

- fake `ProjectService` / `DeploymentsService`
- monkeypatched `get_db_session_local()` async context
- deterministic session UUID fixtures

## Proposed test layout

- `src/tests/unit/projects/test_project_service.py`
- `src/tests/unit/projects/test_deployment_orchestration.py`
- `src/tests/unit/projects/test_output_parsing.py`

## Exit criteria

- deployment utility behavior is deterministic and safe for logs
- project update semantics are covered for success/failure paths
