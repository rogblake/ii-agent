'use client'

import { Check, ChevronDown, ChevronRight, Copy, Folder } from 'lucide-react'
import { memo, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Action from './action'
import EditQuestion from './edit-question'
import AttachmentsList from './attachments-list'
import Markdown from '@/components/markdown'
import { ActionStep, BUILD_STEP, Message, TAB, TOOL } from '@/typings/agent'
import { Button } from '../ui/button'
import { ToolConfirmation } from './tool-confirmation'
import {
    setActiveTab,
    setSelectedBuildStep,
    useAppSelector,
    selectActiveSessionId,
    type AppDispatch
} from '@/state'
import { getFileIconAndColor } from '@/utils/file-utils'
import { SaveCheckpointPublish } from './save-checkpoint-publish'
import { chatService } from '@/services/chat.service'
import { SecretsInput } from './secrets-input'
import { SendUserFilesFork } from './send-user-files-fork'


interface MessageContentProps {
    message: Message
    isLatestUser: boolean
    editingMessage: Message | null | undefined
    workspaceInfo: string
    isThinkMessageExpanded: (id: string) => boolean
    toggleThinkMessage: (id: string) => void
    handleSetEditingMessage: (msg?: Message) => void
    handleEditMessage: (question: string) => void
    handleClickAction: (
        data: ActionStep | undefined,
        showTabOnly?: boolean
    ) => void
    dispatch: AppDispatch
    isReplayMode: boolean
    agentType?: string
}

const MessageContent = memo(
    ({
        message,
        editingMessage,
        workspaceInfo,
        isThinkMessageExpanded,
        toggleThinkMessage,
        handleSetEditingMessage,
        handleEditMessage,
        handleClickAction,
        dispatch,
        agentType
    }: MessageContentProps) => {
        const { t } = useTranslation()
        const [isCopied, setIsCopied] = useState(false)
        const [fetchedImageUrls, setFetchedImageUrls] = useState<
            Record<string, string>
        >({})
        const [failedImages, setFailedImages] = useState<
            Record<string, boolean>
        >({})
        const [loadingImages, setLoadingImages] = useState<
            Record<string, boolean>
        >({})
        const sessionId = useAppSelector(selectActiveSessionId)

        // Fetch images that don't have fileContents (e.g., after page reload)
        useEffect(() => {
            if (!message.files || !sessionId) return

            const fetchedUrls: string[] = []

            const fetchMissingImages = async () => {
                for (const file of message.files || []) {
                    const isImage =
                        file.file_name.match(
                            /\.(jpeg|jpg|gif|png|webp|svg|heic|heif|bmp)$/i
                        ) !== null
                    // HEIC files must always be fetched through the backend
                    // API which converts to JPEG, because browsers can't
                    // render HEIC and fileContents holds the raw GCS URL.
                    const isHeic = /\.(heic|heif)$/i.test(file.file_name)

                    // Skip if not an image, already have content, or already fetched
                    if (
                        !isImage ||
                        (!isHeic &&
                            message.fileContents &&
                            message.fileContents[file.file_name]) ||
                        fetchedImageUrls[file.id]
                    ) {
                        continue
                    }

                    // Set loading state
                    setLoadingImages((prev) => ({ ...prev, [file.id]: true }))

                    try {
                        const blob = await chatService.getFileContent({
                            fileId: file.id
                        })
                        const url = URL.createObjectURL(blob)
                        fetchedUrls.push(url)
                        setFetchedImageUrls((prev) => ({
                            ...prev,
                            [file.id]: url
                        }))
                    } catch (error) {
                        console.error(
                            `Error fetching image ${file.file_name}:`,
                            error
                        )
                    } finally {
                        setLoadingImages((prev) => ({
                            ...prev,
                            [file.id]: false
                        }))
                    }
                }
            }

            fetchMissingImages()

            // Cleanup function to revoke object URLs
            return () => {
                fetchedUrls.forEach((url) => {
                    URL.revokeObjectURL(url)
                })
            }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchedImageUrls
        // is intentionally excluded: including it causes an infinite loop because
        // setFetchedImageUrls inside the effect changes the reference each time.
        // The guard `fetchedImageUrls[file.id]` inside the loop prevents duplicates.
        }, [message.files, message.fileContents, sessionId])

        const handleCopyContent = async () => {
            try {
                await navigator.clipboard.writeText(message.content || '')
                setIsCopied(true)
                setTimeout(() => setIsCopied(false), 2000)
            } catch (err) {
                console.error('Failed to copy text:', err)
            }
        }

        // Memoize transformed markdown content to prevent unnecessary Markdown re-renders
        const transformedContent = useMemo(
            () =>
                message.content
                    ?.replace('<video>', '&lt;video&gt;')
                    ?.replace(/\n/g, '  \n'),
            [message.content]
        )

        const fileElements = useMemo(() => {
            if (!message.files || message.files.length === 0) return null

            // Process files logic (same as before but memoized)
            const folderFiles = message.files.filter((file) =>
                file.file_name.match(/^folder:(.+):(\d+)$/)
            )

            const folderNames = folderFiles
                .map((folderFile) => {
                    const match =
                        folderFile.file_name.match(/^folder:(.+):(\d+)$/)
                    return match ? match[1] : null
                })
                .filter(Boolean) as string[]

            const filesToDisplay = message.files.filter((file) => {
                if (file.file_name.match(/^folder:(.+):(\d+)$/)) {
                    return true
                }
                for (const folderName of folderNames) {
                    if (file.file_name.includes(folderName)) {
                        return false
                    }
                }
                return true
            })

            return filesToDisplay.map((file, fileIndex) => {
                const isFolderMatch =
                    file.file_name.match(/^folder:(.+):(\d+)$/)
                if (isFolderMatch) {
                    const folderName = isFolderMatch[1]
                    const fileCount = parseInt(isFolderMatch[2], 10)

                    return (
                        <div
                            key={`${message.id}-folder-${fileIndex}`}
                            className="inline-block ml-auto bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm"
                        >
                            <div className="flex items-center gap-3">
                                <div className="flex items-center justify-center w-12 h-12 bg-blue-600 rounded-xl">
                                    <Folder className="size-6 text-white" />
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-base font-medium">
                                        {folderName}
                                    </span>
                                    <span className="text-left text-sm text-gray-500">
                                        {fileCount}{' '}
                                        {fileCount === 1
                                            ? t('agent.messageContent.file')
                                            : t('agent.messageContent.files')}
                                    </span>
                                </div>
                            </div>
                        </div>
                    )
                }

                const isImage =
                    file.file_name.match(
                        /\.(jpeg|jpg|gif|png|webp|svg|heic|heif|bmp)$/i
                    ) !== null

                // Get image URL from fileContents (fresh upload) or fetchedImageUrls (after reload).
                // For HEIC files, prefer fetchedImageUrls because the backend
                // converts HEIC→JPEG; fileContents holds the raw GCS URL that
                // browsers cannot render.
                const isHeicFile = /\.(heic|heif)$/i.test(file.file_name)
                const imageUrl = isHeicFile
                    ? fetchedImageUrls[file.id]
                    : (message.fileContents &&
                          message.fileContents[file.file_name]) ||
                      fetchedImageUrls[file.id]
                const isLoading = loadingImages[file.id]

                if (isImage && imageUrl && !failedImages[file.id]) {
                    return (
                        <div
                            key={`${message.id}-file-${fileIndex}`}
                            className="inline-block ml-auto rounded-3xl overflow-hidden max-w-[320px]"
                        >
                            <div className="w-40 h-40 rounded-xl overflow-hidden">
                                <img
                                    src={imageUrl}
                                    alt={file.file_name}
                                    className="w-full h-full object-cover"
                                    loading="lazy"
                                    onError={() => setFailedImages((prev) => ({ ...prev, [file.id]: true }))}
                                />
                            </div>
                        </div>
                    )
                }

                // Show loading state for images being fetched
                if (isImage && isLoading) {
                    return (
                        <div
                            key={`${message.id}-file-${fileIndex}`}
                            className="inline-block ml-auto rounded-3xl overflow-hidden max-w-[320px]"
                        >
                            <div className="w-40 h-40 rounded-xl overflow-hidden bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                                <span className="text-gray-500 text-sm">
                                    {t('common.loading')}
                                </span>
                            </div>
                        </div>
                    )
                }

                const { IconComponent, bgColor, label } = getFileIconAndColor(
                    file.file_name
                )

                return (
                    <div
                        key={`${message.id}-file-${fileIndex}`}
                        className="inline-block ml-auto bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm"
                    >
                        <div className="flex items-center gap-3">
                            <div
                                className={`flex items-center justify-center w-12 h-12 ${bgColor} rounded-xl`}
                            >
                                <IconComponent className="size-6 text-white" />
                            </div>
                            <div className="flex flex-col">
                                <span className="text-base font-medium">
                                    {file.file_name}
                                </span>
                                <span className="text-left text-sm text-gray-500">
                                    {label}
                                </span>
                            </div>
                        </div>
                    </div>
                )
            })
        }, [
            message.files,
            message.fileContents,
            message.id,
            fetchedImageUrls,
            loadingImages,
            failedImages
        ])

        // Render video frames (for video generation)
        const videoFrameElements = useMemo(() => {
            if (!message.videoFrames || message.videoFrames.length === 0)
                return null

            return (
                <div className="flex flex-wrap items-center gap-2 justify-end">
                    {message.videoFrames.map((frame) => (
                        <div
                            key={frame.id}
                            className="relative inline-block rounded-xl overflow-hidden"
                        >
                            <div className="w-24 h-16 rounded-xl overflow-hidden border border-white/20">
                                <img
                                    src={frame.url}
                                    alt={`${frame.type} frame`}
                                    className="w-full h-full object-cover"
                                />
                            </div>
                            <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs px-1 py-0.5 text-center">
                                {frame.type === 'start'
                                    ? t('media.videoFrames.startLabel')
                                    : t('media.videoFrames.endLabel')}
                            </div>
                        </div>
                    ))}
                </div>
            )
        }, [message.videoFrames, t])

        return (
            <>
                {videoFrameElements && (
                    <div className="mb-2">{videoFrameElements}</div>
                )}
                {fileElements && (
                    <div className="flex flex-col gap-2 mb-2">
                        {fileElements}
                    </div>
                )}
                {message.content && (
                    <div
                        className={`inline-block text-left rounded-lg ${
                            message.role === 'user'
                                ? 'bg-[#f5f5f5] dark:bg-grey p-3 max-w-[80%] text-black whitespace-pre-wrap border border-grey dark:none'
                                : message.role === 'system'
                                  ? 'p-3 w-full text-gray-500 dark:text-gray-400'
                                  : 'text-white w-full'
                        } ${
                            editingMessage?.id === message.id
                                ? 'w-full max-w-none'
                                : ''
                        } ${
                            message.content?.startsWith('```Thinking:')
                                ? 'agent-thinking w-full'
                                : ''
                        }`}
                    >
                        {message.role === 'system' ? (
                            <div className="italic">
                                <Markdown>{message.content}</Markdown>
                            </div>
                        ) : message.role === 'user' ? (
                            <div>
                                {editingMessage?.id === message.id ? (
                                    <EditQuestion
                                        editingMessage={message.content}
                                        handleCancel={() =>
                                            handleSetEditingMessage(undefined)
                                        }
                                        handleEditMessage={handleEditMessage}
                                    />
                                ) : (
                                    <div className="relative group">
                                        <div className="text-left text-sm">
                                            {message.content}
                                        </div>
                                        <div className="flex items-center justify-end gap-1 absolute -right-4 -bottom-9">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-6 w-6 text-xs cursor-pointer text-white"
                                                onClick={handleCopyContent}
                                            >
                                                {isCopied ? (
                                                    <Check className="size-3" />
                                                ) : (
                                                    <Copy className="size-3" />
                                                )}
                                            </Button>
                                            {/* {isLatestUser && !isReplayMode && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 text-xs cursor-pointer hover:!bg-gray-200 dark:hover:!bg-gray-700"
                                                    onClick={() =>
                                                        handleSetEditingMessage(
                                                            message
                                                        )
                                                    }
                                                >
                                                    <Pencil className="size-3" />
                                                </Button>
                                            )} */}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : message?.isThinkMessage ? (
                            <div
                                className={`inline-flex flex-col bg-firefly/[0.18] dark:bg-sky-blue/[0.18] border border-grey rounded-xl overflow-hidden ${
                                    isThinkMessageExpanded(message.id)
                                        ? 'w-full'
                                        : ''
                                }`}
                            >
                                <button
                                    onClick={(e) => {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        toggleThinkMessage(message.id)
                                    }}
                                    className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                                >
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 bg-firefly dark:bg-sky-blue rounded-full"></div>
                                        <span className="font-medium text-sm text-gray-700 dark:text-gray-300">
                                            {t('agent.messageContent.thought')}
                                        </span>
                                    </div>
                                    {isThinkMessageExpanded(message.id) ? (
                                        <ChevronDown className="size-4 text-gray-500 dark:text-gray-400" />
                                    ) : (
                                        <ChevronRight className="size-4 text-gray-500 dark:text-gray-400" />
                                    )}
                                </button>
                                {isThinkMessageExpanded(message.id) && (
                                    <div className="px-4 pb-4">
                                        <Markdown>
                                            {transformedContent}
                                        </Markdown>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="relative group">
                                <Markdown>
                                    {transformedContent}
                                </Markdown>
                                <div className="absolute -bottom-1 right-0 flex items-center justify-end gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-6 w-6 text-xs cursor-pointer hover:!bg-gray-700/50 dark:hover:!bg-gray-600/50"
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
                        )}
                    </div>
                )}
                {message.action && (
                    <div className="mt-2 space-y-2">
                        <Action
                            workspaceInfo={workspaceInfo}
                            type={message.action.type}
                            value={message.action.data}
                            onClick={() => {
                                dispatch(setActiveTab(TAB.BUILD))
                                dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                                handleClickAction(message.action, true)
                            }}
                        />
                        {message.action.type === TOOL.SAVE_CHECKPOINT && (
                            <SaveCheckpointPublish
                                isResult={Boolean(message.action.data.isResult)}
                                result={message.action.data.result}
                            />
                        )}
                        {message.action.type === TOOL.SEND_USER_FILES && sessionId && (
                            <SendUserFilesFork
                                sessionId={sessionId}
                                attachments={message.action.data.tool_input?.attachments || []}
                                isResult={Boolean(message.action.data.isResult)}
                                agentType={agentType}
                            />
                        )}
                        {message.action.type === TOOL.ADD_USER_ENV && (
                            <SecretsInput
                                secrets={
                                   message.action.data.tool_input?.secrets || []
                                }
                                readOnly
                            />
                        )}
                    </div>
                )}
                <AttachmentsList attachments={message.attachments} />
                {message.toolConfirmation && (
                    <ToolConfirmation confirmation={message.toolConfirmation} />
                )}
            </>
        )
    },
    (prevProps, nextProps) => {
        return (
            prevProps.message.id === nextProps.message.id &&
            prevProps.message.content === nextProps.message.content &&
            prevProps.message.attachments === nextProps.message.attachments &&
            prevProps.message.action === nextProps.message.action &&
            prevProps.message.toolConfirmation === nextProps.message.toolConfirmation &&
            prevProps.isLatestUser === nextProps.isLatestUser &&
            prevProps.editingMessage?.id === nextProps.editingMessage?.id &&
            prevProps.isThinkMessageExpanded(prevProps.message.id) ===
                nextProps.isThinkMessageExpanded(nextProps.message.id)
        )
    }
)

MessageContent.displayName = 'MessageContent'

export default MessageContent
