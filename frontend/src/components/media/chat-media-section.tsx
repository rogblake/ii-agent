import { useEffect, useRef, useState, type RefObject } from 'react'

import Suggestions from '../question-suggestions'
import { MediaStylePicker } from './media-style-picker'
import MiniToolsGrid from './image/mini-tools-grid'
import MiniToolBoardOverlay from './image/mini-tool-board-overlay'
import { VideoTemplatesSection } from './video/video-templates-section'
import { Button } from '../ui/button'
import { Icon } from '../ui/icon'
import { CHAT_FEATURES } from '@/constants/tool'
import { CHAT_MEDIA_SUGGESTIONS } from '@/constants/media-models'
import {
    getMediaTypeConfig,
    type ChatMediaType
} from '@/constants/media-type-config'
import { QUESTION_MODE } from '@/typings'
import type { ChatMediaPreference } from '@/typings/agent'
import type { MediaTemplate } from '@/services/media-template.service'
import type { MiniTool } from '@/constants/media-tools'
import type { VideoTemplate } from '@/constants/video-models'
import { useTranslation } from 'react-i18next'
import { CouncilConfigPanel } from '@/components/council/council-config-panel'
import {
    selectCouncilPreference,
    setCouncilPreference,
    useAppDispatch,
    useAppSelector
} from '@/state'

type ChatMediaSectionProps = {
    questionMode: QUESTION_MODE
    hideFeatureSelector?: boolean
    hideSuggestions?: boolean
    chatMediaPreference: ChatMediaPreference
    currentTextareaValue: string
    setCurrentTextareaValue: (value: string) => void
    textareaRef?: RefObject<HTMLTextAreaElement>
    onSelectMedia: (type: ChatMediaType) => void
    onMediaTemplateSelect: (template: MediaTemplate | undefined) => void
    onExploreMoreTemplates: () => void
    onVideoTemplateSelect?: (template: VideoTemplate) => void
    miniToolsSessionId?: string
    miniToolsDisabled?: boolean
    miniToolClearSignal: number
    openBoardSignal?: number
    onMiniToolSelect?: (tool: MiniTool) => void
    onMiniToolClear: () => void
    isSessionView: boolean
    fallbackSessionId?: string
}

