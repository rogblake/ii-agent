import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit'
import type { RootState } from '../store'
import { pinService } from '@/services/pin.service'
import type { SessionPinItem } from '@/typings/pin'
import type { ISession } from '@/typings/agent'

interface PinsState {
    pinnedSessionIds: string[]
    pinnedSessions: SessionPinItem[]
    isLoading: boolean
    error: string | null
    isInitialized: boolean
}

const initialState: PinsState = {
    pinnedSessionIds: [],
    pinnedSessions: [],
    isLoading: false,
    error: null,
    isInitialized: false
}

// Async thunks
export const fetchPins = createAsyncThunk(
    'pins/fetchPins',
    async () => {
        const response = await pinService.getPinnedSessions()
        return response.sessions
    }
)

export const pinSessionAsync = createAsyncThunk(
    'pins/pinSession',
    async (sessionId: string) => {
        await pinService.pinSession(sessionId)
        return sessionId
    }
)

export const unpinSessionAsync = createAsyncThunk(
    'pins/unpinSession',
    async (sessionId: string) => {
        await pinService.unpinSession(sessionId)
        return sessionId
    }
)

export const togglePinAsync = createAsyncThunk(
    'pins/togglePin',
    async (sessionId: string, { getState, dispatch }) => {
        const state = getState() as RootState
        const isPinned = state.pins.pinnedSessionIds.includes(sessionId)

        if (isPinned) {
            await pinService.unpinSession(sessionId)
        } else {
            await pinService.pinSession(sessionId)
        }

        // Refetch to sync pinnedSessions; if it fails the fulfilled
        // reducer still updates pinnedSessionIds optimistically.
        try {
            await dispatch(fetchPins()).unwrap()
        } catch {
            // fetchPins failed (transient network error) — fall through
            // so the toggle still reflects in local state.
        }

        return { sessionId, isPinned }
    }
)

const pinsSlice = createSlice({
    name: 'pins',
    initialState,
    reducers: {
        togglePin: (state, action: PayloadAction<string>) => {
            const sessionId = action.payload
            const index = state.pinnedSessionIds.indexOf(sessionId)

            if (index > -1) {
                state.pinnedSessionIds.splice(index, 1)
                state.pinnedSessions = state.pinnedSessions.filter(
                    s => s.session_id !== sessionId
                )
            } else {
                state.pinnedSessionIds.push(sessionId)
            }
        },
        addPin: (state, action: PayloadAction<string>) => {
            const sessionId = action.payload
            if (!state.pinnedSessionIds.includes(sessionId)) {
                state.pinnedSessionIds.push(sessionId)
            }
        },
        removePin: (state, action: PayloadAction<string>) => {
            const sessionId = action.payload
            state.pinnedSessionIds = state.pinnedSessionIds.filter(
                id => id !== sessionId
            )
            state.pinnedSessions = state.pinnedSessions.filter(
                s => s.session_id !== sessionId
            )
        },
        clearPins: (state) => {
            state.pinnedSessionIds = []
            state.pinnedSessions = []
        },
        setPins: (state, action: PayloadAction<string[]>) => {
            state.pinnedSessionIds = action.payload
        },
        clearPinsError: (state) => {
            state.error = null
        }
    },
    extraReducers: (builder) => {
        builder
            // Fetch pins
            .addCase(fetchPins.pending, (state) => {
                state.isLoading = true
                state.error = null
            })
            .addCase(fetchPins.fulfilled, (state, action) => {
                state.isLoading = false
                state.pinnedSessions = action.payload
                state.pinnedSessionIds = action.payload.map(item => item.session_id)
                state.isInitialized = true
            })
            .addCase(fetchPins.rejected, (state, action) => {
                state.isLoading = false
                state.error = action.error.message || 'Failed to fetch pins'
                state.isInitialized = true
            })
            // Pin session
            .addCase(pinSessionAsync.pending, (state) => {
                state.isLoading = true
                state.error = null
            })
            .addCase(pinSessionAsync.fulfilled, (state, action) => {
                state.isLoading = false
                if (!state.pinnedSessionIds.includes(action.payload)) {
                    state.pinnedSessionIds.push(action.payload)
                }
            })
            .addCase(pinSessionAsync.rejected, (state, action) => {
                state.isLoading = false
                state.error = action.error.message || 'Failed to pin session'
            })
            // Unpin session
            .addCase(unpinSessionAsync.pending, (state) => {
                state.isLoading = true
                state.error = null
            })
            .addCase(unpinSessionAsync.fulfilled, (state, action) => {
                state.isLoading = false
                state.pinnedSessionIds = state.pinnedSessionIds.filter(
                    id => id !== action.payload
                )
                state.pinnedSessions = state.pinnedSessions.filter(
                    s => s.session_id !== action.payload
                )
            })
            .addCase(unpinSessionAsync.rejected, (state, action) => {
                state.isLoading = false
                state.error = action.error.message || 'Failed to unpin session'
            })
            // Toggle pin
            .addCase(togglePinAsync.pending, (state) => {
                state.isLoading = true
                state.error = null
            })
            .addCase(togglePinAsync.fulfilled, (state, action) => {
                state.isLoading = false
                // If fetchPins succeeded inside the thunk, state is
                // already authoritative. This ensures correctness as a
                // fallback when fetchPins fails transiently.
                const { sessionId, isPinned } = action.payload
                if (isPinned) {
                    state.pinnedSessionIds = state.pinnedSessionIds.filter(
                        id => id !== sessionId
                    )
                    state.pinnedSessions = state.pinnedSessions.filter(
                        s => s.session_id !== sessionId
                    )
                } else if (!state.pinnedSessionIds.includes(sessionId)) {
                    state.pinnedSessionIds.push(sessionId)
                }
            })
            .addCase(togglePinAsync.rejected, (state, action) => {
                state.isLoading = false
                state.error = action.error.message || 'Failed to toggle pin'
            })
    }
})

export const { togglePin, addPin, removePin, clearPins, setPins, clearPinsError } = pinsSlice.actions

export const selectPinnedSessionIds = (state: RootState) => state.pins.pinnedSessionIds
export const selectPinnedSessions = (state: RootState) => state.pins.pinnedSessions
export const selectIsPinned = (sessionId: string) => (state: RootState) =>
    state.pins.pinnedSessionIds.includes(sessionId)
export const selectPinsLoading = (state: RootState) => state.pins.isLoading
export const selectPinsError = (state: RootState) => state.pins.error
export const selectPinsInitialized = (state: RootState) => state.pins.isInitialized

/**
 * Convert a pinned session item to an ISession stub for display in sidebar lists.
 * Only used for pinned sessions that haven't been loaded via pagination yet.
 */
export function pinnedItemToSession(item: SessionPinItem): ISession {
    return {
        id: item.session_id,
        workspace_dir: '',
        created_at: item.session_created_at ?? item.created_at,
        name: item.session_name ?? undefined,
        agent_type: item.agent_type ?? undefined,
        last_message_at: item.last_message_at
    }
}

export const pinsReducer = pinsSlice.reducer
