import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ReactElement } from 'react'
import type { LucideIcon } from 'lucide-react'

import {
    AlertCircleIcon,
    BookOpenIcon,
    CodeIcon,
    GlobeIcon,
    ImageIcon,
    SearchIcon,
    WrenchIcon,
    PaperclipIcon,
    FileIcon,
    VideoIcon
} from 'lucide-react'

import { Shimmer } from './ai-elements/shimmer'
import {
    ChainOfThoughtSearchResult,
    ChainOfThoughtSearchResults,
    ChainOfThoughtStep
} from '@/components/ai-elements/chain-of-thought'
import { Response } from '@/components/ai-elements/response'
import { ToolInput } from '@/components/ai-elements/tool'
import { ClickableImage } from '@/components/ui/fullscreen-image-modal'
import { StorybookProgressUI } from '@/components/storybook-progress-ui'
import { StorybookThumbnail } from '@/components/ui/storybook-modal'
import { Button } from '@/components/ui/button'
import { ForkSessionDialog } from '@/components/fork-session-dialog'
import { parseJson } from '@/lib/utils'
import type { ContentPart } from '@/utils/chat-events'
import type { ChatMediaType } from '@/constants/media-type-config'
import { parseJSON } from '@/utils/string'
import { parseStorybookProgress } from '@/utils/storybook-progress'
import type { ForkType } from '@/typings/session'


const getToolIcon = (toolName: string): LucideIcon => {
    const TOOL_ICONS: Record<string, LucideIcon> = {
        web_search: SearchIcon,
        web_visit: GlobeIcon,
        image_search: ImageIcon,
        generate_image: ImageIcon,
        generate_storybook: BookOpenIcon,
        code_interpreter: CodeIcon,
        code_execution: CodeIcon,
        send_user_files: PaperclipIcon,
        generate_video: VideoIcon
    }
    return TOOL_ICONS[toolName] ?? WrenchIcon
}

interface ToolContentComponentProps {
    toolCall: ContentPart
    toolResult?: ContentPart
    sessionId?: string
    agentType?: string
    isShareMode?: boolean
    mediaType?: ChatMediaType
}