const ChatMediaSection = ({
    questionMode,
    hideFeatureSelector,
    hideSuggestions,
    chatMediaPreference,
    currentTextareaValue,
    setCurrentTextareaValue,
    textareaRef,
    onSelectMedia,
    onMediaTemplateSelect,
    onExploreMoreTemplates,
    onVideoTemplateSelect,
    miniToolsSessionId,
    miniToolsDisabled,
    openBoardSignal,
    onMiniToolSelect,
    onMiniToolClear,
    isSessionView,
    fallbackSessionId
}: ChatMediaSectionProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const councilPreference = useAppSelector(selectCouncilPreference)
    const [showMiniTools, setShowMiniTools] = useState(false)
    const [miniToolBoardOpen, setMiniToolBoardOpen] = useState(false)
    const miniToolsSectionRef = useRef<HTMLDivElement | null>(null)
    const mediaTypeConfig = getMediaTypeConfig(chatMediaPreference.type)
    const suggestionsKey = CHAT_MEDIA_SUGGESTIONS[chatMediaPreference.type]
    const suggestionsValue = suggestionsKey
        ? t(suggestionsKey, { returnObjects: true })
        : []
    const suggestions = Array.isArray(suggestionsValue) ? suggestionsValue : []

    useEffect(() => {
        const canOpenMiniToolBoard =
            questionMode === QUESTION_MODE.CHAT &&
            !isSessionView &&
            chatMediaPreference.enabled &&
            mediaTypeConfig.supportsMiniTools &&
            Boolean(chatMediaPreference.mini_tools)

        if (!canOpenMiniToolBoard) {
            setMiniToolBoardOpen(false)
        }
    }, [
        chatMediaPreference.enabled,
        chatMediaPreference.mini_tools,
        chatMediaPreference.type,
        isSessionView,
        questionMode
    ])

    useEffect(() => {
        if (!openBoardSignal) return
        setMiniToolBoardOpen(true)
    }, [openBoardSignal])

    const handleClearMiniTool = () => {
        onMiniToolClear()
        setMiniToolBoardOpen(false)
    }

    if (hideFeatureSelector || questionMode !== QUESTION_MODE.CHAT) {
        return null
    }

    return (
        <div className="flex flex-col items-start justify-start w-full mt-3 z-10 gap-3">
            {!chatMediaPreference.enabled && !councilPreference.enabled && (
                <div className="flex items-center gap-3 md:gap-4 md:justify-center flex-wrap md:flex-nowrap w-full">
                    {CHAT_FEATURES.map((chat_feature) => (
                        <Button
                            variant="outline"
                            key={chat_feature.name}
                            onClick={() => {
                                if (chat_feature.type === 'council') {
                                    dispatch(
                                        setCouncilPreference({
                                            enabled: true,
                                            councilModelIds: [],
                                            synthesisModelId: ''
                                        })
                                    )
                                } else {
                                    onSelectMedia(
                                        chat_feature.type as ChatMediaType
                                    )
                                }
                            }}
                            className="h-7 md:h-8 !px-4 cursor-pointer rounded-full text-xs border-charcoal dark:border-sky-blue text-charcoal dark:text-sky-blue"
                        >
                            <Icon
                                name={chat_feature.icon}
                                className="size-4 text-black dark:text-sky-blue"
                            />
                            {chat_feature.nameKey
                                ? t(chat_feature.nameKey)
                                : chat_feature.name}
                        </Button>
                    ))}
                </div>
            )}
            {councilPreference.enabled && <CouncilConfigPanel />}
            {!hideSuggestions &&
                chatMediaPreference.enabled &&
                mediaTypeConfig.supportSuggestions &&
                suggestions.length > 0 && (
                    <Suggestions
                        hidden={!!currentTextareaValue.trim()}
                        suggestions={suggestions}
                        onSelect={(item) => {
                            if (textareaRef?.current) {
                                textareaRef.current.value = item
                                setCurrentTextareaValue(item)
                                setTimeout(() => {
                                    textareaRef.current?.focus()
                                }, 300)
                            }
                        }}
                    />
                )}

            {chatMediaPreference.enabled && mediaTypeConfig.supportsStyles && (
                <MediaStylePicker
                    isVisible
                    mediaType={chatMediaPreference.type}
                    selectedTemplate={chatMediaPreference.template_id}
                    onTemplateSelect={onMediaTemplateSelect}
                    onExploreMore={onExploreMoreTemplates}
                />
            )}

            {/* Video Templates Section - shown when video mode is enabled */}
            {chatMediaPreference.enabled &&
                chatMediaPreference.type === 'video' &&
                onVideoTemplateSelect && (
                    <VideoTemplatesSection
                        onTemplateSelect={onVideoTemplateSelect}
                        className="mt-4"
                    />
                )}

            {chatMediaPreference.enabled &&
                chatMediaPreference.type === 'image' &&
                mediaTypeConfig.supportsMiniTools && (
                    <div
                        ref={miniToolsSectionRef}
                        className="w-full flex flex-col items-center gap-4 mt-2"
                    >
                        <button
                            type="button"
                            onClick={() => setShowMiniTools(!showMiniTools)}
                            className="cursor-pointer flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-all hover:-translate-y-0.5"
                        >
                            <span>{t('media.miniTools.exploreMore')}</span>
                            <span
                                className={`inline-flex items-center justify-center w-5 h-5 rounded-full`}
                            >
                                <Icon
                                    name="arrow-up-2"
                                    className="size-5 fill-current"
                                />
                            </span>
                        </button>

                        {showMiniTools && !miniToolsSessionId && (
                            <MiniToolsGrid
                                open={showMiniTools}
                                disabled={miniToolsDisabled}
                                onSelect={(tool) => {
                                    onMiniToolSelect?.(tool)
                                    setMiniToolBoardOpen(true)
                                    setShowMiniTools(false)
                                }}
                                onClose={() => setShowMiniTools(false)}
                            />
                        )}
                    </div>
                )}

            {miniToolBoardOpen &&
                questionMode === QUESTION_MODE.CHAT &&
                !isSessionView &&
                chatMediaPreference.enabled &&
                mediaTypeConfig.supportsMiniTools &&
                chatMediaPreference.mini_tools && (
                    <MiniToolBoardOverlay
                        open={miniToolBoardOpen}
                        selectedTool={{
                            id: chatMediaPreference.mini_tools.id,
                            name: chatMediaPreference.mini_tools.name
                        }}
                        sessionId={miniToolsSessionId || fallbackSessionId}
                        onClose={() => setMiniToolBoardOpen(false)}
                        onClear={handleClearMiniTool}
                    />
                )}
        </div>
    )
}

export default ChatMediaSection
