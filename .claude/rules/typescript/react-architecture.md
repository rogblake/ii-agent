# React Architecture Rules

## Singleton Hooks via Context

**Hooks with internal refs or mutable state MUST be singleton via context — never instantiated in multiple components.**

If a hook maintains refs (`useRef`) that track state across renders (streaming IDs, agent stacks, tracking maps), creating multiple instances causes state divergence. These hooks must be wrapped in a context provider and consumed via a context hook.

```typescript
// BAD — multiple independent instances with divergent refs
function ComponentA() {
    const { handleEvent } = useAppEvents()  // Instance 1 with its own refs
}
function ComponentB() {
    const { handleEvent } = useAppEvents()  // Instance 2 with different refs
}

// GOOD — single instance shared via context
function RootLayout() {
    return (
        <AppEventsProvider>  {/* Single useAppEvents() instance */}
            <ComponentA />   {/* Uses useAppEventsContext() */}
            <ComponentB />   {/* Same instance, same refs */}
        </AppEventsProvider>
    )
}
```

### Singleton Hooks in This Project

| Hook | Provider | Consumer |
|------|----------|----------|
| `useAppEvents` | `AppEventsProvider` | `useAppEventsContext()` |
| Socket.IO | `SocketIOProvider` | `useSocketIOContext()` |
| Chat | `ChatProvider` | `useChat()` |
| Design Mode | `DesignModeProvider` | `useDesignModeContext()` |

### When to Create a Provider

Create a context provider when a hook:
- Maintains `useRef` state that must be shared (streaming maps, agent tracking)
- Is used in 2+ components that need to see the same state
- Manages a connection or subscription (WebSocket, event bus)

Do NOT create a provider for:
- Hooks that only read Redux state (use `useAppSelector` directly)
- Hooks with no mutable refs (pure computation hooks)
- Hooks used in exactly one component

## Async in useCallback / useEffect

**Always `await` async functions inside `useCallback`.** Fire-and-forget async calls cause race conditions where cleanup runs before the async work completes.

```typescript
// BAD — finally block runs immediately, before events finish processing
const fetchData = useCallback(async () => {
    try {
        const data = await fetchEvents()
        const processAsync = async () => { /* long work */ }
        processAsync()  // NOT awaited — finally runs too early
    } finally {
        setIsLoading(false)  // Runs before processAsync completes
    }
}, [])

// GOOD — properly awaited
const fetchData = useCallback(async () => {
    try {
        const data = await fetchEvents()
        await processEvents(data)  // Awaited — finally waits for completion
    } finally {
        setIsLoading(false)
    }
}, [])
```

## Component Provider Hierarchy

The app's provider tree must follow this order (outermost first):

```
AppEventsProvider          (singleton event handler)
  WebSocketProvider        (socket connection, uses handleEvent from context)
    ChatProvider           (chat state management)
      RouterOutlet         (page components)
```

Changing this order breaks event handling. WebSocketProvider depends on AppEventsProvider for the `handleEvent` callback.

## Prop Drilling vs Context

- **Use context** for: cross-cutting concerns (events, auth, socket, theme)
- **Use props** for: component-specific data and callbacks
- **Use Redux** for: shared application state (messages, UI state, agent state)
- **Never** pass Redux dispatch as a prop — components should dispatch directly

## Event Handler Refs

When passing callbacks to providers or long-lived listeners:

```typescript
// GOOD — ref stays current without re-registering listeners
const handleEventRef = useRef(handleEvent)
handleEventRef.current = handleEvent

socket.on('chat_event', (data) => {
    handleEventRef.current(data)  // Always calls latest handler
})

// BAD — re-registers listener on every render
useEffect(() => {
    socket.on('chat_event', handleEvent)
    return () => socket.off('chat_event', handleEvent)
}, [handleEvent])  // Fires on every re-render if handleEvent changes
```
