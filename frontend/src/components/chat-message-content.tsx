import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ReactElement } from 'react'

import { BrainIcon, Check, CodeIcon, Copy, Pencil, X } from 'lucide-react'

import { MessageContent } from './ai-elements/message'
import DownloadFilesChat from './download-files-chat'
import { Button } from './ui/button'
import { ToolContentComponent } from './tool-content'
import { UploadedFilesDisplay } from './uploaded-files-display'
import { VideoFramesDisplay } from './video-frames-display'
import { StorybookThumbnail } from './ui/storybook-modal'
import {
    ChainOfThought,
    ChainOfThoughtContent,
    ChainOfThoughtHeader,
    ChainOfThoughtStep
} from '@/components/ai-elements/chain-of-thought'
import { Response } from '@/components/ai-elements/response'
import { CouncilResultDisplay } from '@/components/council/council-result-display'
import { type ChatMediaType } from '@/constants/media-type-config'
import { useMediaModels } from '@/hooks/use-media-models'
import {
    selectActiveSessionId,
    selectAvailableModels,
    selectChatMediaPreference,
    useAppSelector
} from '@/state'
import type { ContentPart, GroupedPart } from '@/utils/chat-events'
import {
    parseStorybookProgress,
    type StorybookProgressData
} from '@/utils/storybook-progress'

const isStorybookUrl = (url: string | undefined): boolean => {
    if (!url) return false
    return url.includes('/storybook/') || url.includes('storybook-scene')
}

// Return type that can be either legacy images or new storybook data
type StorybookData =
    | { format: 'legacy'; images: Array<{ url: string }> }
    | {
          format: 'new'
          storybookId: string
          storybookName: string
          images: Array<{ url: string }>
      }
    | null

const extractStorybookData = (
    allGroups: GroupedPart[],
    currentGroupIndex: number
): StorybookData => {
    // Find a nearby group that contains generate_storybook tool_call + tool_result.
    // Depending on hydration order, the tool group can be before or after the text group.
    const candidateIndexes = [
        currentGroupIndex - 1,
        currentGroupIndex + 1
    ].filter((index) => index >= 0 && index < allGroups.length)

    for (const candidateIndex of candidateIndexes) {
        const candidateGroup = allGroups[candidateIndex]
        const hasStorybookToolCall = candidateGroup.parts.some(
            (part) =>
                part.type === 'tool_call' && part.name === 'generate_storybook'
        )

        if (!hasStorybookToolCall) continue

        // Extract storybook data from tool results in the candidate group
        for (const part of candidateGroup.parts) {
            if (part.type !== 'tool_result') continue

            const output = part?.output

            // Check for new StorybookResultContent format (type === 'storybook')
            if (
                output?.type === 'storybook' &&
                output?.storybook_id &&
                output?.pages
            ) {
                const images = output.pages
                    .filter((p) => p.image_url)
                    .map((p) => ({ url: p.image_url }))
                return {
                    format: 'new',
                    storybookId: output.storybook_id,
                    storybookName: output.storybook_name || 'Storybook',
                    images
                }
            }

            // Check if value contains storybook data (JSON string parsed)
            const value = output?.value
            if (typeof value === 'string') {
                try {
                    const parsed = JSON.parse(value)
                    if (parsed?.type === 'storybook' && parsed?.storybook_id) {
                        const images = parsed.pages
                            .filter((p: any) => p.image_url)
                            .map((p: any) => ({ url: p.image_url }))
                        return {
                            format: 'new',
                            storybookId: parsed.storybook_id,
                            storybookName: parsed.storybook_name || 'Storybook',
                            images
                        }
                    }
                } catch {
                    // Not JSON, continue
                }
            }

            // Legacy format: array of image URLs
            if (Array.isArray(value)) {
                const hasStorybookPattern = value.some((item: any) =>
                    isStorybookUrl(item.url)
                )
                if (hasStorybookPattern) {
                    return {
                        format: 'legacy',
                        images: value.map((item: any) => ({
                            url: item.url as string
                        }))
                    }
                }
            }
        }
    }

    return null
}

const parseToolInput = (input?: string): any | null => {
    if (!input) return null
    try {
        return JSON.parse(input)
    } catch {
        return null
    }
}

