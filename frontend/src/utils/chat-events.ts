import { FinishReason } from '@/typings/chat'
import type { ChatMediaType } from '@/constants/media-type-config'
import type { VideoFrameReference } from '@/typings/agent'
import reverse from 'lodash/reverse'

export type AgentStatusState = 'ready' | 'running'

export type FileMetadata = {
    id: string
    file_name: string
    file_size: number
    content_type: string
    created_at: string
}

export type ChatMessage = {
    id: string
    role: 'user' | 'assistant' | 'system' | 'tool'
    content: string
    model: string
    createdAt?: string
    isError?: boolean
    files?: FileMetadata[]
    fileContents?: Record<string, string>
    videoFrames?: VideoFrameReference[]
    parts?: ContentPart[]
    finish_reason?: FinishReason | null
    metadata?: {
        media?: {
            enabled?: boolean
            type?: ChatMediaType
            model_name?: string
            provider?: string
            [key: string]: unknown
        }
        [key: string]: unknown
    }
}

export type ContentPart = {
    message_id?: string
    message_metadata?: ChatMessage['metadata']
    role?: 'user' | 'assistant' | 'system' | 'tool'
    model?: string
    createdAt?: string
    id?: string
    text?: string
    type: string
    thinking?: string
    signature?: string
    started_at?: number | null
    finished_at?: number | null
    stream_active?: boolean
    tool_call_id?: string
    name?: string
    input?: string
    finished?: boolean
    finish_reason?: FinishReason | null
    content?: string
    output?: {
        type: string
        value?: string | { url: string }[]
        // Storybook result/progress fields
        storybook_id?: string
        storybook_name?: string
        version?: number
        aspect_ratio?: string
        resolution?: string
        // All completed pages (used in both result and progress)
        pages?: Array<{
            page_number: number
            image_url: string
            text_content?: string
            text_position?: string
            html_content?: string
        }>
        // Storybook progress-specific fields
        total_pages?: number
        completed_pages?: number
        current_page?: number
        status?: 'generating' | 'completed' | 'failed'
        // Latest completed page (for incremental updates)
        page?: {
            page_number: number
            image_url: string
            text_content?: string
            text_position?: string
        }
        error_message?: string
        // Pages currently being generated in parallel
        generating_pages?: number[]
        polling?: boolean
    }
    metadata?: string
    is_error?: boolean
    files?: FileMetadata[]
    isLastOfTurn?: boolean
    // Council-specific fields
    model_id?: string
    model_name?: string
    status?: string
    error_message?: string
    synthesis_model_id?: string
}

export type GroupedPart = {
    parts: ContentPart[]
    files?: FileMetadata[]
    fileContents?: Record<string, string>
    videoFrames?: VideoFrameReference[]
    metadata?: ChatMessage['metadata']
}

export function groupMessageParts(allMessages: ChatMessage[]): GroupedPart[] {
    // Step 1: Create a map to track message metadata (files, fileContents, videoFrames)
    const messageMetadataMap = new Map<
        string,
        {
            files?: FileMetadata[]
            fileContents?: Record<string, string>
            videoFrames?: VideoFrameReference[]
            metadata?: ChatMessage['metadata']
        }
    >()
    allMessages.forEach((message) => {
        messageMetadataMap.set(message.id, {
            files: message.files,
            fileContents: message.fileContents,
            videoFrames: message.videoFrames,
            metadata: message.metadata
        })
    })

    // Step 2: Merge all parts from message into a single array
    const allPartsFromMessage: ContentPart[] = allMessages
        .map((message) => {
            // If message has parts, use them
            if (message.parts && message.parts.length > 0) {
                return message.parts.map(
                    (part, index) =>
                        ({
                            ...part,
                            message_id: message.id,
                            message_metadata: message.metadata,
                            role: message.role,
                            model: message.model,
                            createdAt: message.createdAt,
                            isLastOfTurn:
                                index === (message.parts?.length || 0) - 1,
                            finish_reason: message.finish_reason
                        }) as ContentPart
                )
            }

            // If message has content but no parts, create a text part from content
            if (message.content) {
                return [
                    {
                        type: 'text',
                        text: message.content,
                        message_id: message.id,
                        message_metadata: message.metadata,
                        role: message.role,
                        model: message.model,
                        createdAt: message.createdAt,
                        finish_reason: message.finish_reason
                        // files: message.files
                    } as ContentPart
                ]
            }

            // No parts and no content
            return []
        })
        .flat()

    // Step 3: Group parts - when encountering 'text', start a new group; otherwise add to latest group
    const reversedParts = reverse(allPartsFromMessage)
    const groups: GroupedPart[] = []
    for (const part of reversedParts) {
        const messageExtras =
            messageMetadataMap.get(part.message_id || '') || {}

        if (part.type === 'text') {
            // Get metadata from the message this part belongs to
            groups.push(
                { parts: [part], ...messageExtras },
                { parts: [], ...messageExtras }
            )
        } else {
            // Ensure there's at least one group to add to
            if (groups.length === 0) {
                groups.push({ parts: [], ...messageExtras })
            }

            const targetGroup = groups[groups.length - 1]
            if (!targetGroup.metadata && messageExtras.metadata) {
                targetGroup.metadata = messageExtras.metadata
            }
            if (!targetGroup.files && messageExtras.files) {
                targetGroup.files = messageExtras.files
            }
            if (!targetGroup.fileContents && messageExtras.fileContents) {
                targetGroup.fileContents = messageExtras.fileContents
            }

            targetGroup.parts.push(part)
        }
    }

    return reverse(groups?.filter((group) => group.parts.length > 0))?.map(
        (group) => ({
            ...group,
            parts: reverse(group.parts)
        })
    )
}
