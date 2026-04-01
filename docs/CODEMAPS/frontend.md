<!-- Generated: 2026-03-29 | Routes: 24 | Hooks: 19 | Slices: 12 | Token estimate: ~800 -->
# Frontend

## Stack

React 18 + TypeScript + Vite + Redux Toolkit + Socket.IO Client + TailwindCSS

## Routes (frontend/src/app/routes/)

| Route | File | Purpose |
|-------|------|---------|
| `/` | `home.tsx` | Landing / main entry |
| `/chat` | `chat.tsx` | Chat interface |
| `/agent` | `agent.tsx` | Agent workspace |
| `/login` | `login.tsx` | Authentication |
| `/signup` | `signup.tsx` | Registration |
| `/dashboard` | `dashboard.tsx` | User dashboard |
| `/settings` | `settings.tsx` | User settings |
| `/share` | `share.tsx` | Shared session view |
| `/presentations` | `presentations.tsx` | Slides/presentations |
| `/storybooks` | `storybooks.tsx` | Storybook content |
| `/billing-success` | `billing-success.tsx` | Payment success |
| `/billing-cancel` | `billing-cancel.tsx` | Payment cancelled |
| `/session-ledger` | `session-ledger.tsx` | Session credit ledger |
| `/session-usage` | `session-usage.tsx` | Session usage stats |
| `/session-reservations` | `session-reservations.tsx` | Session reservations |
| `/forgot-password` | `forgot-password.tsx` | Password reset |
| `/oauth-consent` | `oauth-consent.tsx` | OAuth consent |
| `/github-callback` | `github-callback.tsx` | GitHub OAuth callback |
| `/google-drive-callback` | `google-drive-callback.tsx` | Google Drive callback |
| `/composio-oauth-callback` | `composio-oauth-callback.tsx` | Composio callback |
| `/revenuecat-callback` | `revenuecat-callback.tsx` | RevenueCat callback |
| `/privacy-policy` | `privacy-policy.tsx` | Privacy policy |
| `/terms-of-use` | `terms-of-use.tsx` | Terms of use |
| `*` | `not-found.tsx` | 404 page |

## Context Providers (frontend/src/contexts/)

Provider tree (outermost first):
```
AppEventsProvider → WebSocketProvider → ChatProvider → RouterOutlet
```

| Context | File | Purpose |
|---------|------|---------|
| `AppEventsProvider` | `app-events-context.tsx` | Singleton event handler (useAppEvents) |
| `WebSocketProvider` | `websocket-context.tsx` | Socket.IO connection, delegates to handleEvent |
| `AuthContext` | `auth-context.tsx` | Authentication state |
| `TerminalContext` | `terminal-context.tsx` | Terminal/sandbox state |
| `StorybookContext` | `storybook-context.tsx` | Storybook viewer state |
| `StorybookEditContext` | `storybook-edit-context.tsx` | Storybook editor state |

## Hooks (frontend/src/hooks/)

| Hook | File | Purpose |
|------|------|---------|
| `useAppEvents` | `use-app-events.tsx` | Event dispatch handler (singleton via context) |
| `useSessionManager` | `use-session-manager.tsx` | Session replay + event reconciliation |
| `useSessionEnter` | `use-session-enter.tsx` | Session join lifecycle |
| `useSessionStateManager` | `use-session-state-manager.tsx` | Session state transitions |
| `useChatQuery` | `use-chat-query.tsx` | Chat message sending |
| `useChatTransport` | `use-chat-transport.tsx` | Chat transport layer |
| `useQuestionHandlers` | `use-question-handlers.tsx` | User input handling |
| `useUploadFiles` | `use-upload-files.tsx` | File upload |
| `useNavigationLeaveSession` | `use-navigation-leave-session.tsx` | Cleanup on nav away |
| `useWebsocketAuthSync` | `use-websocket-auth-sync.tsx` | Auth token sync |
| `useGithub` | `use-github.tsx` | GitHub integration |
| `useGoogleDrive` | `use-google-drive.tsx` | Google Drive integration |
| `useMobile` | `use-mobile.ts` | Mobile platform detection |
| `useRevenuecat` | `use-revenuecat.tsx` | RevenueCat subscriptions |
| `useChatMediaPreference` | `use-chat-media-preference.ts` | Media model preference |
| `useMediaModels` | `use-media-models.ts` | Available media models |
| `useIsSageTheme` | `use-is-sage-theme.ts` | Theme detection |
| `useVideoFrameUpload` | `use-video-frame-upload.ts` | Video frame capture |
| `useWindowSize` | `use-window-size.tsx` | Responsive breakpoints |

## Redux Slices (frontend/src/state/slice/)

| Slice | File | Key State |
|-------|------|-----------|
| `agent` | `agent.ts` | runStatus, cancelling, agentInitialized, projectId |
| `messages` | `messages.ts` | messages array, editingMessage |
| `ui` | `ui.ts` | loading, activeTab, buildMode, planData, milestones |
| `files` | `files.ts` | isUploading, uploadedFiles, requireClearFiles |
| `workspace` | `workspace.ts` | currentQuestion, workspaceInfo, browserUrl |
| `settings` | `settings.ts` | selectedModel, toolSettings |
| `sessions` | `sessions.ts` | activeSessionId, sessions list |
| `user` | `user.ts` | user profile, auth state |
| `editor` | `editor.ts` | Editor state |
| `favorites` | `favorites.ts` | Favorited items |
| `pins` | `pins.ts` | Pinned sessions |
| `session-state` | `session-state.ts` | Session lifecycle state |

## Services (frontend/src/services/)

21 API service files mapping to BE domains:
`auth`, `billing`, `chat`, `connector`, `file`, `fullstack`, `media-template`, `media-tools`, `media`, `mobile-app`, `pin`, `project`, `prompt`, `session`, `settings`, `slide`, `storybook`, `subdomain`, `upload`, `user`, `wishlist`

## Event System (FE side)

```
Socket.IO "chat_event" → websocket-context.tsx
  → handleEventRef.current(data) → use-app-events.tsx
    → switch (data.name: AgentEvent) → Redux dispatches

Session replay: use-session-manager.tsx
  → same handleEvent() path (shared via AppEventsProvider context)
```

Dispatch key: `data.name` (dotted string, e.g. `"agent.response"`)
Enum: `AgentEvent` in `typings/agent.ts` — values match BE `EventType` exactly
Interface: `IEvent { id, name: AgentEvent, content, run_id?, session_id?, run_status? }`
