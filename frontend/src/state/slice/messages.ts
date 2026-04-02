import { createSlice, PayloadAction, createSelector } from '@reduxjs/toolkit'
import { Message, AgentContext } from '@/typings/agent'
import { uniqBy } from 'lodash'

interface MessagesState {
    messages: Message[]
    editingMessage?: Message
}

const initialState: MessagesState = {
    messages: [],
    editingMessage: undefined
}

const messagesSlice = createSlice({
    name: 'messages',
    initialState,
    reducers: {
        setMessages: (state, action: PayloadAction<Message[]>) => {
            state.messages = action.payload
        },
        addMessage: (state, action: PayloadAction<Message>) => {
            const messages = uniqBy([...state.messages, action.payload], 'id')
            state.messages = messages
        },
        updateMessage: (state, action: PayloadAction<Message>) => {
            const index = state.messages.findIndex(
                (msg) => msg.id === action.payload.id
            )
            if (index !== -1) {
                state.messages[index] = action.payload
            }
        },
        setEditingMessage: (
            state,
            action: PayloadAction<Message | undefined>
        ) => {
            state.editingMessage = action.payload
        }
    }
})

export const { setMessages, addMessage, updateMessage, setEditingMessage } =
    messagesSlice.actions
export const messagesReducer = messagesSlice.reducer

// Base Selectors
export const selectMessages = (state: { messages: MessagesState }) =>
    state.messages.messages
export const selectEditingMessage = (state: { messages: MessagesState }) =>
    state.messages.editingMessage

// Memoized Selectors for Performance Optimization
export const selectMessagesLength = createSelector(
    [selectMessages],
    (messages) => messages.length
)

export const selectLastMessage = createSelector(
    [selectMessages],
    (messages) => messages[messages.length - 1]
)

export const selectLatestUserMessage = createSelector(
    [selectMessages],
    (messages) => {
        const userMessages = messages.filter((msg) => msg.role === 'user')
        return userMessages.length > 0
            ? userMessages[userMessages.length - 1]
            : undefined
    }
)

export const selectVisibleMessages = createSelector(
    [selectMessages],
    (messages) => messages.filter((msg) => !msg.isHidden)
)

// Memoized selector for grouped messages (expensive computation)
export const selectGroupedMessages = createSelector(
    [selectVisibleMessages],
    (visibleMessages) => {
        const result: Array<{
            type: 'main' | 'subagent'
            agentContext?: AgentContext
            messages: Message[]
        }> = []

        let currentGroup: Message[] = []
        let currentAgentContext: AgentContext | undefined = undefined

        for (const message of visibleMessages) {
            const messageAgentContext = message.agentContext

            const needNewGroup =
                messageAgentContext?.agentId !==
                    (currentAgentContext as AgentContext | undefined)
                        ?.agentId ||
                messageAgentContext?.agentType !==
                    (currentAgentContext as AgentContext | undefined)?.agentType

            if (needNewGroup && currentGroup.length > 0) {
                result.push({
                    type:
                        currentAgentContext?.agentType === 'subagent'
                            ? 'subagent'
                            : 'main',
                    agentContext: currentAgentContext,
                    messages: currentGroup
                })
                currentGroup = []
            }

            currentGroup.push(message)
            currentAgentContext = messageAgentContext
        }

        if (currentGroup.length > 0) {
            result.push({
                type:
                    currentAgentContext?.agentType === 'subagent'
                        ? 'subagent'
                        : 'main',
                agentContext: currentAgentContext,
                messages: currentGroup
            })
        }

        return result
    }
)

// Selector factory for forked sessions (parameterized selector)
export const makeSelectGroupedMessagesForForkedSession = () =>
    createSelector(
        [selectVisibleMessages, (_state: unknown, isForkedSession: boolean) => isForkedSession],
        (visibleMessages, isForkedSession) => {
            let filtered = visibleMessages
            if (isForkedSession && filtered.length > 0) {
                const firstUserIndex = filtered.findIndex((msg) => msg.role === 'user')
                if (firstUserIndex !== -1) {
                    filtered = [
                        ...filtered.slice(0, firstUserIndex),
                        ...filtered.slice(firstUserIndex + 1)
                    ]
                }
            }

            const result: Array<{
                type: 'main' | 'subagent'
                agentContext?: AgentContext
                messages: Message[]
            }> = []

            let currentGroup: Message[] = []
            let currentAgentContext: AgentContext | undefined = undefined

            for (const message of filtered) {
                const messageAgentContext = message.agentContext

                const needNewGroup =
                    messageAgentContext?.agentId !==
                        (currentAgentContext as AgentContext | undefined)
                            ?.agentId ||
                    messageAgentContext?.agentType !==
                        (currentAgentContext as AgentContext | undefined)?.agentType

                if (needNewGroup && currentGroup.length > 0) {
                    result.push({
                        type:
                            currentAgentContext?.agentType === 'subagent'
                                ? 'subagent'
                                : 'main',
                        agentContext: currentAgentContext,
                        messages: currentGroup
                    })
                    currentGroup = []
                }

                currentGroup.push(message)
                currentAgentContext = messageAgentContext
            }

            if (currentGroup.length > 0) {
                result.push({
                    type:
                        currentAgentContext?.agentType === 'subagent'
                            ? 'subagent'
                            : 'main',
                    agentContext: currentAgentContext,
                    messages: currentGroup
                })
            }

            return result
        }
    )

// Memoized selector for preview URL from fullstack project init
export const selectPreviewUrl = createSelector(
    [selectMessages],
    (messages) => {
        const fullstackResult = [...messages]
            .reverse()
            .find(
                (message) =>
                    message.action?.type === 'fullstack_project_init' &&
                    message.action?.data?.result
            )

        const result = fullstackResult?.action?.data?.result
        if (result && typeof result === 'object') {
            const preview = (result as { preview_url?: string }).preview_url
            if (preview) {
                return preview
            }
        }
        return ''
    }
)

// Memoized selector for last user message content (used in review)
export const selectLastUserMessageContent = createSelector(
    [selectLatestUserMessage],
    (latestUserMessage) => latestUserMessage?.content || ''
)

// Memoized selector for streaming state - tracks if the last message is being streamed
// Returns a lightweight object that changes when streaming content updates
export const selectStreamingState = createSelector(
    [selectLastMessage],
    (lastMessage) => {
        if (!lastMessage) return { isStreaming: false, contentLength: 0 }
        // Track content length changes for auto-scroll during streaming
        const contentLength = lastMessage.content?.length || 0
        const isThinkMessage = lastMessage.isThinkMessage || false
        return {
            isStreaming: isThinkMessage,
            contentLength,
            messageId: lastMessage.id
        }
    }
)
