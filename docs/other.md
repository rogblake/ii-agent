# Other Production Test Plans

## Purpose

Cover high-value non-unit, non-smoke test categories needed for production hardening.

## 1. Contract tests

- verify FastAPI response schemas for key routers (`auth`, `sessions`, `chat`, `files`, `billing`)
- validate websocket event envelopes (`type`, `content`, `run_id`, `session_id`)
- snapshot key API contracts to detect breaking changes

## 2. Regression tests

- every resolved incident gets a focused reproduction test
- pin known edge cases (credit arithmetic, webhook duplication, cancellation races)
- maintain a small always-on regression pack in CI

## 3. Resilience / fault-injection tests

- Redis unavailable -> verify graceful fallback/error handling paths
- storage signed-url failures -> fallback URL behavior
- sandbox reconnect/init failures -> retry/fallback behavior
- DB lock/contention paths in task creation

## 4. Security tests

- auth bypass checks on session/file/project ownership
- webhook signature validation negative tests
- secrets redaction checks in logs/output formatting
- input validation fuzzing for IDs and route params

## 5. Performance baseline tests

- chat turn orchestration latency budget under mocked model/provider
- websocket fanout throughput baseline
- batch signed URL generation throughput and fallback behavior
- scheduler cleanup processing bounds (batch and max limits)

## 6. Migration and data-compatibility tests

- alembic upgrade on representative production-like snapshot
- backward compatibility for metadata fields (`style_json`, session metadata, billing metadata)
- rollback viability for latest migration set (where supported)

## 7. Observability tests

- logs include request/run/session correlation IDs
- critical failures emit structured logs with actionable context
- metrics subscriber accepts and processes key event classes

## Execution cadence

- contract + regression: every PR
- resilience + security: nightly
- performance + migration compatibility: pre-release and weekly scheduled
