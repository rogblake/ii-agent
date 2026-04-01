# Redux Patterns (Strict)

## Never Use Magic String Dispatches

**NEVER dispatch actions using raw string types.** RTK generates namespaced action types (e.g., `ui/setLoading`), so `dispatch({ type: 'SET_LOADING', payload: true })` is a **silent no-op** — no reducer matches it.

```typescript
// BAD — silent no-op, no reducer handles this action type
dispatch({ type: 'SET_LOADING', payload: true })
dispatch({ type: 'SET_COMPLETED', payload: false })
dispatch({ type: 'ADD_UPLOADED_FILES', payload: paths })
dispatch({ type: 'SET_CURRENT_QUESTION', payload: value })

// GOOD — use exported action creators from slices
import { setLoading } from '@/state/slice/ui'
import { setCurrentQuestion } from '@/state/slice/workspace'

dispatch(setLoading(true))
dispatch(setCurrentQuestion(value))
```

### How to Find the Right Action Creator

1. Identify which slice owns the state you want to update
2. Import the action creator from that slice (or from `@/state` barrel export)
3. Use it with `dispatch(actionCreator(payload))`

### Slice Ownership

| State | Slice | Key Actions |
|-------|-------|-------------|
| Loading / UI state | `ui` | `setLoading`, `setActiveTab`, `setBuildMode`, `setPlanData`, `updateMilestoneStatus` |
| Messages | `messages` | `addMessage`, `updateMessage`, `setMessages`, `setEditingMessage` |
| Agent state | `agent` | `setRunStatus`, `setCancelling`, `setAgentInitialized`, `setProjectId` |
| Files | `files` | `setIsUploading`, `addUploadedFiles`, `setRequireClearFiles` |
| Workspace | `workspace` | `setCurrentQuestion`, `setWorkspaceInfo`, `setBrowserUrl` |
| Settings | `settings` | `setSelectedModel`, `setToolSettings` |
| Sessions | `sessions` | `setActiveSessionId`, `fetchSessions` |

## Import Action Creators from Slices

```typescript
// GOOD — import from barrel
import { setLoading, setActiveTab } from '@/state'

// GOOD — import from specific slice when barrel has conflicts
import { setCurrentQuestion } from '@/state/slice/workspace'
import { setLoading as setUserLoading } from '@/state/slice/user'

// BAD — inline action objects
dispatch({ type: 'ui/setLoading', payload: true })
```

## Selector Patterns

- Use memoized selectors for derived state (`selectIsCompleted`, `selectMilestoneProgress`)
- Never compute derived state in components when a selector exists
- Use `selectMessages` for list operations, `selectLastUserMessageContent` for single-value checks

## RTK Query Cache Invalidation

Use `invalidateTags` for cache refresh, not manual refetches:

```typescript
dispatch(userApi.util.invalidateTags(['CreditBalance', 'CreditUsage']))
dispatch(sessionApi.util.invalidateTags([{ type: 'Sessions', id: 'LIST' }]))
```
