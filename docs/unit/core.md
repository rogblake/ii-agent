# Unit Test Plan: `core`

## Scope

- Configuration composition and validation (`core/config/*`)
- Database session management (`core/db/*`)
- Redis cancellation/locking/cache adapters (`core/redis/*`)
- Storage factory/client abstractions (`core/storage/*`)
- Cross-cutting middleware and request context

## Priority test suites

1. `Settings` source precedence and defaults.
- `env` overrides `dotenv`
- `USE_GCP_SECRETS` toggles source list behavior
- invalid enum/port values fail validation

2. DB session manager semantics.
- `get_db()` rolls back on SQLAlchemy errors
- `get_db_session_local()` commits on success, rolls back on failure

3. Run cancellation managers.
- memory manager register/cancel/cleanup lifecycle
- redis manager key namespacing and TTL behavior
- `raise_if_cancelled()` throws `RunCancelledException`

4. Storage factory and provider errors.
- known provider returns proper client
- unknown provider raises deterministic `ValueError`

5. Middleware behavior.
- request tracing injects request identifiers
- `IIAgentError` maps to expected response contract
- exception middleware preserves structured logging context

## Fixtures / mocks

- `FakeAsyncSession` with commit/rollback counters
- `FakeRedis` for `setex/get/delete/keys`
- `monkeypatch` for environment variables and singleton settings cache

## Proposed test layout

- `src/tests/unit/core/test_settings.py`
- `src/tests/unit/core/test_db_manager.py`
- `src/tests/unit/core/test_redis_cancel.py`
- `src/tests/unit/core/test_storage_factory.py`
- `src/tests/unit/core/test_middleware.py`

## Exit criteria

- Critical startup paths and failure paths covered
- No network dependency in unit suite
- Deterministic behavior for config and cancellation logic
