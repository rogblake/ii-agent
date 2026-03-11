import { configureStore } from '@reduxjs/toolkit'
import type { TypedUseSelectorHook } from 'react-redux'
import { useDispatch, useSelector } from 'react-redux'
import { persistReducer, persistStore } from 'redux-persist'
import storage from 'redux-persist/lib/storage'

import rootReducer from './reducer'
import { userApi } from './api/user.api'
import { sessionApi } from './api/session.api'
import { connectorApi } from './api/connector.api'
import { composioApi } from './api/composio.api'

// Default media preference for migration (models are loaded dynamically via useMediaModels hook)
const DEFAULT_MEDIA_PREFERENCE = {
    enabled: false,
    type: 'image' as const,
    model_name: '',
    provider: '',
    voice_enabled: true,
    rich_dialogue: false
}

const persistConfig = {
    key: 'root',
    whitelist: ['settings', 'favorites', 'sessionState'],
    storage,
    version: 3,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    migrate: (state: any) => {
        // Ensure chatToolSettings has default values if undefined
        if (state?.settings) {
            state.settings.chatToolSettings = {
                web_search: true,
                web_visit: true,
                image_search: true,
                code_interpreter: true,
                generate_image: true,
                generate_video: false
            }
        }

        if (state?.settings && !state.settings.chatMediaPreference) {
            state.settings.chatMediaPreference = DEFAULT_MEDIA_PREFERENCE
        } else if (state?.settings?.chatMediaPreference) {
            // Always reset enabled to false on page reload
            // so user doesn't stay in Generate Image/Video mode unexpectedly
            state.settings.chatMediaPreference = {
                ...state.settings.chatMediaPreference,
                enabled: false,
                references: undefined
            }
        }

        // Council: ensure state exists, reset enabled on reload
        if (state?.settings) {
            if (!state.settings.councilPreference) {
                state.settings.councilPreference = {
                    enabled: false,
                    councilModelIds: [],
                    synthesisModelId: ''
                }
            } else {
                state.settings.councilPreference = {
                    ...state.settings.councilPreference,
                    enabled: false
                }
            }
        }
        return Promise.resolve(state)
    }
}
const persistedReducer = persistReducer(persistConfig, rootReducer)

const store = configureStore({
    reducer: persistedReducer,
    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({ serializableCheck: false }).concat(
            userApi.middleware,
            sessionApi.middleware,
            connectorApi.middleware,
            composioApi.middleware
        ),
    devTools: !import.meta.env.PROD
})

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch

// Use throughout your app instead of plain `useDispatch` and `useSelector`
export const useAppDispatch: () => AppDispatch = useDispatch
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector

export default store

export const persistor = persistStore(store)
