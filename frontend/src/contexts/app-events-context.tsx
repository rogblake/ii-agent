import { createContext, useContext, type ReactNode } from 'react'
import { useAppEvents } from '@/hooks/use-app-events'

type AppEventsValue = ReturnType<typeof useAppEvents>

const AppEventsContext = createContext<AppEventsValue | null>(null)

interface AppEventsProviderProps {
    children: ReactNode
}

/**
 * Provides a single useAppEvents() instance to the entire app.
 *
 * This MUST wrap WebSocketProvider so that the live socket handler and
 * the session-replay handler share the same refs (agent tracking,
 * streaming message IDs, etc.).
 */
export function AppEventsProvider({ children }: AppEventsProviderProps) {
    const appEvents = useAppEvents()

    return (
        <AppEventsContext.Provider value={appEvents}>
            {children}
        </AppEventsContext.Provider>
    )
}

/**
 * Consume the single AppEvents instance.
 *
 * Must be called inside AppEventsProvider.
 */
export function useAppEventsContext(): AppEventsValue {
    const ctx = useContext(AppEventsContext)
    if (!ctx) {
        throw new Error(
            'useAppEventsContext must be used within an AppEventsProvider'
        )
    }
    return ctx
}
