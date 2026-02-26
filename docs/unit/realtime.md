# Unit Test Plan: `realtime`

## Scope

- event persistence service
- Socket.IO connection/session flow (`realtime/socket/socketio.py`)
- command handler registry (`realtime/socket/command/handler_factory.py`)
- subscribers (database/socket/metrics)

## Priority test suites

1. Event service behavior.
- timestamp normalization with and without event timestamp
- save path delegates repository with UTC timestamp

2. Socket connection/auth flow.
- connect rejects missing/invalid tokens
- connect stores user/session identity in socket session
- join validates UUID format and ownership checks

3. Chat message dispatch.
- unknown command type emits structured error
- handler exceptions emit failure event without crashing server

4. Handler factory initialization.
- all expected command types are registered
- query handler reuse in dependent handlers (start-fork)

5. Database subscriber filters and transforms.
- ignores skipped event types (deltas, plan-generated, user-message)
- transforms `file_url` tool result into persisted file metadata
- handles duplicate event writes (`IntegrityError`) gracefully

## Fixtures / mocks

- fake `socketio.AsyncServer` with call recorder
- fake service container and command handlers
- fake event stream and subscriber dependencies

## Proposed test layout

- `src/tests/unit/realtime/test_event_service.py`
- `src/tests/unit/realtime/test_socketio_manager.py`
- `src/tests/unit/realtime/test_handler_factory.py`
- `src/tests/unit/realtime/test_database_subscriber.py`

## Exit criteria

- realtime command routing and event persistence are predictable
- auth and access checks are covered for socket paths