const getStorybookExpectedTotalPages = (
    input?: string,
    fallbackPageCount?: number | 'unlimited'
): number | undefined => {
    const parsed = parseToolInput(input)
    if (parsed?.total_pages && typeof parsed.total_pages === 'number') {
        return parsed.total_pages
    }
    if (parsed?.totalPages && typeof parsed.totalPages === 'number') {
        return parsed.totalPages
    }
    if (parsed?.page_count && typeof parsed.page_count === 'number') {
        // page_count is content pages; +1 for cover page
        return parsed.page_count + 1
    }
    if (Array.isArray(parsed?.pages)) {
        return parsed.pages.length
    }
    if (Array.isArray(parsed?.scenes)) {
        return parsed.scenes.length
    }
    if (typeof fallbackPageCount === 'number') {
        return fallbackPageCount + 1
    }
    return undefined
}

const createStorybookProgressPlaceholder = (
    totalPages?: number
): StorybookProgressData => {
    const safeTotalPages =
        typeof totalPages === 'number' && totalPages > 0 ? totalPages : 0
    const pageSlots = Array.from({ length: safeTotalPages }, (_, i) => ({
        pageNumber: i + 1,
        imageUrl: null,
        isCompleted: false,
        isGenerating: safeTotalPages > 0 && i === 0
    }))

    return {
        storybookId: '',
        totalPages: safeTotalPages,
        completedPages: 0,
        progressPercent: 0,
        progressStatus: 'generating',
        pageSlots
    }
}

interface ChatMessageContentProps {
    group: GroupedPart
    isStreaming?: boolean
    isWaitingForNextEvent?: boolean
    isShareMode?: boolean
    allToolResults?: Map<string, ContentPart>
    allGroups?: GroupedPart[]
    groupIndex?: number
    agentType?: string
    editingMessageId?: string | null
    onEditStart?: (messageId: string) => void
    onEditSubmit?: (messageId: string, newContent: string) => void
    onEditCancel?: () => void
    chatStatus?: 'ready' | 'running'
}

