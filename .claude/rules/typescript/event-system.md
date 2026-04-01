# Event System Contract (FE/BE Alignment)

This project has a real-time event system where BE emits events via Socket.IO and FE dispatches on them. The contract between BE and FE is critical and must stay in sync.

## Event Type Flow

```
BE BaseEvent.name (dotted)  ->  to_socket_payload() = model_dump()
     "agent.response"              { name: "agent.response", ... }
                                           |
                                 FE dispatches on data.name
                                AgentEvent.AGENT_RESPONSE = "agent.response"
```

There is **no mapping layer** and **no `type` field**. The dotted `name` on every `BaseEvent` subclass IS the dispatch key the FE receives via `data.name`. `EventType` enum values are the same dotted strings.

### Key Files

| Layer | File | Purpose |
|-------|------|---------|
| BE event definitions | `realtime/events/app_events.py` | `BaseEvent` subclasses, `EventType` enum (dotted values) |
| BE converter | `agents/factory/converter.py` | `convert_agent_event_to_realtime()` — runtime events to BaseEvent |
| BE socket emission | `realtime/pubsub/` | Calls `event.to_socket_payload()` which is just `model_dump()` |
| BE event replay | `sessions/router.py` | `_build_event_info()` passes stored dotted name as `name` directly |
| FE type definitions | `frontend/src/typings/agent.ts` | `AgentEvent` enum — values are dotted names matching BE `BaseEvent.name` |
| FE event handler | `frontend/src/hooks/use-app-events.tsx` | `handleEvent()` switch on `data.name: AgentEvent` |
| FE socket listener | `frontend/src/contexts/websocket-context.tsx` | Receives `chat_event` and delegates to `handleEvent` |
| FE session replay | `frontend/src/hooks/use-session-manager.tsx` | Replays stored events through same `handleEvent` |

### Rules

1. **Never add a BE event without adding its FE enum member.** When adding a new `BaseEvent` subclass in `app_events.py`:
   - Add the corresponding `EventType` enum value (must equal the `name` string)
   - Add the matching `AgentEvent` enum member in `frontend/src/typings/agent.ts` with the same dotted value
   - Add a `case` in `use-app-events.tsx` `handleEvent` switch

2. **FE dispatches on `data.name` which is the dotted name (e.g. `"agent.response"`).** There is no `type` field — `name` IS the dispatch key.

3. **Event replay must use the same `handleEvent` path as live events.** Both Socket.IO `chat_event` and session replay in `useSessionManager` call the same `handleEvent` function from the single `AppEventsProvider` context.

4. **`run_status` is the authoritative run state.** Both live events and replay reconcile final state from `run_status`. FE derives `isCompleted`, `isStopped`, `isWaitingForInput` from `runStatus` via Redux selectors — never set these independently.

5. **Test coverage.** `test_v1_factory_converter.py::TestEventTypeMatchesName` verifies `EventType` enum values match the expected dotted names and that `to_socket_payload()` uses `name` (no `type`).
