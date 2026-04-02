import { useMemo, type ReactElement } from 'react'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'

import { Icon } from '../ui/icon'
import ChatMediaControls from './chat-media-controls'
import { AdvancedModeController } from './image/advanced-mode-controller'
import type { AdvancedModeSettings } from '@/typings/chat'
import {
    VideoDurationPicker,
    VideoResolutionPicker,
    VideoAspectRatioPicker,
    VideoAudioPicker,
    VideoMultishotPicker
} from './video/video-individual-pickers'
import ChatMediaVideoFrames from './chat-media-video-frames'
import { type ChatMediaModel } from '@/constants/media-models'
import { getMediaTypeConfig } from '@/constants/media-type-config'
import { useMediaModels } from '@/hooks/use-media-models'
import type {
    ChatMediaPreference,
    ImageAspectRatio,
    ImageResolution,
    PageCount,
    TextPosition,
    StorybookLanguage,
    StorybookGenre,
    VideoSettings
} from '@/typings/agent'
import {
    AspectRatioPicker,
    PagePicker,
    ResolutionPicker,
    TextIncludedPicker,
    LanguagePicker,
    MoreSettingsPicker,
    StorybookStylePicker
} from './image/image-settings-picker'
import { DEFAULT_VIDEO_SETTINGS } from '@/constants/video-models'
import { getStorybookLanguageFromLocale } from '@/utils/storybook-language'

interface ChatMediaToolbarProps {
    mediaPreference: ChatMediaPreference
    disabled: boolean
    isSessionView: boolean
    hideChatMediaCancel?: boolean
    isPro?: boolean
    onModelSelect: (model: ChatMediaModel) => void
    onClear: () => void
    onMiniToolChipClick?: () => void
    onMiniToolClear?: () => void
    onTemplateClear?: () => void
    onAspectRatioChange: (ratio: ImageAspectRatio) => void
    onResolutionChange: (resolution: ImageResolution) => void
    onPageCountChange: (count: PageCount) => void
    onTextPositionChange: (position: TextPosition) => void
    onLanguageChange: (language: StorybookLanguage) => void
    onGenreChange: (genre: StorybookGenre) => void
    onMangaLayoutChange: (enabled: boolean) => void
    onRichDialogueChange: (enabled: boolean) => void
    onVoiceEnabledChange: (enabled: boolean) => void
    onVideoSettingsChange?: (settings: Partial<VideoSettings>) => void
    // Video frame props
    onVideoFrameAdd?: (file: File, type: 'start' | 'end') => void
    uploadingVideoFrames?: Set<'start' | 'end'>
    onVideoFrameRemove?: (frameId: string) => void
    onOpenPickStyleModal?: () => void
    // Advanced mode props
    sessionId?: string
    advancedModeSettings?: AdvancedModeSettings | null
    onAdvancedModeSettingsChange?: (
        settings: AdvancedModeSettings | null
    ) => void
}

