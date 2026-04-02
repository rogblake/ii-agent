import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

import { type ChatMediaModel } from '@/constants/media-models'
import { useMediaModels } from '@/hooks/use-media-models'
import {
    PageCount,
    StorybookGenre,
    StorybookLanguage,
    TextPosition,
    VideoSettings,
    type ImageAspectRatio,
    type ImageResolution
} from '@/typings/agent'
import { Icon } from '../ui/icon'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '../ui/dropdown-menu'
import { Button } from '../ui/button'
import { useChatMediaPreference } from '@/hooks/use-chat-media-preference'
import { selectSubscriptionPlan, useAppSelector } from '@/state'
import { getStorybookLanguageFromLocale } from '@/utils/storybook-language'

import {
    AspectRatioPicker,
    LanguagePicker,
    MoreSettingsPicker,
    PagePicker,
    ResolutionPicker,
    TextIncludedPicker
} from './image/image-settings-picker'
import {
    VideoAspectRatioPicker,
    VideoAudioPicker,
    VideoDurationPicker,
    VideoMultishotPicker,
    VideoResolutionPicker
} from './video/video-individual-pickers'
import { DEFAULT_VIDEO_SETTINGS } from '@/constants/video-models'
import ChatMediaVideoFrames from './chat-media-video-frames'

type Props = {
    disabled?: boolean
    onModelSelect: (model: ChatMediaModel) => void
    onTextPositionChange: (position: TextPosition) => void
    onLanguageChange: (language: StorybookLanguage) => void
    onGenreChange: (genre: StorybookGenre) => void
    onMangaLayoutChange: (enabled: boolean) => void
    onRichDialogueChange: (enabled: boolean) => void
    onVoiceEnabledChange: (enabled: boolean) => void
    onPageCountChange: (count: PageCount) => void
    onAspectRatioChange: (ratio: ImageAspectRatio) => void
    onResolutionChange: (resolution: ImageResolution) => void
    onVideoSettingsChange?: (settings: Partial<VideoSettings>) => void
    onVideoFrameAdd?: (file: File, type: 'start' | 'end') => void
    uploadingVideoFrames?: Set<'start' | 'end'>
    onVideoFrameRemove?: (frameId: string) => void
}

