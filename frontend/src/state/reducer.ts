import { combineReducers } from 'redux'
import { persistReducer } from 'redux-persist'
import storage from 'redux-persist/lib/storage'
import { messagesReducer } from './slice/messages'
import { uiReducer } from './slice/ui'
import { editorReducer } from './slice/editor'
import { agentReducer } from './slice/agent'
import { filesReducer } from './slice/files'
import { workspaceReducer } from './slice/workspace'
import { settingsReducer } from './slice/settings'
import { sessionsReducer } from './slice/sessions'
import { userReducer } from './slice/user'
import { favoritesReducer } from './slice/favorites'
import { pinsReducer } from './slice/pins'
import { sessionStateReducer } from './slice/session-state'
import { fileExplorerReducer } from './slice/file-explorer'
import { userApi } from './api/user.api'
import { sessionApi } from './api/session.api'
import { connectorApi } from './api/connector.api'
import { composioApi } from './api/composio.api'

// Nested persist config for ui slice - only persist mode selections
const uiPersistConfig = {
    key: 'ui',
    storage,
    whitelist: ['questionMode']
}

export default combineReducers({
    messages: messagesReducer,
    ui: persistReducer(uiPersistConfig, uiReducer),
    editor: editorReducer,
    agent: agentReducer,
    files: filesReducer,
    workspace: workspaceReducer,
    settings: settingsReducer,
    sessions: sessionsReducer,
    user: userReducer,
    favorites: favoritesReducer,
    pins: pinsReducer,
    sessionState: sessionStateReducer,
    fileExplorer: fileExplorerReducer,
    [userApi.reducerPath]: userApi.reducer,
    [sessionApi.reducerPath]: sessionApi.reducer,
    [connectorApi.reducerPath]: connectorApi.reducer,
    [composioApi.reducerPath]: composioApi.reducer
})