function ChatMediaToolbar({
    mediaPreference,
    disabled,
    isSessionView,
    hideChatMediaCancel,
    isPro = false,
    onModelSelect,
    onClear,
    onMiniToolChipClick,
    onMiniToolClear,
    onAspectRatioChange,
    onResolutionChange,
    onPageCountChange,
    onTextPositionChange,
    onLanguageChange,
    onGenreChange,
    onMangaLayoutChange,
    onRichDialogueChange,
    onVoiceEnabledChange,
    onVideoSettingsChange,
    onVideoFrameAdd,
    uploadingVideoFrames,
    onVideoFrameRemove,
    onOpenPickStyleModal,
    sessionId,
    advancedModeSettings,
    onAdvancedModeSettingsChange
}: ChatMediaToolbarProps): ReactElement | null {
    const { getModelsForMediaType } = useMediaModels()
    const { i18n } = useTranslation()
    const defaultStorybookLanguage = useMemo(
        () => getStorybookLanguageFromLocale(i18n.language),
        [i18n.language]
    )

    if (!mediaPreference.enabled) return null

    const mediaTypeConfig = getMediaTypeConfig(mediaPreference.type)
    const isImageOrStorybook =
        mediaPreference.type === 'image' ||
        mediaPreference.type === 'storybook' ||
        mediaPreference.type === 'infographic' ||
        mediaPreference.type === 'poster'
    const isStorybook = mediaPreference.type === 'storybook'
    const currentModel = getModelsForMediaType(mediaPreference.type).find(
        (m) => m.model_name === mediaPreference.model_name
    )
    const showMiniToolChip =
        !isSessionView &&
        mediaTypeConfig.supportsMiniTools &&
        mediaPreference.mini_tools

    const handleMiniToolChipKeyDown = (
        e: React.KeyboardEvent<HTMLDivElement>
    ): void => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onMiniToolChipClick?.()
        }
    }

    const handleMiniToolClearClick = (
        e: React.MouseEvent<HTMLButtonElement>
    ): void => {
        e.stopPropagation()
        onMiniToolClear?.()
    }

    const videoSettings =
        mediaPreference.video_settings ?? DEFAULT_VIDEO_SETTINGS

    // Get video model capabilities
    const currentVideoModel =
        mediaPreference.type === 'video'
            ? getModelsForMediaType('video').find(
                  (m) => m.model_name === mediaPreference.model_name
              )
            : null

    const handleVideoSettingsChange = (settings: Partial<VideoSettings>) => {
        onVideoSettingsChange?.(settings)
    }

    return (
        <div className="flex flex-col gap-2">
            {isImageOrStorybook && (
                <div className="flex flex-row items-center gap-2 flex-wrap">
                    {isStorybook && (
                        <PagePicker
                            pageCount={mediaPreference.page_count ?? 4}
                            onPageCountChange={onPageCountChange}
                            disabled={disabled}
                            isPro={isPro}
                        />
                    )}
                    <AspectRatioPicker
                        aspectRatio={mediaPreference.aspect_ratio ?? '1:1'}
                        onAspectRatioChange={onAspectRatioChange}
                        disabled={disabled}
                        supportedAspectRatios={
                            currentModel?.supported_aspect_ratios
                        }
                        textPosition={mediaPreference.text_position}
                        modelName={mediaPreference.model_name}
                    />
                    <ResolutionPicker
                        resolution={mediaPreference.resolution ?? '1K'}
                        onResolutionChange={onResolutionChange}
                        disabled={disabled}
                        isPro={isPro}
                        supportedResolutions={
                            currentModel?.supported_resolutions
                        }
                    />
                    {isStorybook && !mediaPreference.manga_layout && (
                        <TextIncludedPicker
                            textPosition={
                                mediaPreference.text_position ?? 'right'
                            }
                            onTextPositionChange={onTextPositionChange}
                            disabled={disabled}
                        />
                    )}
                    {isStorybook && (
                        <LanguagePicker
                            language={
                                mediaPreference.language ??
                                defaultStorybookLanguage
                            }
                            onLanguageChange={onLanguageChange}
                            disabled={disabled}
                        />
                    )}
                    {isStorybook && (
                        <MoreSettingsPicker
                            genre={mediaPreference.genre ?? 'fun_playful'}
                            onGenreChange={onGenreChange}
                            mangaLayout={mediaPreference.manga_layout ?? false}
                            richDialogue={
                                mediaPreference.rich_dialogue ?? false
                            }
                            onRichDialogueChange={onRichDialogueChange}
                            voiceEnabled={
                                mediaPreference.voice_enabled ?? false
                            }
                            onVoiceEnabledChange={onVoiceEnabledChange}
                            textPosition={mediaPreference.text_position}
                            disabled={disabled}
                        />
                    )}
                </div>
            )}
            {/* Video Settings - Same pattern as Image */}
            {mediaPreference.type === 'video' && onVideoSettingsChange && (
                <div className="flex flex-row items-center gap-2 flex-wrap">
                    <VideoAspectRatioPicker
                        aspectRatio={videoSettings.aspect_ratio}
                        onAspectRatioChange={(ratio) =>
                            handleVideoSettingsChange({ aspect_ratio: ratio })
                        }
                        disabled={disabled}
                        supportedAspectRatios={
                            currentVideoModel?.supported_video_aspect_ratios
                        }
                    />
                    <VideoResolutionPicker
                        resolution={videoSettings.resolution}
                        onResolutionChange={(resolution) =>
                            handleVideoSettingsChange({ resolution })
                        }
                        disabled={disabled}
                        isPro={isPro}
                        supportedResolutions={
                            currentVideoModel?.supported_video_resolutions
                        }
                    />
                    <VideoDurationPicker
                        duration={videoSettings.duration}
                        onDurationChange={(duration) =>
                            handleVideoSettingsChange({ duration })
                        }
                        disabled={disabled}
                        isPro={isPro}
                        supportedDurations={
                            currentVideoModel?.supported_durations
                        }
                    />
                    <VideoAudioPicker
                        audioIncluded={videoSettings.audio_included}
                        onAudioChange={(audio_included) =>
                            handleVideoSettingsChange({ audio_included })
                        }
                        disabled={disabled}
                        supportsAudio={
                            currentVideoModel?.supports_audio ?? true
                        }
                    />
                    <VideoMultishotPicker
                        multishotMode={videoSettings.multishot_mode}
                        onMultishotChange={(multishot_mode) =>
                            handleVideoSettingsChange({ multishot_mode })
                        }
                        disabled={disabled}
                        supportsMultishot={
                            currentVideoModel?.supports_multishot ?? true
                        }
                    />
                </div>
            )}
            <ChatMediaVideoFrames
                mediaPreference={mediaPreference}
                currentVideoModel={currentVideoModel || null}
                onVideoFrameAdd={onVideoFrameAdd}
                uploadingVideoFrames={uploadingVideoFrames}
                onVideoFrameRemove={onVideoFrameRemove}
                disabled={disabled}
            />
            <div className="flex flex-row items-center gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                    <ChatMediaControls
                        disabled={disabled}
                        mediaPreference={mediaPreference}
                        onModelSelect={onModelSelect}
                        onClear={onClear}
                        showCancel={!hideChatMediaCancel}
                    />
                    {mediaTypeConfig.supportsStyles && (
                        <div
                            className={clsx(
                                'flex justify-center size-7 items-center gap-1.5 rounded-full bg-charcoal/10 dark:bg-sky-blue-2/10 cursor-pointer',
                                {
                                    '!bg-sky-blue':
                                        mediaPreference.template_name
                                }
                            )}
                            role="button"
                            onClick={onOpenPickStyleModal}
                        >
                            <Icon
                                name="note-2"
                                className={clsx(
                                    'size-[18px] fill-black dark:fill-sky-blue',
                                    {
                                        '!fill-black':
                                            mediaPreference.template_name
                                    }
                                )}
                            />
                        </div>
                    )}

                    {showMiniToolChip && (
                        <div
                            className="inline-flex h-7 items-center gap-1.5 rounded-full border border-black px-2.5 dark:border-sky-blue-2 dark:bg-sky-blue-2 cursor-pointer"
                            role="button"
                            tabIndex={0}
                            onClick={onMiniToolChipClick}
                            onKeyDown={handleMiniToolChipKeyDown}
                        >
                            <span
                                className="text-xs font-medium text-black dark:text-black truncate max-w-[120px]"
                                title={mediaPreference.mini_tools?.name}
                            >
                                {mediaPreference.mini_tools?.name}
                            </span>
                            <button
                                type="button"
                                className="ml-0.5 flex-shrink-0 rounded-full p-0.5 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                                onClick={handleMiniToolClearClick}
                                title="Clear mini tool"
                            >
                                <Icon
                                    name="close"
                                    className="size-3 fill-black"
                                />
                            </button>
                        </div>
                    )}
                    {isStorybook && (
                        <StorybookStylePicker
                            mangaLayout={mediaPreference.manga_layout ?? false}
                            onMangaLayoutChange={onMangaLayoutChange}
                            disabled={disabled}
                            className="h-7 rounded-full"
                        />
                    )}

                    {mediaPreference.type === 'image' && (
                        <AdvancedModeController
                            disabled={disabled}
                            sessionId={sessionId}
                            modelName={mediaPreference.model_name}
                            provider={mediaPreference.provider}
                            advancedModeSettings={advancedModeSettings}
                            onAdvancedModeSettingsChange={
                                onAdvancedModeSettingsChange
                            }
                            hiddenByMiniTool={!!mediaPreference.mini_tools}
                            toggleButtonClassName={
                                isSessionView ? 'hidden' : ''
                            }
                            showPreviewPosition="fixed"
                        />
                    )}
                </div>
            </div>
        </div>
    )
}

export default ChatMediaToolbar