function ChatMessageContent({
    group,
    isStreaming = false,
    isWaitingForNextEvent = false,
    isShareMode = false,
    allToolResults,
    allGroups,
    groupIndex,
    agentType,
    editingMessageId,
    onEditStart,
    onEditSubmit,
    onEditCancel,
    chatStatus
}: ChatMessageContentProps): ReactElement | null {
    const { t } = useTranslation()
    const [isCopied, setIsCopied] = useState(false)
    const availableModels = useAppSelector(selectAvailableModels)
    const sessionId = useAppSelector(selectActiveSessionId)
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const { allMediaModels } = useMediaModels()

    async function handleCopyContent(): Promise<void> {
        const textContent = group.parts
            .filter((part) => part.type === 'text')
            .map((part) => part.text)
            .join('')

        if (textContent) {
            await navigator.clipboard.writeText(textContent)
            setIsCopied(true)
            setTimeout(() => setIsCopied(false), 2000)
        }
    }

    // Edit message support
    const messageId = group.parts[0]?.message_id
    const isEditing = Boolean(
        editingMessageId && messageId && editingMessageId === messageId
    )
    const [editText, setEditText] = useState('')
    const editTextareaRef = useRef<HTMLTextAreaElement>(null)

    useEffect(() => {
        if (isEditing && editTextareaRef.current) {
            const textarea = editTextareaRef.current
            textarea.focus()
            textarea.setSelectionRange(textarea.value.length, textarea.value.length)
        }
    }, [isEditing])

    const handleEditStart = useCallback(() => {
        if (!messageId || !onEditStart) return
        const textContent = group.parts
            .filter((part) => part.type === 'text')
            .map((part) => part.text)
            .join('')
        setEditText(textContent)
        onEditStart(messageId)
    }, [messageId, onEditStart, group.parts])

    const handleEditSubmit = useCallback(() => {
        if (!messageId || !onEditSubmit) return
        const trimmed = editText.trim()
        if (!trimmed) return
        onEditSubmit(messageId, trimmed)
    }, [messageId, onEditSubmit, editText])

    const handleEditCancel = useCallback(() => {
        setEditText('')
        onEditCancel?.()
    }, [onEditCancel])

    const handleEditKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleEditSubmit()
            }
            if (e.key === 'Escape') {
                handleEditCancel()
            }
        },
        [handleEditSubmit, handleEditCancel]
    )

    // Helper function to find matching tool_result for a tool_call with O(1) lookup
    // Uses allToolResults (from parent) if available, otherwise falls back to searching within group
    const findToolResult = useCallback(
        (toolCallId: string): ContentPart | undefined => {
            // First check allToolResults (passed from parent, contains all tool results across messages)
            if (allToolResults) {
                return allToolResults.get(toolCallId)
            }
            // Fallback: search within current group parts
            return group.parts.find(
                (part) =>
                    part.type === 'tool_result' &&
                    part.tool_call_id === toolCallId
            )
        },
        [allToolResults, group.parts]
    )

    // Don't render if group has no parts
    if (!group.parts || group.parts.length === 0) {
        return null
    }

    // Extract metadata from the first part (all parts from the same message have same metadata)
    const firstPart = group.parts[0]
    const role = firstPart?.role || 'assistant'

    // Only allow editing text-only user messages with real backend UUIDs.
    // Messages with file attachments or media metadata are excluded because
    // the edit flow only preserves text content.
    const hasBackendId = Boolean(messageId && !messageId.startsWith('user-'))
    const hasAttachments = Boolean(
        group.files?.length || group.videoFrames?.length
    )
    const hasMediaMetadata = Boolean(group.metadata?.media?.type)
    const canEdit =
        role === 'user' &&
        chatStatus !== 'running' &&
        !isShareMode &&
        Boolean(onEditStart) &&
        hasBackendId &&
        !hasAttachments &&
        !hasMediaMetadata

    const llmModelLabel = firstPart?.model
        ? availableModels
              .find((m) => m.id === firstPart.model)
              ?.model?.split('@')?.[0]
        : undefined

    const toolCallMediaOverride = useMemo(() => {
        const toolCall = group.parts.find(
            (part) =>
                part.type === 'tool_call' &&
                (part.name === 'generate_image' ||
                    part.name === 'generate_storybook' ||
                    part.name === 'generate_video')
        )
        if (!toolCall) return null
        const parsed = parseToolInput(toolCall.input)
        const rawModelKey =
            parsed?.model_name ??
            parsed?.model ??
            parsed?.model_id ??
            parsed?.modelId ??
            parsed?.modelName
        const modelKey =
            typeof rawModelKey === 'string' && rawModelKey.trim().length > 0
                ? rawModelKey
                : undefined
        const modelType: ChatMediaType | undefined =
            toolCall.name === 'generate_video'
                ? 'video'
                : toolCall.name === 'generate_storybook'
                  ? 'storybook'
                  : undefined
        return { modelKey, modelType }
    }, [group.parts])

    // Determine chat media metadata (prefer matching type, fallback to the latest prior user message)
    const directMediaMetadataRaw =
        firstPart?.message_metadata?.media ?? group.metadata?.media
    const resolvedMediaMetadata = useMemo(() => {
        const preferredType = toolCallMediaOverride?.modelType
        const directType = directMediaMetadataRaw?.type as
            | ChatMediaType
            | undefined

        if (
            directMediaMetadataRaw &&
            (!preferredType || directType === preferredType)
        ) {
            return directMediaMetadataRaw
        }

        if (!allGroups || groupIndex === undefined) {
            return directMediaMetadataRaw ?? undefined
        }

        let fallback:
            | NonNullable<GroupedPart['metadata']>['media']
            | undefined = directMediaMetadataRaw ?? undefined
        let typedFallback:
            | NonNullable<GroupedPart['metadata']>['media']
            | undefined

        for (let i = groupIndex - 1; i >= 0; i -= 1) {
            const candidate = allGroups[i]
            const candidateMedia =
                candidate?.parts?.[0]?.message_metadata?.media ??
                candidate?.metadata?.media
            if (!candidateMedia) continue

            const candidateRole = candidate.parts?.[0]?.role
            const candidateType = candidateMedia.type as
                | ChatMediaType
                | undefined

            if (preferredType && candidateType === preferredType) {
                if (candidateRole === 'user') return candidateMedia
                if (!typedFallback) typedFallback = candidateMedia
                continue
            }

            if (!preferredType) {
                if (candidateRole === 'user') return candidateMedia
                if (!fallback) fallback = candidateMedia
            } else if (!fallback) {
                fallback = candidateMedia
            }
        }
        return typedFallback ?? fallback
    }, [allGroups, directMediaMetadataRaw, groupIndex, toolCallMediaOverride])

    const mediaMetadata = resolvedMediaMetadata
    const metadataModelName = mediaMetadata?.model_name
    const effectiveModelName =
        toolCallMediaOverride?.modelKey ?? metadataModelName
    const effectiveType: ChatMediaType | undefined =
        toolCallMediaOverride?.modelType ??
        (mediaMetadata?.type as ChatMediaType | undefined) ??
        (toolCallMediaOverride ? 'image' : undefined)
    const isMediaMode = Boolean(
        effectiveModelName ??
            toolCallMediaOverride?.modelType ??
            mediaMetadata?.enabled ??
            mediaMetadata
    )
    const mediaModel =
        isMediaMode && effectiveModelName
            ? allMediaModels.find(
                  (model) =>
                      model.model_name === effectiveModelName ||
                      model.id === effectiveModelName
              )
            : undefined
    const mediaModelLabel =
        isMediaMode && effectiveModelName
            ? allMediaModels.find(
                  (model) =>
                      model.model_name === effectiveModelName ||
                      model.id === effectiveModelName
              )?.label || effectiveModelName
            : undefined
    const chatMediaMetadata =
        isMediaMode && effectiveModelName
            ? {
                  modelName: mediaModelLabel || effectiveModelName,
                  modelType: effectiveType,
                  modelId:
                      mediaModel?.model_name ??
                      mediaModel?.id ??
                      effectiveModelName
              }
            : undefined

    if (role === 'tool') return null

    return (
        <div
            className={`rounded-lg text-base ${
                role === 'user'
                    ? 'flex flex-col items-end justify-end gap-2'
                    : role === 'system'
                      ? 'p-3 border italic w-full text-gray-500 dark:text-gray-400'
                      : 'text-white w-full'
            }`}
        >
            {role === 'user' ? (
                <>
                    <VideoFramesDisplay
                        frames={group.videoFrames}
                        className="mb-2"
                    />
                    <UploadedFilesDisplay
                        files={group.files}
                        fileContents={group.fileContents}
                        sessionId={sessionId || undefined}
                        isShareMode={isShareMode}
                    />
                    {(() => {
                        const textContent = group.parts
                            .filter((part) => part.type === 'text')
                            .map((part) => part.text)
                            .join('')
                            .trim()

                        // Don't render text bubble if content is empty or "generate an image using minitools" (mini_tools case)
                        if (
                            !textContent ||
                            textContent.toLowerCase() ===
                                'generate an image using minitools'
                        )
                            return null

                        if (isEditing) {
                            return (
                                <div className="mb-6 w-full max-w-[80%]">
                                    <textarea
                                        ref={editTextareaRef}
                                        value={editText}
                                        onChange={(e) =>
                                            setEditText(e.target.value)
                                        }
                                        onKeyDown={handleEditKeyDown}
                                        className="w-full min-h-[80px] rounded-lg p-3 text-black dark:text-white bg-[#f5f5f5] dark:bg-grey border border-primary resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                                        rows={Math.min(
                                            editText.split('\n').length + 1,
                                            10
                                        )}
                                    />
                                    <div className="flex items-center justify-end gap-2 mt-2">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-7 px-3 text-xs cursor-pointer"
                                            onClick={handleEditCancel}
                                        >
                                            <X className="size-3 mr-1" />
                                            {t('common.cancel', 'Cancel')}
                                        </Button>
                                        <Button
                                            variant="default"
                                            size="sm"
                                            className="h-7 px-3 text-xs cursor-pointer"
                                            onClick={handleEditSubmit}
                                            disabled={!editText.trim()}
                                        >
                                            {t('common.submit', 'Submit')}
                                        </Button>
                                    </div>
                                </div>
                            )
                        }

                        return (
                            <div className="mb-6 relative w-fit bg-[#f5f5f5] dark:bg-grey rounded-lg p-3 max-w-[80%] text-black whitespace-pre-wrap border border-grey dark:none">
                                <div className="break-word-legacy">
                                    {textContent}
                                </div>
                                <div className="absolute flex items-center justify-end gap-2 -bottom-6 right-0 text-grey-6 dark:text-grey-2">
                                    <span className="text-xs w-max">
                                        {llmModelLabel || ''}
                                    </span>
                                    {canEdit && (
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="size-3 text-[10px] cursor-pointer"
                                            onClick={handleEditStart}
                                        >
                                            <Pencil className="size-3" />
                                        </Button>
                                    )}
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="size-3 text-[10px] cursor-pointer"
                                        onClick={handleCopyContent}
                                    >
                                        {isCopied ? (
                                            <Check className="size-3" />
                                        ) : (
                                            <Copy className="size-3" />
                                        )}
                                    </Button>
                                </div>
                            </div>
                        )
                    })()}
                </>
            ) : (
                <MessageContent variant="flat" className="p-0">
                    {(() => {
                        const councilParts = group.parts.filter(
                            (p) =>
                                p.type === 'council_member_output' ||
                                p.type === 'council_synthesis'
                        )
                        if (councilParts.length > 0) {
                            return (
                                <CouncilResultDisplay parts={councilParts} />
                            )
                        }
                        return null
                    })()}
                    {(() => {
                        const chainParts = group.parts
                        const hasCouncilParts = chainParts.some(
                            (part) =>
                                part.type === 'council_member_output' ||
                                part.type === 'council_synthesis'
                        )
                        if (hasCouncilParts) return null
                        const hasTextPart = chainParts.some(
                            (part) => part.type === 'text'
                        )
                        const isLastOfTurn = chainParts.some(
                            (part) => part.isLastOfTurn
                        )
                        const hasGenerateImageToolCall = chainParts.some(
                            (part) =>
                                part.type === 'tool_call' &&
                                part.name === 'generate_image'
                        )
                        const hasGenerateStorybookToolCall = chainParts.some(
                            (part) =>
                                part.type === 'tool_call' &&
                                part.name === 'generate_storybook'
                        )
                        const hasGenerateVideoToolCall = chainParts.some(
                            (part) =>
                                part.type === 'tool_call' &&
                                part.name === 'generate_video'
                        )

                        const shouldRenderChainOfThought =
                            !hasTextPart ||
                            ((effectiveType === 'infographic' ||
                                effectiveType === 'poster') &&
                                hasGenerateImageToolCall)

                        let textBlock: ReactElement | null = null

                        if (hasTextPart) {
                            // Render text directly
                            const textContent = chainParts
                                .filter((part) => part.type === 'text')
                                .map((part) => part.text)
                                .join('')

                            textBlock = (
                                <div className="group mb-4">
                                    <Response>{textContent}</Response>
                                    {isLastOfTurn && (
                                        <DownloadFilesChat
                                            files={group.files || []}
                                            sessionId={sessionId || ''}
                                        />
                                    )}
                                    {isLastOfTurn && !isStreaming && (
                                        <div className="flex items-center justify-start gap-1 mt-2">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="size-3 p-0 text-xs cursor-pointer hover:!bg-gray-700/50 dark:hover:!bg-gray-600/50"
                                                onClick={handleCopyContent}
                                            >
                                                {isCopied ? (
                                                    <Check className="size-3" />
                                                ) : (
                                                    <Copy className="size-3" />
                                                )}
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            )

                            if (!shouldRenderChainOfThought) {
                                return textBlock
                            }
                        }

                        // Extract storybook progress data
                        let storybookProgressData = null
                        let storybookResultData: StorybookData = null
                        let isStorybookToolResultError = false
                        if (hasGenerateStorybookToolCall) {
                            const storybookToolCall = chainParts.find(
                                (part) =>
                                    part.type === 'tool_call' &&
                                    part.name === 'generate_storybook'
                            )
                            if (storybookToolCall) {
                                const toolResult = findToolResult(
                                    storybookToolCall.id || ''
                                )
                                if (toolResult?.is_error) {
                                    isStorybookToolResultError = true
                                }
                                const rawContent =
                                    toolResult?.output ?? toolResult?.content
                                let content: any = rawContent ?? {}
                                if (typeof rawContent === 'string') {
                                    try {
                                        content = JSON.parse(rawContent)
                                    } catch {
                                        content = {}
                                    }
                                }
                                const progressData =
                                    parseStorybookProgress(content)
                                if (progressData) {
                                    const generatingPages =
                                        content?.generating_pages || []
                                    storybookProgressData = {
                                        ...progressData,
                                        generatingPages
                                    }
                                }

                                const result = content?.value
                                const storybookData =
                                    content?.type === 'storybook'
                                        ? content
                                        : result?.type === 'storybook'
                                          ? result
                                          : null

                                if (
                                    storybookData?.storybook_id &&
                                    Array.isArray(storybookData.pages)
                                ) {
                                    const images = storybookData.pages
                                        .filter((p: any) => p.image_url)
                                        .map((p: any) => ({ url: p.image_url }))
                                    storybookResultData = {
                                        format: 'new',
                                        storybookId: storybookData.storybook_id,
                                        storybookName:
                                            storybookData.storybook_name ||
                                            'Storybook',
                                        images
                                    }
                                }
                            }
                        }

                        // When the tool result is an error (e.g. cancelled),
                        // show a "failed" progress state instead of a generating placeholder.
                        const storybookPlaceholderData =
                            !storybookProgressData &&
                            hasGenerateStorybookToolCall &&
                            !storybookResultData
                                ? (() => {
                                      const expectedTotalPages =
                                          getStorybookExpectedTotalPages(
                                              chainParts.find(
                                                  (part) =>
                                                      part.type ===
                                                          'tool_call' &&
                                                      part.name ===
                                                          'generate_storybook'
                                              )?.input,
                                              chatMediaPreference.page_count
                                          )
                                      if (isStorybookToolResultError) {
                                          const safeTotalPages =
                                              typeof expectedTotalPages === 'number' && expectedTotalPages > 0
                                                  ? expectedTotalPages
                                                  : 0
                                          return {
                                              storybookId: '',
                                              totalPages: safeTotalPages,
                                              completedPages: 0,
                                              progressPercent: 0,
                                              progressStatus: 'failed',
                                              errorMessage: 'storybook_cancelled',
                                              pageSlots: Array.from({ length: safeTotalPages }, (_, i) => ({
                                                  pageNumber: i + 1,
                                                  imageUrl: null,
                                                  isCompleted: false,
                                                  isGenerating: false,
                                              })),
                                              generatingPages: [] as number[],
                                          }
                                      }
                                      const placeholder =
                                          createStorybookProgressPlaceholder(
                                              expectedTotalPages
                                          )
                                      return {
                                          ...placeholder,
                                          generatingPages:
                                              placeholder.totalPages > 0
                                                  ? [1]
                                                  : []
                                      }
                                  })()
                                : null

                        const storybookProgressDisplayData =
                            storybookProgressData || storybookPlaceholderData

                        const storybookResultId =
                            storybookResultData?.format === 'new'
                                ? storybookResultData.storybookId
                                : null

                        const hasStorybookPreviewLater =
                            storybookResultId &&
                            allGroups &&
                            groupIndex !== undefined
                                ? allGroups
                                      .slice(groupIndex + 1)
                                      .some((_, offset) => {
                                          const candidateGroup =
                                              allGroups[groupIndex + 1 + offset]
                                          if (
                                              candidateGroup.parts.some(
                                                  (part) => part.type === 'text'
                                              )
                                          ) {
                                              return false
                                          }
                                          const data = extractStorybookData(
                                              allGroups,
                                              groupIndex + 1 + offset
                                          )
                                          if (!data) return false
                                          if (data.format === 'new') {
                                              return (
                                                  data.storybookId ===
                                                  storybookResultId
                                              )
                                          }
                                          return true
                                      })
                                : false

                        const standaloneStorybook =
                            storybookResultData &&
                            storybookResultData.images.length > 0 &&
                            !hasStorybookPreviewLater
                                ? storybookResultData
                                : null

                        const standaloneStorybookId =
                            standaloneStorybook?.format === 'new'
                                ? standaloneStorybook.storybookId
                                : undefined

                        return (
                            <>
                                {textBlock}
                                <ChainOfThought
                                    isStreaming={isStreaming}
                                    className="mb-4"
                                >
                                    <ChainOfThoughtHeader
                                        chatMediaMetadata={
                                            chatMediaMetadata || undefined
                                        }
                                        hasGenerateImageToolCall={
                                            hasGenerateImageToolCall
                                        }
                                        hasGenerateStorybookToolCall={
                                            hasGenerateStorybookToolCall
                                        }
                                        hasGenerateVideoToolCall={
                                            hasGenerateVideoToolCall
                                        }
                                        storybookProgressData={
                                            storybookProgressDisplayData
                                        }
                                        isStorybookCompleted={
                                            !!storybookResultData
                                        }
                                    />
                                    <ChainOfThoughtContent>
                                        {chainParts.map((part, partIndex) => {
                                            if (part.type === 'reasoning') {
                                                const reasoningPart = part as {
                                                    type: 'reasoning'
                                                    id?: string
                                                    thinking?: string
                                                    started_at?: number | null
                                                    finished_at?: number | null
                                                    stream_active?: boolean
                                                }

                                                const isThisPartStreaming =
                                                    reasoningPart.stream_active ===
                                                    true

                                                let duration: number | undefined
                                                if (
                                                    reasoningPart.started_at &&
                                                    reasoningPart.finished_at
                                                ) {
                                                    duration = Math.ceil(
                                                        (reasoningPart.finished_at -
                                                            reasoningPart.started_at) /
                                                            1000
                                                    )
                                                }

                                                return (
                                                    <ChainOfThoughtStep
                                                        key={
                                                            reasoningPart.id ??
                                                            partIndex
                                                        }
                                                        icon={BrainIcon}
                                                        label={
                                                            isThisPartStreaming
                                                                ? t(
                                                                      'chain.thinking.streaming'
                                                                  )
                                                                : duration
                                                                  ? t(
                                                                        'chain.thinking.completeWithDuration',
                                                                        {
                                                                            seconds:
                                                                                duration
                                                                        }
                                                                    )
                                                                  : t(
                                                                        'chain.thinking.complete'
                                                                    )
                                                        }
                                                        status={
                                                            isThisPartStreaming
                                                                ? 'active'
                                                                : 'complete'
                                                        }
                                                    >
                                                        <Response className="text-black/56 dark:text-grey-2">
                                                            {reasoningPart.thinking ||
                                                                ''}
                                                        </Response>
                                                    </ChainOfThoughtStep>
                                                )
                                            }
                                            if (part.type === 'tool_call') {
                                                const toolResult =
                                                    findToolResult(
                                                        part.id || ''
                                                    )

                                                return (
                                                    <ToolContentComponent
                                                        key={partIndex}
                                                        toolCall={part}
                                                        toolResult={toolResult}
                                                        sessionId={
                                                            sessionId ||
                                                            undefined
                                                        }
                                                        agentType={agentType}
                                                        isShareMode={
                                                            isShareMode
                                                        }
                                                        mediaType={effectiveType}
                                                    />
                                                )
                                            }

                                            if (part.type === 'code_block') {
                                                return (
                                                    <ChainOfThoughtStep
                                                        key={
                                                            part.id ?? partIndex
                                                        }
                                                        icon={CodeIcon}
                                                        label={t(
                                                            'chain.codeInterpreter'
                                                        )}
                                                        status={'complete'}
                                                    >
                                                        <Response
                                                            key={`code-block-${part.id}`}
                                                        >
                                                            {`\`\`\`python\n${part.content}\n\`\`\``}
                                                        </Response>
                                                    </ChainOfThoughtStep>
                                                )
                                            }
                                            return null
                                        })}
                                        {isWaitingForNextEvent && (
                                            <ChainOfThoughtStep
                                                icon={BrainIcon}
                                                label={t(
                                                    'chain.thinking.streaming'
                                                )}
                                                status="active"
                                            />
                                        )}
                                    </ChainOfThoughtContent>
                                </ChainOfThought>
                                {standaloneStorybook ? (
                                    <StorybookThumbnail
                                        images={standaloneStorybook.images}
                                        storybookId={standaloneStorybookId}
                                        isShareMode={isShareMode}
                                    />
                                ) : null}
                            </>
                        )
                    })()}
                </MessageContent>
            )}
        </div>
    )
}

export default ChatMessageContent