const ChatMediaControlsMobile = ({
    disabled,
    onModelSelect,
    onTextPositionChange,
    onLanguageChange,
    onGenreChange,
    onRichDialogueChange,
    onVoiceEnabledChange,
    onPageCountChange,
    onAspectRatioChange,
    onResolutionChange,
    onVideoSettingsChange,
    onVideoFrameAdd,
    uploadingVideoFrames,
    onVideoFrameRemove
}: Props) => {
    const { t, i18n } = useTranslation()
    const subscriptionPlan = useAppSelector(selectSubscriptionPlan)
    const { chatMediaPreference } = useChatMediaPreference()
    const { getModelsForMediaType } = useMediaModels()
    const [showMoreTools, setShowMoreTools] = useState(false)

    const modelsForType = useMemo(
        () => getModelsForMediaType(chatMediaPreference.type),
        [chatMediaPreference.type, getModelsForMediaType]
    )

    const selectedModel = useMemo(
        () =>
            modelsForType.find(
                (m) => m.model_name === chatMediaPreference.model_name
            ) || modelsForType[0],
        [modelsForType, chatMediaPreference?.model_name]
    )

    const typeLabel = t('media.controls.modelLabel', {
        type: t(`media.types.${chatMediaPreference.type}`)
    })

    const isPro = useMemo(
        () => subscriptionPlan === 'pro' || subscriptionPlan === 'plus',
        [subscriptionPlan]
    )

    const isImage = useMemo(
        () =>
            chatMediaPreference.type === 'image' ||
            chatMediaPreference.type === 'infographic' ||
            chatMediaPreference.type === 'poster',
        [chatMediaPreference.type]
    )

    const isStorybook = useMemo(
        () => chatMediaPreference.type === 'storybook',
        [chatMediaPreference.type]
    )

    const isVideo = useMemo(
        () => chatMediaPreference.type === 'video',
        [chatMediaPreference.type]
    )

    const defaultStorybookLanguage = useMemo(
        () => getStorybookLanguageFromLocale(i18n.language),
        [i18n.language]
    )

    const videoSettings = useMemo(
        () => chatMediaPreference.video_settings ?? DEFAULT_VIDEO_SETTINGS,
        [chatMediaPreference.video_settings]
    )

    const currentVideoModel = useMemo(
        () =>
            chatMediaPreference.type === 'video'
                ? getModelsForMediaType('video').find(
                      (m) => m.model_name === chatMediaPreference.model_name
                  )
                : null,
        [chatMediaPreference.type, chatMediaPreference.model_name]
    )

    const handleVideoSettingsChange = (settings: Partial<VideoSettings>) => {
        onVideoSettingsChange?.(settings)
    }

    if (!chatMediaPreference.enabled) return null

    return (
        <>
            {showMoreTools && (
                <div
                    className={clsx(
                        `absolute left-0 right-0 mb-3 rounded-t-xl bg-white px-4 pt-3 pb-8 text-black z-[21]`,
                        {
                            '-top-[98px]': isStorybook || isVideo,
                            '-top-[54px]': isImage
                        }
                    )}
                >
                    <div className="grid grid-cols-2 gap-3">
                        {isStorybook && (
                            <PagePicker
                                pageCount={chatMediaPreference.page_count ?? 4}
                                onPageCountChange={onPageCountChange}
                                disabled={disabled}
                                isPro={isPro}
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isImage && (
                            <AspectRatioPicker
                                aspectRatio={
                                    chatMediaPreference.aspect_ratio ?? '1:1'
                                }
                                onAspectRatioChange={onAspectRatioChange}
                                disabled={disabled}
                                supportedAspectRatios={
                                    selectedModel?.supported_aspect_ratios
                                }
                                textPosition={chatMediaPreference.text_position}
                                modelName={chatMediaPreference.model_name}
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isImage && (
                            <ResolutionPicker
                                resolution={
                                    chatMediaPreference.resolution ?? '1K'
                                }
                                onResolutionChange={onResolutionChange}
                                disabled={disabled}
                                isPro={isPro}
                                supportedResolutions={
                                    selectedModel?.supported_resolutions
                                }
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isStorybook && !chatMediaPreference.manga_layout && (
                            <TextIncludedPicker
                                textPosition={
                                    chatMediaPreference.text_position ?? 'right'
                                }
                                onTextPositionChange={onTextPositionChange}
                                disabled={disabled}
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isStorybook && (
                            <LanguagePicker
                                language={
                                    chatMediaPreference.language ??
                                    defaultStorybookLanguage
                                }
                                onLanguageChange={onLanguageChange}
                                disabled={disabled}
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isStorybook && (
                            <MoreSettingsPicker
                                genre={
                                    chatMediaPreference.genre ?? 'fun_playful'
                                }
                                onGenreChange={onGenreChange}
                                mangaLayout={
                                    chatMediaPreference.manga_layout ?? false
                                }
                                richDialogue={
                                    chatMediaPreference.rich_dialogue ?? false
                                }
                                onRichDialogueChange={onRichDialogueChange}
                                voiceEnabled={
                                    chatMediaPreference.voice_enabled ?? false
                                }
                                onVoiceEnabledChange={onVoiceEnabledChange}
                                textPosition={chatMediaPreference.text_position}
                                disabled={disabled}
                                className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                            />
                        )}
                        {isVideo && (
                            <>
                                <VideoAspectRatioPicker
                                    aspectRatio={videoSettings.aspect_ratio}
                                    onAspectRatioChange={(ratio) =>
                                        handleVideoSettingsChange({
                                            aspect_ratio: ratio
                                        })
                                    }
                                    disabled={disabled}
                                    supportedAspectRatios={
                                        currentVideoModel?.supported_video_aspect_ratios
                                    }
                                    className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                                />
                                <VideoResolutionPicker
                                    resolution={videoSettings.resolution}
                                    onResolutionChange={(resolution) =>
                                        handleVideoSettingsChange({
                                            resolution
                                        })
                                    }
                                    disabled={disabled}
                                    isPro={isPro}
                                    supportedResolutions={
                                        currentVideoModel?.supported_video_resolutions
                                    }
                                    className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
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
                                    className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                                />
                                <VideoAudioPicker
                                    audioIncluded={videoSettings.audio_included}
                                    onAudioChange={(audio_included) =>
                                        handleVideoSettingsChange({
                                            audio_included
                                        })
                                    }
                                    disabled={disabled}
                                    supportsAudio={
                                        currentVideoModel?.supports_audio ??
                                        true
                                    }
                                    className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                                />
                                <VideoMultishotPicker
                                    multishotMode={videoSettings.multishot_mode}
                                    onMultishotChange={(multishot_mode) =>
                                        handleVideoSettingsChange({
                                            multishot_mode
                                        })
                                    }
                                    disabled={disabled}
                                    supportsMultishot={
                                        currentVideoModel?.supports_multishot ??
                                        true
                                    }
                                    className="!h-8 justify-center rounded-full !bg-black font-normal text-white"
                                />
                            </>
                        )}
                    </div>
                    <ChatMediaVideoFrames
                        className="mt-3"
                        mediaPreference={chatMediaPreference}
                        currentVideoModel={currentVideoModel || null}
                        onVideoFrameAdd={onVideoFrameAdd}
                        uploadingVideoFrames={uploadingVideoFrames}
                        onVideoFrameRemove={onVideoFrameRemove}
                        disabled={disabled}
                    />
                </div>
            )}
            <div className="flex w-[calc(100vw-56px)] items-center justify-between absolute top-4 right-4 z-[23]">
                <div className="flex items-center gap-2">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button
                                type="button"
                                variant="secondary"
                                size="icon"
                                className="text-xs px-2 w-auto h-7 rounded-full cursor-pointer flex-shrink-0 border border-firefly dark:border-sky-blue-2 text-firefly dark:text-sky-blue-2"
                                title={typeLabel}
                            >
                                <Icon
                                    name={selectedModel?.icon}
                                    className="inline md:hidden size-4"
                                />
                                <span className="truncate max-w-[120px]">
                                    {selectedModel
                                        ? t(selectedModel.label)
                                        : t('media.controls.selectModel')}
                                </span>
                                <Icon
                                    name="arrow-down"
                                    className="fill-firefly dark:fill-sky-blue-2"
                                />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent className="w-[240px] p-2">
                            {modelsForType.map((model) => (
                                <DropdownMenuItem
                                    key={model.id}
                                    className="cursor-pointer flex-col items-start gap-1 py-2"
                                    onClick={() => onModelSelect(model)}
                                >
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-black">
                                            {t(model.label)}
                                        </span>
                                        {model.model_name ===
                                            chatMediaPreference.model_name && (
                                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                                                {t('media.controls.selected')}
                                            </span>
                                        )}
                                    </div>
                                    <p className="text-xs text-grey-1">
                                        {t(model.description)}
                                    </p>
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                <button
                    type="button"
                    aria-label="Toggle media tools"
                    aria-expanded={showMoreTools}
                    onClick={() => setShowMoreTools((prev) => !prev)}
                    className={clsx({
                        'bg-sky-blue-2 text-black rounded-full size-7 flex items-center justify-center':
                            showMoreTools
                    })}
                >
                    <Icon name="dashboard-3" className="size-5" />
                </button>
            </div>
        </>
    )
}

export default ChatMediaControlsMobile