export function ToolContentComponent({
    toolCall,
    toolResult,
    sessionId,
    agentType: _agentType,
    isShareMode = false,
    mediaType
}: ToolContentComponentProps): ReactElement {
    const { t } = useTranslation()
    const [showForkDialog, setShowForkDialog] = useState(false)
    const [forkType, setForkType] = useState<ForkType>('research_to_website')
    const parsedInput = useMemo(() => {
        if (!toolCall.input) return {}
        try {
            return parseJSON(toolCall.input)
        } catch {
            return {}
        }
    }, [toolCall.input])

    const status = toolResult ? 'complete' : 'active'

    const icon = toolResult?.is_error
        ? AlertCircleIcon
        : getToolIcon(toolCall.name || '')

    const label = useMemo(() => {
        const toolName = toolCall.name || ''
        const query = String(parsedInput?.query ?? '')
        const url = String(parsedInput?.url ?? '')

        switch (toolName) {
            case 'web_search':
                return t('tools.labels.webSearch', { query })
            case 'web_visit':
                return t('tools.labels.webVisit', { url })
            case 'image_search':
                return t('tools.labels.imageSearch', { query })
            case 'generate_image':
                return mediaType === 'infographic'
                    ? t('tools.labels.generateInfographic')
                    : mediaType === 'poster'
                      ? t('tools.labels.generatePoster')
                      : t('tools.labels.generateImage')
            case 'send_user_files':
                    return t('tools.labels.sendUserFiles')
            case 'generate_storybook':
                return t('tools.labels.generateStorybook')
            case 'generate_video':
                return t('tools.labels.generateVideo')
            default:
                return t('tools.labels.generic', { toolName })
        }
    }, [toolCall.name, parsedInput, t, mediaType])

    const output = useMemo(() => {
        const content =
            toolResult?.output || parseJSON(toolResult?.content || '')
        const result = content?.value

        if (toolCall.name === 'web_search') {
            if (!result) return null
            const search_results = parseJson(result)

            return (
                <ChainOfThoughtSearchResults>
                    {Array.isArray(search_results) &&
                        search_results?.map((item, index) => (
                            <ChainOfThoughtSearchResult key={index}>
                                <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:underline"
                                >
                                    {item.title || new URL(item.url).hostname}
                                </a>
                            </ChainOfThoughtSearchResult>
                        ))}
                </ChainOfThoughtSearchResults>
            )
        }
        if (toolCall.name === 'web_visit') {
            if (!result) return null
            return (
                <Response className="text-black/56 dark:text-grey-2">
                    {result?.substring(0, 400)}
                </Response>
            )
        }
        if (toolCall.name === 'image_search') {
            if (!result) return null
            const search_results = parseJson(result)
            return (
                <div className="flex flex-wrap gap-2">
                    {Array.isArray(search_results) &&
                        search_results?.map((item, index) => (
                            <img
                                key={index}
                                src={item.image_url}
                                alt={t('tools.imageAlt', { index: index + 1 })}
                                className="size-[200px] object-cover rounded-xl"
                            />
                        ))}
                </div>
            )
        }
        if (toolCall.name === 'code_interpreter') {
            if (!result) return null
            const code_result = parseJson(result)
            return <Response>{code_result?.answer}</Response>
        }
        if (toolCall.name === 'github') {
            return <ToolInput className="p-0" input={parsedInput || {}} />
        }
        if (toolCall.name === 'code_execution') {
            return <ToolInput className="p-0" input={parsedInput || {}} />
        }
        if (toolCall.name === 'generate_image') {
            return (
                <div>
                    <ToolInput className="p-0" input={parsedInput || {}} />
                    {parsedInput && <p className="mt-2">{t('tools.result')}</p>}
                    {result ? (
                        <div className="mt-1 flex gap-2">
                            {Array.isArray(result) &&
                                result?.map((item, index) => (
                                    <ClickableImage
                                        key={index}
                                        src={item.url}
                                        alt={t('tools.generatedImageAlt', {
                                            index: index + 1
                                        })}
                                        className="size-[200px] object-cover rounded-xl hover:opacity-90 transition-opacity"
                                    />
                                ))}
                        </div>
                    ) : parsedInput ? (
                        <Shimmer>
                            {mediaType === 'infographic'
                                ? t('tools.generatingInfographic')
                                : mediaType === 'poster'
                                  ? t('tools.generatingPoster')
                                : t('tools.generatingImage')}
                        </Shimmer>
                    ) : null}
                </div>
            )
        }
        if (toolCall.name === 'generate_storybook') {
            // Check for storybook_progress type (streaming generation)
            const progressData = parseStorybookProgress(content)
            if (progressData) {
                const generatingPages: number[] =
                    content?.generating_pages || []
                return (
                    <div>
                        <ToolInput className="p-0" input={parsedInput || {}} />
                        <div className="mt-3">
                            <StorybookProgressUI
                                data={progressData}
                                generatingPages={generatingPages}
                            />
                        </div>
                    </div>
                )
            }

            // Regular storybook result (completed)
            // Check if we have a completed storybook result
            const hasCompletedStorybook =
                content?.type === 'storybook' || result?.type === 'storybook'
            const storybookData =
                content?.type === 'storybook' ? content : result

            return (
                <div>
                    <ToolInput className="p-0" input={parsedInput || {}} />
                    {parsedInput && hasCompletedStorybook && (
                        <p className="mt-2">{t('tools.result')}</p>
                    )}
                    {hasCompletedStorybook && storybookData ? (
                        <StorybookThumbnail
                            images={
                                storybookData.pages
                                    ?.filter((p: any) => p.image_url)
                                    .map((p: any) => ({
                                        url: p.image_url
                                    })) || []
                            }
                            storybookId={storybookData.storybook_id}
                            isShareMode={isShareMode}
                        />
                    ) : parsedInput ? (
                        <Shimmer>{t('tools.generatingStorybook')}</Shimmer>
                    ) : null}
                </div>
            )
        }
        if (toolCall.name === 'send_user_files') {
            // Return null here - send_user_files is handled separately below
            return null
        }
        if (toolCall.name === 'generate_video') {
            return (
                <div>
                    <ToolInput className="p-0" input={parsedInput || {}} />
                    {parsedInput && (
                        <p className="mt-2">{t('tools.result')}</p>
                    )}
                    {result ? (
                        <div className="mt-1 flex flex-col gap-2">
                            {Array.isArray(result) &&
                                result?.map((item, index) => (
                                    <video
                                        key={index}
                                        src={item.url}
                                        controls
                                        className="max-w-[400px] rounded-xl"
                                    >
                                        {t('tools.videoNotSupported')}
                                    </video>
                                ))}
                        </div>
                    ) : parsedInput ? (
                        <Shimmer>{t('tools.generatingVideo')}</Shimmer>
                    ) : null}
                </div>
            )
        }
        if (!result) return null
        return <Response>{result}</Response>
    }, [toolResult, toolCall.name, parsedInput, t, mediaType])

    // Handle send_user_files separately to avoid useMemo issues with dialog state
    if (toolCall.name === 'send_user_files') {
        const description = parsedInput?.description || ''
        const attachments = parsedInput?.attachments || []
        // TODO: Re-enable agent type check for production: FORKABLE_AGENT_TYPES.includes(agentType)
        const canFork = toolResult && sessionId

        return (
            <ChainOfThoughtStep
                icon={icon}
                label={label}
                status={status}
                description={
                    toolResult?.is_error ? t('tools.executionFailed') : undefined
                }
            >
                <div className="space-y-3">
                    {description && (
                        <p className="text-sm text-black/70 dark:text-white/70">
                            {description}
                        </p>
                    )}
                    {Array.isArray(attachments) && attachments.length > 0 && (
                        <div className="space-y-1">
                            {attachments.map((file: string, index: number) => (
                                <div
                                    key={index}
                                    className="flex items-center gap-2 text-sm"
                                >
                                    <FileIcon className="size-4 text-blue-500" />
                                    <span className="truncate">
                                        {file.split('/').pop()}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Fork buttons - only show when tool completed and agent type is forkable */}
                    {canFork && Array.isArray(attachments) && attachments.length > 0 && (
                        <div className="flex gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                            <Button
                                variant="outline"
                                size="sm"
                                className="gap-2"
                                onClick={() => {
                                    setForkType('research_to_website')
                                    setShowForkDialog(true)
                                }}
                            >
                                <GlobeIcon className="size-4" />
                                {t('fork.createWebsite.button')}
                            </Button>
                            {/* Future: Add more fork options like slide */}
                        </div>
                    )}
                </div>

                {/* Dialog rendered outside conditional to ensure proper state updates */}
                {sessionId && (
                    <ForkSessionDialog
                        open={showForkDialog}
                        onOpenChange={setShowForkDialog}
                        sessionId={sessionId}
                        attachments={attachments}
                        forkType={forkType}
                    />
                )}
            </ChainOfThoughtStep>
        )
    }

    return (
        <ChainOfThoughtStep
            icon={icon}
            label={label}
            status={status}
            description={
                toolResult?.is_error ? t('tools.executionFailed') : undefined
            }
        >
            {output}
        </ChainOfThoughtStep>
    )
}
