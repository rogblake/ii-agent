import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import {
    BUILD_MODE,
    BUILD_STEP,
    Milestone,
    PlanModificationSuggestion
} from '@/typings/agent'
import type { CouncilPreference } from './settings'

/**
 * Per-session UI state that should be saved and restored when switching between sessions
 * Note: isCompleted/isStopped/isWaitingForInput are derived from runStatus via selectors
 */
export interface PerSessionState {
    buildMode: BUILD_MODE
    buildStep: BUILD_STEP
    selectedFeature: string | null
    milestones: Milestone[]
    selectedMilestoneId: string | null
    planSummary: string | null
    planModificationOptions: {
        message: string
        suggestions: PlanModificationSuggestion[]
    } | null
    runStatus: string | null
    councilPreference?: CouncilPreference
    lastAccessed?: number // Timestamp for LRU eviction
}

interface SessionStateCache {
    [sessionId: string]: PerSessionState
}

interface SessionStateSlice {
    cache: SessionStateCache
}

const initialState: SessionStateSlice = {
    cache: {}
}

const MAX_CACHED_SESSIONS = 100

const sessionStateSlice = createSlice({
    name: 'sessionState',
    initialState,
    reducers: {
        saveSessionState: (
            state,
            action: PayloadAction<{ sessionId: string; state: PerSessionState }>
        ) => {
            // Update the session state with current timestamp
            state.cache[action.payload.sessionId] = {
                ...action.payload.state,
                lastAccessed: Date.now()
            }

            // LRU eviction: Keep only the 100 most recently accessed sessions
            const sessionIds = Object.keys(state.cache)
            if (sessionIds.length > MAX_CACHED_SESSIONS) {
                // Sort by lastAccessed descending (most recent first)
                const sortedSessions = sessionIds
                    .map((id) => ({
                        id,
                        lastAccessed: state.cache[id].lastAccessed || 0
                    }))
                    .sort((a, b) => b.lastAccessed - a.lastAccessed)

                // Keep only the most recent MAX_CACHED_SESSIONS
                const sessionsToKeep = new Set(
                    sortedSessions
                        .slice(0, MAX_CACHED_SESSIONS)
                        .map((s) => s.id)
                )

                // Remove old sessions
                sessionIds.forEach((id) => {
                    if (!sessionsToKeep.has(id)) {
                        delete state.cache[id]
                    }
                })
            }
        },
        clearSessionState: (state, action: PayloadAction<string>) => {
            delete state.cache[action.payload]
        },
        clearAllSessionStates: (state) => {
            state.cache = {}
        }
    }
})

export const { saveSessionState, clearSessionState, clearAllSessionStates } =
    sessionStateSlice.actions
export const sessionStateReducer = sessionStateSlice.reducer

// Selectors
export const selectSessionState =
    (sessionId: string) => (state: { sessionState: SessionStateSlice }) =>
        state.sessionState.cache[sessionId]
