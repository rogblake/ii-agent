# TypeScript Strict Typing Rules

## No `any` in Application Code

Use `unknown` for untrusted data, then narrow safely. Use generics when type depends on caller.

```typescript
// BAD
function handle(data: any) { return data.name }

// GOOD
function handle(data: unknown): string {
    if (typeof data === 'object' && data !== null && 'name' in data) {
        return String((data as { name: unknown }).name)
    }
    throw new Error('Invalid data')
}
```

## Type Narrowing Over Type Assertions

Prefer runtime checks over `as` casts. Use `as` only when you have external guarantees (e.g., Zod-validated data).

```typescript
// BAD — unsafe cast, no runtime check
const text = data.content.text as string

// ACCEPTABLE — when data shape is validated at boundary (socket schema, API response)
const text = data.content.text as string  // OK if content is validated by Pydantic on BE

// BEST — runtime check
const text = typeof data.content.text === 'string' ? data.content.text : ''
```

## Enum Values Must Match BE Exactly

FE `AgentEvent` enum values must be identical to BE `EventType` string values. A mismatch means the event silently falls through the switch statement.

```typescript
// FE enum — values must match BE EventType exactly
export enum AgentEvent {
    AGENT_RESPONSE = 'agent_response',      // Must match BE EventType.AGENT_RESPONSE
    TOOL_CALL = 'tool_call',                // Must match BE EventType.TOOL_CALL
}
```

When adding a new event:
1. Check `realtime/events/app_events.py` for the `EventType` value
2. Add matching enum member to `AgentEvent` in `frontend/src/typings/agent.ts`
3. Add case to `handleEvent` switch in `use-app-events.tsx`

## Interface vs Type

```typescript
// Use interface for object shapes (extendable)
interface IEvent {
    id: string
    type: AgentEvent
    content: Record<string, unknown>
}

// Use type for unions, intersections, utility types
type EventHandler = (event: IEvent) => void
type RunState = 'running' | 'completed' | 'failed' | 'cancelled'
```

## Discriminated Unions for Event Content

When event content has a known structure per event type, define typed content interfaces:

```typescript
// Prefer typed content when the shape is known
interface ToolCallContent {
    tool_name: string
    tool_call_id: string
    tool_input: Record<string, unknown>
    tool_display_name?: string
}

interface AgentResponseContent {
    text: string
}

// Use Record<string, unknown> only for truly dynamic content
```

## No `console.log` in Production Code

Use proper error boundaries and logging. `console.error` is acceptable for caught errors in development.

```typescript
// BAD
console.log('Socket connected:', socket.id)

// ACCEPTABLE (development-only, remove before merge)
if (import.meta.env.DEV) {
    console.log('Socket connected:', socket.id)
}
```
