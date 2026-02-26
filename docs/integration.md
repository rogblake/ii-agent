# Integration Test Plan (`src/ii_agent`)

## Objective

Validate cross-module behavior for production-critical flows where multiple services, persistence layers, and transport channels interact.

## Recommended integration environment

- `pytest` + `pytest-asyncio`
- ephemeral PostgreSQL schema per test run
- isolated Redis database per test run
- fake or local object storage adapter for signed URL flows
- external APIs mocked at boundary (Stripe, GitHub, MCP upstream, cloud providers)

## Core integration scenarios

1. Auth -> Session -> Chat run flow.
- create/resolve user
- create session
- stream one chat turn
- assert message + event persistence

2. Session validation + credits gate.
- insufficient credits blocks run for system models
- user-provided model key bypasses credit check path

3. File upload lifecycle.
- generate upload URL
- complete upload
- retrieve file stream with ownership checks
- batch signed URLs include missing-path reporting

4. Billing lifecycle.
- checkout session creation
- webhook `checkout.session.completed` updates subscription fields
- webhook idempotency on repeated event ID
- cancellation webhook resets plan/credits

5. Storybook async generation flow.
- task accepted event
- progress updates persisted
- completion emits final tool-result payload with pages

6. Realtime socket flow.
- websocket connect/join
- query command dispatch
- event fanout to socket + database subscriber
- cancel command propagates to run-cancellation manager

7. Settings resolution flow.
- create user LLM setting with encrypted key
- bind session to setting
- run uses user config; fallback to system config if deleted

8. Project deployment orchestration flow.
- resolve project path/name
- create deployment context
- finalize success updates deployment + project URL

9. A2A session bootstrap flow.
- process request with missing user
- service-user auto-creation and fallback email rules
- sandbox reuse fallback on provider reconnect failure

10. Scheduler maintenance flow.
- stale run cleanup marks tasks interrupted
- related interruption event persisted

## Data and isolation strategy

- per-test transaction or per-test schema reset
- deterministic clocks for subscription/refresh logic
- no shared global singleton state across test modules (patch or reset caches)

## CI gating recommendation

- run full integration suite on merge to main
- run critical subset (1, 3, 4, 6, 7) on pull requests
- publish flaky-test quarantine report; do not silently ignore failures

## Exit criteria

- all critical scenarios pass with deterministic outcomes
- no network calls escape mocked boundaries
- event/message/subscription state transitions are verified end-to-end
