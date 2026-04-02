import {
    useCallback,
    useEffect,
    useLayoutEffect,
    useMemo,
    useRef,
    useState
} from 'react'
import type { CSSProperties } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import AgentSetting from '@/components/agent-setting'
import {
    Conversation,
    ConversationContent,
    ConversationScrollButton
} from '@/components/ai-elements/conversation'
import { Loader } from '@/components/ai-elements/loader'
import ChatMessageContent from '@/components/chat-message-content'
// import DownloadFilesChat, {
//     ExternalImageUrl
// } from '@/components/download-files-chat'
import QuestionInput from '@/components/question-input'
import Sidebar from '@/components/sidebar'
import ThinkingMessage from '@/components/thinking-message'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { useChat } from '@/hooks/use-chat-query'
import { useIsMobile } from '@/hooks/use-mobile'
import ChatMiniTools from '@/components/media/image/chat-mini-tools'
import {
    selectIsLoading,
    setQuestionMode,
    setSelectedGitHubRepository,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { QUESTION_MODE } from '@/typings/agent'
import { FinishReason } from '@/typings/chat'
import { ContentPart, groupMessageParts } from '@/utils/chat-events'
import { useGoogleDrive } from '@/hooks/use-google-drive'
import { useGitHub } from '@/hooks/use-github'
import type { GitHubRepository } from '@/services/connector.service'
import { type MiniTool } from '@/constants/media-tools'
import { useChatMediaPreference } from '@/hooks/use-chat-media-preference'
import { useSessionEnter } from '@/hooks/use-session-enter'
import ChatHeader from '@/components/chat-header'
import { StorybookProvider } from '@/contexts/storybook-context'
import { StorybookModal } from '@/components/ui/storybook-modal'

const MINI_TOOLS_VERTICAL_GAP = 12

const getFinishReasonMessage = (
    finishReason: FinishReason,
    t: (key: string) => string
): string | null => {
    switch (finishReason) {
        case FinishReason.MAX_TOKENS:
            return t('chat.finishReasons.maxTokens')
        case FinishReason.CANCELED:
            return t('chat.finishReasons.canceled')
        case FinishReason.ERROR:
            return t('chat.finishReasons.error')
        case FinishReason.PERMISSION_DENIED:
            return t('chat.finishReasons.permissionDenied')
        case FinishReason.PAUSE_TURN:
            return t('chat.finishReasons.paused')
        case FinishReason.END_TURN:
        case FinishReason.TOOL_USE:
        case FinishReason.UNKNOWN:
        default:
            return null
    }
}

function ChatPageContent() {
    const { t } = useTranslation()
    const [searchParams, setSearchParams] = useSearchParams()
    const initialSessionId = searchParams.get('id')

    const location = useLocation()
    const navigateTo = useNavigate()
    const [isOpenSetting, setIsOpenSetting] = useState(false)
    const [filesCount, setFilesCount] = useState(0)
    const isMobile = useIsMobile()
    const [advancedPreviewTarget, setAdvancedPreviewTarget] =
        useState<HTMLDivElement | null>(null)
    const dispatch = useAppDispatch()

    // Restore session state when entering a session
    useSessionEnter()

    const {
        sessionId,
        setSessionId,
        sessionData,
        sessionError,
        messages,
        chatStatus,
        isHistoryLoading,
        isLoadingMore,
        hasMoreMessages,
        isWaitingForNextEvent,
        showThinking,
        hydrateSessionHistory,
        loadMoreMessages,
        resetConversationState,
        sendMessage,
        isSubmitting,
        stopActiveStream,
        advancedModeSettings,
        setAdvancedModeSettings,
        editingMessageId,
        setEditingMessageId,
        editMessage
    } = useChat()

    const {
        isConnected: isGoogleDriveConnected,
        isAuthLoading: isGoogleDriveAuthLoading,
        handleGoogleDriveClick,
        downloadedFiles: downloadedGoogleDriveFiles,
        clearDownloadedFiles
    } = useGoogleDrive()

    const [isConnectorDropdownOpen, setIsConnectorDropdownOpen] =
        useState(false)

    const {
        isConnected: isGitHubConnected,
        handleGitHubClick: handleGitHubConnect
    } = useGitHub({
        onConnectionSuccess: () => {
            // Auto-open dropdown after successful GitHub connection
            setIsConnectorDropdownOpen(true)
        }
    })

    const isLoading = useAppSelector(selectIsLoading)
    const miniToolsDisabled =
        isLoading || isSubmitting || chatStatus === 'running'
    const {
        chatMediaPreference,
        applyMiniToolSelection,
        clearMiniToolSelection
    } = useChatMediaPreference()

    const handleRepositorySelect = useCallback(
        (repository: GitHubRepository | undefined) => {
            dispatch(
                setSelectedGitHubRepository(
                    repository
                        ? {
                              owner: repository.owner,
                              name: repository.name,
                              full_name: repository.full_name,
                              default_branch: repository.default_branch
                          }
                        : undefined
                )
            )
        },
        [dispatch]
    )

    const showChatMiniTools =
        chatMediaPreference.enabled && chatMediaPreference.type === 'image'
    const miniToolsRef = useRef<HTMLDivElement | null>(null)
    const [miniToolsHeight, setMiniToolsHeight] = useState(0)
    const [miniToolClearSignal, setMiniToolClearSignal] = useState(0)

    const handleMiniToolSelect = useCallback(
        (tool: MiniTool) => {
            applyMiniToolSelection(tool)
        },
        [applyMiniToolSelection]
    )

    const handleMiniToolClear = useCallback(() => {
        clearMiniToolSelection()
    }, [clearMiniToolSelection])

    // Track ChatMiniTools height so the conversation area can shrink accordingly
    useLayoutEffect(() => {
        if (!showChatMiniTools) {
            setMiniToolsHeight((prev) => (prev === 0 ? prev : 0))
            return
        }

        const element = miniToolsRef.current

        if (!element) return

        const applyHeight = (value: number) => {
            setMiniToolsHeight((prev) => (prev === value ? prev : value))
        }

        const updateHeight = () => {
            applyHeight(Math.round(element.offsetHeight))
        }

        updateHeight()

        const observer = new ResizeObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.target === element) {
                    applyHeight(Math.round(entry.contentRect.height))
                }
            })
        })

        observer.observe(element)

        return () => {
            observer.disconnect()
        }
    }, [showChatMiniTools])

    const conversationExtraOffset = showChatMiniTools
        ? Math.round(miniToolsHeight + MINI_TOOLS_VERTICAL_GAP)
        : 0

    const conversationStyle = conversationExtraOffset
        ? ({
              '--chat-media-tools-offset': `${conversationExtraOffset}px`
          } as CSSProperties)
        : undefined

    // Infinite scroll: load older messages when scrolling to top
    const topSentinelRef = useRef<HTMLDivElement>(null)
    const scrollContainerRef = useRef<HTMLElement | null>(null)
    const prevScrollHeightRef = useRef(0)

    // Find the scrollable ancestor once the sentinel mounts
    useEffect(() => {
        if (!topSentinelRef.current) return
        let el = topSentinelRef.current.parentElement
        while (el) {
            const style = getComputedStyle(el)
            if (
                style.overflowY === 'auto' ||
                style.overflowY === 'scroll' ||
                style.overflow === 'auto' ||
                style.overflow === 'scroll'
            ) {
                scrollContainerRef.current = el
                break
            }
            el = el.parentElement
        }
    }, [])

    // Preserve scroll position after older messages are prepended
    useLayoutEffect(() => {
        const container = scrollContainerRef.current
        if (!container || prevScrollHeightRef.current === 0) return

        const newScrollHeight = container.scrollHeight
        container.scrollTop += newScrollHeight - prevScrollHeightRef.current
        prevScrollHeightRef.current = 0
    }, [messages])

    // Observe the top sentinel to trigger loading more messages
    useEffect(() => {
        const sentinel = topSentinelRef.current
        const container = scrollContainerRef.current
        if (!sentinel || !container || !hasMoreMessages || isLoadingMore) return

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    // Record scroll height before prepending so we can restore position
                    prevScrollHeightRef.current = container.scrollHeight
                    loadMoreMessages()
                }
            },
            { root: container, rootMargin: '200px 0px 0px 0px' }
        )

        observer.observe(sentinel)
        return () => observer.disconnect()
    }, [hasMoreMessages, isLoadingMore, loadMoreMessages])

    // Group message parts for rendering
    const groupedMessages = useMemo(() => {
        return groupMessageParts(messages)
    }, [messages])

    // Build a map of all tool results across all messages for O(1) lookups
    // This allows tool_calls to find their tool_results even when they're in different groups
    const allToolResults = useMemo(() => {
        const map = new Map<string, ContentPart>()
        messages.forEach((message) => {
            if (message.parts) {
                message.parts.forEach((part) => {
                    if (part.type === 'tool_result' && part.tool_call_id) {
                        map.set(part.tool_call_id, part)
                    }
                })
            }
        })
        return map
    }, [messages])

    // Extract Google Storage image URLs from all tool results to display at the end of chat
    // const externalImageUrls = useMemo((): ExternalImageUrl[] => {
    //     if (allToolResults.size === 0) return []
    //
    //     const urls: ExternalImageUrl[] = []
    //     const googleStorageRegex =
    //         /https:\/\/storage\.googleapis\.com\/[^\s"'<>]+/g
    //
    //     // Build a set of URLs already present in assistant messages to avoid duplicates
    //     const urlsInAssistantMessages = new Set<string>()
    //     const urlRegex = /https?:\/\/[^\s"'<>()]+/g
    //     messages.forEach((message) => {
    //         if (message.role === 'assistant') {
    //             // Check message content
    //             if (message.content) {
    //                 const matches = message.content.match(urlRegex)
    //                 if (matches) {
    //                     matches.forEach((url) =>
    //                         urlsInAssistantMessages.add(url)
    //                     )
    //                 }
    //             }
    //             // Check message parts for text content
    //             if (message.parts) {
    //                 message.parts.forEach((part) => {
    //                     if (part.type === 'text' && part.text) {
    //                         const matches = part.text.match(urlRegex)
    //                         if (matches) {
    //                             matches.forEach((url) =>
    //                                 urlsInAssistantMessages.add(url)
    //                             )
    //                         }
    //                     }
    //                 })
    //             }
    //         }
    //     })
    //
    //     allToolResults.forEach((toolResult) => {
    //         // Check in content field
    //         if (toolResult.content) {
    //             const matches = toolResult.content.match(googleStorageRegex)
    //             if (matches) {
    //                 matches.forEach((url) => {
    //                     const urlParts = url.split('/')
    //                     const fileName =
    //                         urlParts[urlParts.length - 1]?.split('?')[0] ||
    //                         'image'
    //                     urls.push({ url, name: fileName })
    //                 })
    //             }
    //         }
    //         // Check in output.value field (can be a string or array of objects with url)
    //         if (toolResult.output?.value) {
    //             const outputValue = toolResult.output.value
    //             if (typeof outputValue === 'string') {
    //                 const matches = outputValue.match(googleStorageRegex)
    //                 if (matches) {
    //                     matches.forEach((url) => {
    //                         const urlParts = url.split('/')
    //                         const fileName =
    //                             urlParts[urlParts.length - 1]?.split('?')[0] ||
    //                             'image'
    //                         urls.push({ url, name: fileName })
    //                     })
    //                 }
    //             } else if (Array.isArray(outputValue)) {
    //                 // Handle array of objects with url property
    //                 outputValue.forEach((item) => {
    //                     if (item.url?.includes('storage.googleapis.com')) {
    //                         const urlParts = item.url.split('/')
    //                         const fileName =
    //                             urlParts[urlParts.length - 1]?.split('?')[0] ||
    //                             'image'
    //                         urls.push({ url: item.url, name: fileName })
    //                     }
    //                 })
    //             }
    //         }
    //     })
    //
    //     // Remove duplicates based on URL and filter out URLs already in assistant messages
    //     const uniqueUrls = urls.filter(
    //         (item, index, self) =>
    //             index === self.findIndex((t) => t.url === item.url) &&
    //             !urlsInAssistantMessages.has(item.url)
    //     )
    //
    //     return uniqueUrls
    // }, [allToolResults, messages])

    // Get finish reason from the last message part
    const lastMessageFinishReason = useMemo(() => {
        if (groupedMessages.length === 0) return null
        const lastGroup = groupedMessages[groupedMessages.length - 1]
        if (!lastGroup.parts || lastGroup.parts.length === 0) return null
        const lastPart = lastGroup.parts[lastGroup.parts.length - 1]
        return lastPart.finish_reason || null
    }, [groupedMessages])

    // Set question mode to CHAT when the chat page loads
    useEffect(() => {
        dispatch(setQuestionMode(QUESTION_MODE.CHAT))
    }, [dispatch])

    useEffect(() => {
        setSessionId(initialSessionId)
    }, [initialSessionId, setSessionId])

    useEffect(() => {
        if (!sessionId) {
            resetConversationState()
            return
        }

        // Skip hydration if agent is already running (e.g., navigated from home page with active query)
        if (chatStatus === 'running') {
            return
        }

        hydrateSessionHistory(sessionId).catch((error) => {
            console.error('Failed to hydrate history', error)
        })
    }, [chatStatus, hydrateSessionHistory, resetConversationState, sessionId])

    const handleSend = useCallback(
        async (overrideQuestion?: string) => {
            await sendMessage(overrideQuestion)
        },
        [sendMessage]
    )

    useEffect(() => {
        const rawState =
            (location.state as Record<string, unknown> | null) ?? null
        const pendingQuestion =
            typeof rawState?.pendingQuestion === 'string'
                ? (rawState.pendingQuestion as string)
                : undefined

        if (pendingQuestion) {
            handleSend(pendingQuestion)
            if (rawState) {
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                const { pendingQuestion: _ignored, ...rest } = rawState
                const nextState = Object.keys(rest).length > 0 ? rest : null
                navigateTo('.', { replace: true, state: nextState })
            } else {
                navigateTo('.', { replace: true, state: null })
            }
        }
    }, [handleSend, location.state, navigateTo])

    const handleKeyDown = useCallback(
        (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                if (!isSubmitting && chatStatus !== 'running') {
                    handleSend()
                }
            }
        },
        [chatStatus, handleSend, isSubmitting]
    )

    // Only update URL when a new session is created (not when loading existing session)
    // This prevents circular updates while allowing new session navigation
    useEffect(() => {
        // If we have a sessionId in state but no ID in URL, it means a new session was created
        if (sessionId && !initialSessionId) {
            setSearchParams({ id: sessionId })
        }
    }, [sessionId, initialSessionId, setSearchParams])

    return (
        <div className="flex h-screen overflow-hidden">
            <SidebarProvider>
                <Sidebar />
                <div className="sidebar-home absolute z-20 ml-6 bottom-8 hidden md:block">
                    <SidebarTrigger className="size-6 p-0" />
                </div>
                <div className="flex-1 flex flex-col min-h-0">
                    <ChatHeader
                        sessionData={sessionData}
                        onOpenSetting={() => setIsOpenSetting(true)}
                    />
                    <div
                        id="chat-wrapper"
                        className="flex flex-1 min-h-0 justify-center"
                    >
                        <div className="flex-1 flex flex-col items-center min-h-0 py-3 md:py-4">
                            <div className="chat-separator hidden md:block" />
                            <Conversation
                                className={`chat-conversation w-full flex-1 min-h-0${filesCount > 0 ? ' with-files' : ''}`}
                                style={conversationStyle}
                            >
                                <ConversationContent className="p-0 md:p-2 max-w-4xl w-full">
                                    {/* Sentinel for infinite scroll - triggers loading older messages */}
                                    <div ref={topSentinelRef} />
                                    {isLoadingMore && (
                                        <div className="flex items-center justify-center gap-2 py-4">
                                            <Loader size={16} />
                                            <span className="text-sm text-neutral-500">
                                                {t('chat.loadingHistory')}
                                            </span>
                                        </div>
                                    )}
                                    {isHistoryLoading && (
                                        <div className="flex items-center justify-center gap-2 py-12">
                                            <Loader size={20} />
                                            <span className="text-sm text-neutral-500">
                                                {t('chat.loadingHistory')}
                                            </span>
                                        </div>
                                    )}
                                    {sessionError && (
                                        <div className="mb-4 rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500 dark:text-red-300">
                                            {sessionError}
                                        </div>
                                    )}
                                    {!isHistoryLoading &&
                                        !sessionError &&
                                        messages.length === 0 && (
                                            <div className="text-sm text-neutral-500 text-center py-12">
                                                {t('chat.emptyState')}
                                            </div>
                                        )}

                                    {groupedMessages.map((group, index) => {
                                        // Check if this is the last group and agent is running
                                        const isLastGroup =
                                            index === groupedMessages.length - 1
                                        const isStreaming =
                                            isLastGroup &&
                                            chatStatus === 'running'

                                        return (
                                            <ChatMessageContent
                                                key={index}
                                                group={group}
                                                isStreaming={isStreaming}
                                                isWaitingForNextEvent={
                                                    isLastGroup &&
                                                    isWaitingForNextEvent
                                                }
                                                allToolResults={allToolResults}
                                                allGroups={groupedMessages}
                                                groupIndex={index}
                                                agentType={
                                                    sessionData?.agent_type
                                                }
                                                editingMessageId={editingMessageId}
                                                onEditStart={setEditingMessageId}
                                                onEditSubmit={editMessage}
                                                onEditCancel={() => setEditingMessageId(null)}
                                                chatStatus={chatStatus}
                                            />
                                        )
                                    })}

                                    {/* Show external images (Google Storage) at the end of chat */}
                                    {/*{externalImageUrls.length > 0 &&*/}
                                    {/*    chatStatus !== 'running' && (*/}
                                    {/*        <DownloadFilesChat*/}
                                    {/*            files={[]}*/}
                                    {/*            sessionId={sessionId || ''}*/}
                                    {/*            externalImageUrls={*/}
                                    {/*                externalImageUrls*/}
                                    {/*            }*/}
                                    {/*        />*/}
                                    {/*    )}*/}

                                    {showThinking && <ThinkingMessage />}

                                    {lastMessageFinishReason &&
                                        getFinishReasonMessage(
                                            lastMessageFinishReason,
                                            t
                                        ) && (
                                            <div className="rounded-lg border border-yellow dark:border-yellow/40 bg-yellow dark:bg-yellow/10 p-3 text-sm text-black dark:text-yellow">
                                                {getFinishReasonMessage(
                                                    lastMessageFinishReason,
                                                    t
                                                )}
                                            </div>
                                        )}
                                </ConversationContent>
                                <ConversationScrollButton />
                            </Conversation>

                            <div className="flex w-full shrink-0 flex-col items-start gap-3 px-3 md:px-0 max-w-4xl">
                                {showChatMiniTools && (
                                    <div ref={miniToolsRef} className="w-full">
                                        <ChatMiniTools
                                            disabled={miniToolsDisabled}
                                            sessionId={sessionId ?? undefined}
                                            modelName={
                                                chatMediaPreference.model_name
                                            }
                                            provider={
                                                chatMediaPreference.provider
                                            }
                                            clearSignal={miniToolClearSignal}
                                            onSelect={handleMiniToolSelect}
                                            onClear={handleMiniToolClear}
                                            advancedModeSettings={
                                                advancedModeSettings
                                            }
                                            onAdvancedModeSettingsChange={
                                                setAdvancedModeSettings
                                            }
                                            previewPortalTarget={
                                                advancedPreviewTarget
                                            }
                                        />
                                    </div>
                                )}
                                <div className="relative w-full">
                                    {isMobile && (
                                        <div
                                            ref={setAdvancedPreviewTarget}
                                            className="absolute -top-14 right-3 z-30"
                                        />
                                    )}
                                    <QuestionInput
                                        hideSuggestions
                                        className="w-full max-w-none"
                                        textareaClassName="min-h-[128px] md:min-h-35 w-full"
                                        placeholder={t('home.askAnything')}
                                        value=""
                                        handleKeyDown={handleKeyDown}
                                        handleSubmit={handleSend}
                                        hideFeatureSelector
                                        isDisabled={isLoading}
                                        hideModeSelector
                                        hideBuildModeSelector
                                        hideAdvancedMode={showChatMiniTools}
                                        handleCancel={stopActiveStream}
                                        onOpenSetting={() =>
                                            setIsOpenSetting(true)
                                        }
                                        onFilesChange={setFilesCount}
                                        onGoogleDriveClick={
                                            handleGoogleDriveClick
                                        }
                                        isGoogleDriveConnected={
                                            isGoogleDriveConnected
                                        }
                                        isGoogleDriveAuthLoading={
                                            isGoogleDriveAuthLoading
                                        }
                                        googleDriveFiles={
                                            downloadedGoogleDriveFiles
                                        }
                                        onGoogleDriveFilesHandled={
                                            clearDownloadedFiles
                                        }
                                        isGitHubConnected={isGitHubConnected}
                                        onGitHubConnect={handleGitHubConnect}
                                        onRepositorySelect={
                                            handleRepositorySelect
                                        }
                                        isConnectorDropdownOpen={
                                            isConnectorDropdownOpen
                                        }
                                        onConnectorDropdownOpenChange={
                                            setIsConnectorDropdownOpen
                                        }
                                        advancedModeSettings={
                                            advancedModeSettings
                                        }
                                        onAdvancedModeSettingsChange={
                                            setAdvancedModeSettings
                                        }
                                        onMiniToolClear={() =>
                                            setMiniToolClearSignal(
                                                (prev) => prev + 1
                                            )
                                        }
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <StorybookModal />
            </SidebarProvider>
            <AgentSetting
                isOpen={isOpenSetting}
                onOpenChange={setIsOpenSetting}
            />
        </div>
    )
}

export function ChatPage() {
    return (
        <StorybookProvider>
            <ChatPageContent />
        </StorybookProvider>
    )
}

export const Component = ChatPage
