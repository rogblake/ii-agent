import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'

import AgentHeader from '@/components/header'
import ChatMessageContent from '@/components/chat-message-content'
import DownloadFilesChat, {
    ExternalImageUrl
} from '@/components/download-files-chat'
import Sidebar from '@/components/sidebar'
import { sessionService } from '@/services/session.service'
import { chatService } from '@/services/chat.service'
import { ISession } from '@/typings/agent'
import {
    type ChatMessage,
    type ContentPart,
    groupMessageParts
} from '@/utils/chat-events'
import { Loader } from './ai-elements/loader'
import {
    Conversation,
    ConversationContent,
    ConversationScrollButton
} from './ai-elements/conversation'

export function ShareChatContent() {
    const { sessionId } = useParams()
    const messagesEndRef = useRef<HTMLDivElement | null>(null)
    const [sessionData, setSessionData] = useState<ISession | undefined>(
        undefined
    )
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const fetchSessionData = async () => {
            if (!sessionId) {
                setError('No session ID provided')
                setIsLoading(false)
                return
            }

            try {
                setIsLoading(true)
                const session = await sessionService.getPublicSession(sessionId)
                setSessionData(session)

                // Fetch chat history
                const historyResponse =
                    await chatService.getPublicChatHistory(sessionId)

                // Convert ChatHistoryMessage[] to ChatMessage[] directly
                const messages: ChatMessage[] = (
                    historyResponse.messages ?? []
                ).map((historyMsg) => {
                    // Extract text content from parts
                    const textContent = historyMsg.content
                        .filter(
                            (
                                part
                            ): part is Extract<typeof part, { type: 'text' }> =>
                                part.type === 'text'
                        )
                        .map((part) => part.text)
                        .join('')

                    return {
                        id: historyMsg.id,
                        role: historyMsg.role,
                        content: textContent,
                        createdAt: historyMsg.created_at,
                        model: historyMsg.model,
                        parts: historyMsg.content,
                        files: historyMsg.files,
                        finish_reason: historyMsg.finish_reason
                    }
                })

                setMessages(messages)
                setError(null)
            } catch (err) {
                console.error('Error fetching session data:', err)
                setError('Failed to load conversation')
            } finally {
                setIsLoading(false)
            }
        }

        fetchSessionData()
    }, [sessionId])

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

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
    const externalImageUrls = useMemo((): ExternalImageUrl[] => {
        if (allToolResults.size === 0) return []

        const urls: ExternalImageUrl[] = []
        const googleStorageRegex =
            /https:\/\/storage\.googleapis\.com\/[^\s"'<>]+/g

        // Build a set of URLs already present in assistant messages to avoid duplicates
        const urlsInAssistantMessages = new Set<string>()
        const urlRegex = /https?:\/\/[^\s"'<>()]+/g
        messages.forEach((message) => {
            if (message.role === 'assistant') {
                // Check message content
                if (message.content) {
                    const matches = message.content.match(urlRegex)
                    if (matches) {
                        matches.forEach((url) =>
                            urlsInAssistantMessages.add(url)
                        )
                    }
                }
                // Check message parts for text content
                if (message.parts) {
                    message.parts.forEach((part) => {
                        if (part.type === 'text' && part.text) {
                            const matches = part.text.match(urlRegex)
                            if (matches) {
                                matches.forEach((url) =>
                                    urlsInAssistantMessages.add(url)
                                )
                            }
                        }
                    })
                }
            }
        })

        allToolResults.forEach((toolResult) => {
            if (toolResult.name === 'generate_image') {
                // Check in content field
                if (toolResult.content) {
                    const matches = toolResult.content.match(googleStorageRegex)
                    if (matches) {
                        matches.forEach((url) => {
                            const urlParts = url.split('/')
                            const fileName =
                                urlParts[urlParts.length - 1]?.split('?')[0] ||
                                'image'
                            urls.push({ url, name: fileName })
                        })
                    }
                }
                // Check in output.value field (can be a string or array of objects with url)
                if (toolResult.output?.value) {
                    const outputValue = toolResult.output.value
                    if (typeof outputValue === 'string') {
                        const matches = outputValue.match(googleStorageRegex)
                        if (matches) {
                            matches.forEach((url) => {
                                const urlParts = url.split('/')
                                const fileName =
                                    urlParts[urlParts.length - 1]?.split(
                                        '?'
                                    )[0] || 'image'
                                urls.push({ url, name: fileName })
                            })
                        }
                    } else if (Array.isArray(outputValue)) {
                        // Handle array of objects with url property
                        outputValue.forEach((item) => {
                            if (item.url?.includes('storage.googleapis.com')) {
                                const urlParts = item.url.split('/')
                                const fileName =
                                    urlParts[urlParts.length - 1]?.split(
                                        '?'
                                    )[0] || 'image'
                                urls.push({ url: item.url, name: fileName })
                            }
                        })
                    }
                }
            }
        })

        // Remove duplicates based on URL and filter out URLs already in assistant messages
        const uniqueUrls = urls.filter(
            (item, index, self) =>
                index === self.findIndex((t) => t.url === item.url) &&
                !urlsInAssistantMessages.has(item.url)
        )

        return uniqueUrls
    }, [allToolResults, messages])

    return (
        <div className="flex w-full h-screen">
            <div className="flex-1">
                <AgentHeader sessionData={sessionData} />
                <Sidebar className="block md:hidden" />
                <div
                    id="chat-wrapper"
                    className="flex justify-center h-[calc(100vh-53px)]"
                >
                    <div className="flex-1 flex flex-col max-w-4xl p-3 md:p-4">
                        <Conversation className="flex-1 share-conversation">
                            <ConversationContent className="p-0 md:p-2">
                                {isLoading && (
                                    <div className="flex items-center justify-center gap-2 py-12">
                                        <Loader size={20} />
                                        <span className="text-sm text-neutral-500">
                                            Loading conversation history&hellip;
                                        </span>
                                    </div>
                                )}
                                {error && (
                                    <div className="mb-4 rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500 dark:text-red-300">
                                        {error}
                                    </div>
                                )}
                                {!isLoading &&
                                    !error &&
                                    groupedMessages.length === 0 && (
                                        <div className="text-sm text-neutral-500 text-center py-12">
                                            No messages in this conversation.
                                        </div>
                                    )}

                                {groupedMessages.map((group, index) => {
                                    return (
                                        <ChatMessageContent
                                            key={index}
                                            group={group}
                                            isShareMode
                                            allToolResults={allToolResults}
                                            allGroups={groupedMessages}
                                            groupIndex={index}
                                            agentType={sessionData?.agent_type}
                                        />
                                    )
                                })}

                                {/* Show external images (Google Storage) at the end of chat */}
                                {externalImageUrls.length > 0 && (
                                    <DownloadFilesChat
                                        files={[]}
                                        sessionId={sessionId || ''}
                                        externalImageUrls={externalImageUrls}
                                    />
                                )}
                            </ConversationContent>
                            <ConversationScrollButton />
                        </Conversation>
                    </div>
                </div>
            </div>
        </div>
    )
}
