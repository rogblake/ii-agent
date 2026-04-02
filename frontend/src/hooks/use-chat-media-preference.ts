import { useCallback, useEffect, useMemo, useRef } from 'react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { type ChatMediaModel } from '@/constants/media-models'
import { type MiniTool } from '@/constants/media-tools'
import { type ChatMediaType } from '@/constants/media-type-config'
import {
    clearChatMediaTool,
    removeFromCurrentMessageFileIds,
    selectChatMediaPreference,
    setChatMediaPreference,
    useAppDispatch,
    useAppSelector
} from '@/state'
import type {
    ChatMediaPreference,
    ImageAspectRatio,
    ImageResolution,
    PageCount,
    TextPosition,
    StorybookLanguage,
    StorybookGenre,
    VideoSettings,
    VideoFrameReference
} from '@/typings/agent'
import { DEFAULT_VIDEO_SETTINGS } from '@/constants/video-models'
import type { ChatQueryPayload } from '@/typings/chat'
import { useMediaModels } from './use-media-models'
import { getStorybookLanguageFromLocale } from '@/utils/storybook-language'

// Aspect ratio restrictions for separate_page mode per model
export const SEPARATE_PAGE_ASPECT_RATIOS: Record<string, ImageAspectRatio[]> = {
    'nano-banana-pro': ['1:1', '2:3', '3:4', '4:3', '9:16', '16:9'],
    'gemini-3-pro-image-preview': ['1:1', '2:3', '3:4', '4:3', '9:16', '16:9'], // model_name for nano-banana-pro
    'gpt-image-1.5': ['1:1', '2:3', '3:2'],
    // Default fallback for other models
    default: ['1:1', '2:3', '3:4']
}

export function getSeparatePageAspectRatios(
    modelName: string | undefined
): ImageAspectRatio[] {
    if (!modelName) return SEPARATE_PAGE_ASPECT_RATIOS['default']
    return (
        SEPARATE_PAGE_ASPECT_RATIOS[modelName] ??
        SEPARATE_PAGE_ASPECT_RATIOS['default']
    )
}

interface DefaultModel {
    model_name: string
    provider?: string
}

function getDefaultModelForType(
    type: ChatMediaType,
    getModelsForMediaType: (type: ChatMediaType) => ChatMediaModel[]
): DefaultModel {
    const modelsArray = getModelsForMediaType(type)
    const fallback = modelsArray.find((m) => m.type === type) ?? modelsArray[0]

    return {
        model_name: fallback?.model_name ?? '',
        provider: fallback?.provider
    }
}

export function getEffectiveMediaFileIds(
    preference: ChatMediaPreference | undefined,
    currentFileIds: string[]
): string[] {
    return preference?.mini_tools?.reference_file_ids ?? currentFileIds
}

interface MediaPreferencesPayload {
    messageFileIds: string[]
    mediaPreferences?: ChatQueryPayload['media_preferences']
}

export function buildMediaPreferencesPayload(
    preference: ChatMediaPreference | undefined,
    baseFileIds: string[]
): MediaPreferencesPayload {
    const miniToolFileIds = preference?.mini_tools?.reference_file_ids ?? []
    const messageFileIds = Array.from(
        new Set([...baseFileIds, ...miniToolFileIds])
    )
    const isInfographic = preference?.type === 'infographic'
    const isPoster = preference?.type === 'poster'
    const isTemplateOnlyMedia = isInfographic || isPoster

    if (!preference?.enabled) {
        return { messageFileIds, mediaPreferences: undefined }
    }

    const mediaReferences = preference?.advanced_mode
        ? preference.references
        : messageFileIds.length > 0
          ? messageFileIds.map((fileId) => ({ file_id: fileId }))
          : preference?.references

    return {
        messageFileIds,
        mediaPreferences: {
            enabled: true,
            type: preference.type ?? 'image',
            model_name: preference.model_name ?? '',
            provider: preference.provider,
            aspect_ratio: preference.aspect_ratio,
            resolution: preference.resolution,
            page_count: preference.page_count,
            text_position:
                preference.manga_layout === true
                    ? 'none'
                    : preference.text_position,
            language: preference.language,
            genre: preference.genre,
            manga_layout: preference.manga_layout,
            rich_dialogue:
                preference.manga_layout === true
                    ? false
                    : preference.rich_dialogue,
            voice_enabled:
                preference.manga_layout === true
                    ? false
                    : preference.voice_enabled,
            references: isTemplateOnlyMedia ? undefined : mediaReferences,
            advanced_mode: isTemplateOnlyMedia ? false : preference.advanced_mode,
            mini_tools: isTemplateOnlyMedia ? undefined : preference.mini_tools,
            template_id: preference.template_id,
            video_settings: preference?.video_settings,
            video_frames: preference?.video_frames,
            storybook_context: preference?.storybook_context
        }
    }
}

interface MediaMetadata {
    [key: string]: unknown
    media: {
        enabled: boolean
        type: ChatMediaType
        model_name: string
        provider?: string
        aspect_ratio?: ImageAspectRatio
        resolution?: ImageResolution
        page_count?: PageCount
        text_position?: TextPosition
        language?: StorybookLanguage
        language_source?: 'system' | 'user'
        genre?: StorybookGenre
        manga_layout?: boolean
        rich_dialogue?: boolean
        voice_enabled?: boolean
        video_settings?: VideoSettings
        video_frames?: VideoFrameReference[]
    }
}

export function getMediaMetadata(
    preference: ChatMediaPreference | undefined
): MediaMetadata | undefined {
    if (!preference?.enabled) return undefined

    const media: MediaMetadata['media'] = {
        enabled: true,
        type: preference.type,
        model_name: preference.model_name,
        provider: preference.provider,
        aspect_ratio: preference.aspect_ratio,
        resolution: preference.resolution,
        page_count: preference.page_count,
        text_position:
            preference.manga_layout === true
                ? 'none'
                : preference.text_position,
        language: preference.language,
        language_source: preference.language_source,
        genre: preference.genre,
        manga_layout: preference.manga_layout,
        rich_dialogue:
            preference.manga_layout === true
                ? false
                : preference.rich_dialogue,
        voice_enabled:
            preference.manga_layout === true
                ? false
                : preference.voice_enabled,
        video_frames: preference.video_frames
    }

    if (preference.type === 'video') {
        media.video_settings = preference.video_settings
    }

    return { media }
}

export function useChatMediaPreference() {
    const dispatch = useAppDispatch()
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const { i18n } = useTranslation()
    const { getModelsForMediaType, isLoading: isMediaModelsLoading } =
        useMediaModels()
    const defaultStorybookLanguage = useMemo(
        () => getStorybookLanguageFromLocale(i18n.language),
        [i18n.language]
    )
    const lastStorybookPrefsRef = useRef<{
        text_position?: TextPosition
        rich_dialogue?: boolean
        voice_enabled?: boolean
    } | null>(null)

    const hasMiniToolSelection = useMemo(() => {
        return (
            chatMediaPreference.enabled &&
            chatMediaPreference.type === 'image' &&
            (chatMediaPreference.mini_tools?.reference_file_ids?.length ?? 0) >
                0
        )
    }, [chatMediaPreference])

    useEffect(() => {
        if (
            chatMediaPreference.enabled &&
            chatMediaPreference.type === 'storybook' &&
            chatMediaPreference.language_source !== 'user' &&
            chatMediaPreference.language !== defaultStorybookLanguage
        ) {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    language: defaultStorybookLanguage,
                    language_source: 'system'
                })
            )
        }
    }, [chatMediaPreference, defaultStorybookLanguage, dispatch])

    const selectMediaType = useCallback(
        (type: ChatMediaType) => {
            const isSameTypeActive =
                chatMediaPreference.enabled && chatMediaPreference.type === type

            if (isSameTypeActive) {
                dispatch(
                    setChatMediaPreference({
                        ...chatMediaPreference,
                        enabled: false
                    })
                )
                return
            }

            const defaults = getDefaultModelForType(type, getModelsForMediaType)

            // Prevent enabling media mode with empty model_name (models not loaded yet)
            if (!defaults.model_name) {
                console.warn(
                    `Cannot select media type "${type}": models not loaded yet`
                )
                return
            }

            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    enabled: true,
                    type,
                    model_name: defaults.model_name,
                    provider: defaults.provider ?? chatMediaPreference.provider,
                    aspect_ratio: chatMediaPreference.aspect_ratio ?? '1:1',
                    resolution: chatMediaPreference.resolution ?? '1K',
                    page_count:
                        type === 'storybook'
                            ? (chatMediaPreference.page_count ?? 4)
                            : undefined,
                    text_position:
                        type === 'storybook'
                            ? (chatMediaPreference.text_position ?? 'separate_page')
                            : undefined,
                    language:
                        type === 'storybook'
                            ? (chatMediaPreference.language ??
                                  defaultStorybookLanguage)
                            : undefined,
                    language_source:
                        type === 'storybook'
                            ? (chatMediaPreference.language_source ?? 'system')
                            : undefined,
                    genre:
                        type === 'storybook'
                            ? (chatMediaPreference.genre ?? 'fun_playful')
                            : undefined,
                    rich_dialogue:
                        type === 'storybook'
                            ? (chatMediaPreference.rich_dialogue ?? false)
                            : chatMediaPreference.rich_dialogue,
                    voice_enabled: chatMediaPreference.voice_enabled ?? true,
                    mini_tools: undefined,
                    template_id: undefined,
                    template_name: undefined,
                    template_prompt: undefined,
                    advanced_mode: false,
                    references: undefined
                })
            )
        },
        [chatMediaPreference, dispatch, getModelsForMediaType]
    )

    const clearMediaPreference = useCallback(() => {
        dispatch(
            setChatMediaPreference({
                ...chatMediaPreference,
                enabled: false
            })
        )
    }, [chatMediaPreference, dispatch])

    const selectMediaModel = useCallback(
        (model: ChatMediaModel) => {
            const nextType =
                chatMediaPreference.type === 'infographic' ||
                chatMediaPreference.type === 'poster'
                    ? chatMediaPreference.type
                    : model.type
            const currentRatio = chatMediaPreference.aspect_ratio ?? '1:1'
            const supportedRatios = model.supported_aspect_ratios
            const newAspectRatio =
                supportedRatios && !supportedRatios.includes(currentRatio)
                    ? supportedRatios[0]
                    : currentRatio

            const currentResolution = chatMediaPreference.resolution ?? '1K'
            const supportedResolutions = model.supported_resolutions
            const newResolution =
                supportedResolutions &&
                !supportedResolutions.includes(currentResolution)
                    ? supportedResolutions[0]
                    : currentResolution

            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    enabled: true,
                    type: nextType,
                    model_name: model.model_name,
                    provider: model.provider,
                    aspect_ratio: newAspectRatio,
                    resolution: newResolution
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeAspectRatio = useCallback(
        (ratio: ImageAspectRatio) => {
            // When in separate_page mode, validate the aspect ratio
            if (chatMediaPreference.text_position === 'separate_page') {
                const allowedRatios = getSeparatePageAspectRatios(
                    chatMediaPreference.model_name
                )
                if (!allowedRatios.includes(ratio)) {
                    toast.error(
                        `Aspect ratio ${ratio} is not supported in Separate Page mode`
                    )
                    return
                }
            }

            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    aspect_ratio: ratio
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeResolution = useCallback(
        (resolution: ImageResolution) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    resolution
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changePageCount = useCallback(
        (page_count: PageCount) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    page_count
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeVideoSettings = useCallback(
        (settings: Partial<VideoSettings>) => {
            const currentSettings =
                chatMediaPreference.video_settings ?? DEFAULT_VIDEO_SETTINGS
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    video_settings: {
                        ...currentSettings,
                        ...settings
                    }
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeTextPosition = useCallback(
        (text_position: TextPosition) => {
            let newAspectRatio = chatMediaPreference.aspect_ratio
            const currentRatio = chatMediaPreference.aspect_ratio ?? '1:1'

            // When switching to separate_page, validate and adjust aspect ratio
            if (text_position === 'separate_page') {
                const allowedRatios = getSeparatePageAspectRatios(
                    chatMediaPreference.model_name
                )

                if (!allowedRatios.includes(currentRatio)) {
                    // Auto-switch to first allowed ratio
                    newAspectRatio = allowedRatios[0]
                }
            }
            // When switching away from separate_page, reset to 1:1 if current ratio is 2:3 or 3:4
            else if (chatMediaPreference.text_position === 'separate_page') {
                if (currentRatio === '2:3' || currentRatio === '3:4') {
                    newAspectRatio = '1:1'
                }
            }

            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    text_position,
                    aspect_ratio: newAspectRatio,
                    rich_dialogue:
                        text_position !== 'separate_page'
                            ? false
                            : chatMediaPreference.rich_dialogue
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const addVideoFrame = useCallback(
        (frame: VideoFrameReference) => {
            const currentFrames = chatMediaPreference.video_frames ?? []
            // Remove existing frame of the same type
            const filteredFrames = currentFrames.filter(
                (f) => f.type !== frame.type
            )
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    video_frames: [...filteredFrames, frame]
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeLanguage = useCallback(
        (language: StorybookLanguage) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    language,
                    language_source: 'user'
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    // const updateVideoFrameFileId = useCallback(
    //     (frameId: string, fileId: string) => {
    //         const currentFrames = chatMediaPreference.video_frames ?? []
    //         const updatedFrames = currentFrames.map(f =>
    //             f.id === frameId ? { ...f, file_id: fileId } : f
    //         )
    //         dispatch(
    //             setChatMediaPreference({
    //                 ...chatMediaPreference,
    //                 video_frames: updatedFrames
    //             })
    //         )
    //     },
    //     [chatMediaPreference, dispatch]
    // )

    const changeGenre = useCallback(
        (genre: StorybookGenre) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    genre
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeMangaLayout = useCallback(
        (enabled: boolean) => {
            if (enabled) {
                lastStorybookPrefsRef.current = {
                    text_position: chatMediaPreference.text_position,
                    rich_dialogue: chatMediaPreference.rich_dialogue,
                    voice_enabled: chatMediaPreference.voice_enabled
                }
            }
            const previousPrefs = lastStorybookPrefsRef.current
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    manga_layout: enabled,
                    text_position: enabled
                        ? 'none'
                        : previousPrefs?.text_position ??
                          (chatMediaPreference.text_position !== 'none'
                              ? chatMediaPreference.text_position
                              : 'separate_page'),
                    rich_dialogue: enabled
                        ? chatMediaPreference.rich_dialogue
                        : previousPrefs?.rich_dialogue ??
                          chatMediaPreference.rich_dialogue,
                    voice_enabled: enabled
                        ? chatMediaPreference.voice_enabled
                        : previousPrefs?.voice_enabled ??
                          chatMediaPreference.voice_enabled
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const removeVideoFrame = useCallback(
        (frameId: string) => {
            const currentFrames = chatMediaPreference.video_frames ?? []
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    video_frames: currentFrames.filter((f) => f.id !== frameId)
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeRichDialogue = useCallback(
        (enabled: boolean) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    rich_dialogue: enabled
                })
            )
        },
        [chatMediaPreference, dispatch]
    )

    const changeVoiceEnabled = useCallback(
        (enabled: boolean) => {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    voice_enabled: enabled
                })
            )
        },
        [chatMediaPreference, dispatch]
    )
    const clearVideoFrames = useCallback(() => {
        dispatch(
            setChatMediaPreference({
                ...chatMediaPreference,
                video_frames: []
            })
        )
    }, [chatMediaPreference, dispatch])

    const clearMiniToolSelection = useCallback(
        (options?: { removeReferencesFromMessage?: boolean }) => {
            const referenceIds =
                chatMediaPreference.mini_tools?.reference_file_ids ?? []
            if (options?.removeReferencesFromMessage && referenceIds.length) {
                dispatch(removeFromCurrentMessageFileIds(referenceIds))
            }
            dispatch(clearChatMediaTool())
        },
        [chatMediaPreference.mini_tools?.reference_file_ids, dispatch]
    )

    const applyMiniToolSelection = useCallback(
        (tool: MiniTool, options?: { clearPreviousReferences?: boolean }) => {
            if (options?.clearPreviousReferences) {
                const prevRefs =
                    chatMediaPreference.mini_tools?.reference_file_ids ?? []
                if (prevRefs.length) {
                    dispatch(removeFromCurrentMessageFileIds(prevRefs))
                }
            }

            const defaults = getDefaultModelForType(
                'image',
                getModelsForMediaType
            )
            let effectiveModel =
                chatMediaPreference.type === 'image'
                    ? chatMediaPreference.model_name
                    : defaults.model_name
            let effectiveProvider =
                chatMediaPreference.type === 'image'
                    ? chatMediaPreference.provider
                    : defaults.provider
            let effectiveAspectRatio = chatMediaPreference.aspect_ratio
            let effectiveResolution = chatMediaPreference.resolution

            // Force GPT-image-1.5 for Remove Background tool
            if (tool.name === 'Remove Background') {
                effectiveModel = 'gpt-image-1.5'
                effectiveProvider = 'openai'
                effectiveAspectRatio = '1:1'
                effectiveResolution = '1K'

                // Show toast notification
                toast.info(
                    'Remove Background works best with GPT-image-1.5. Model automatically switched for optimal results.'
                )
            }

            // Prevent enabling media mode with empty model_name (models not loaded yet)
            if (!effectiveModel) {
                console.warn('Cannot apply mini tool: models not loaded yet')
                return
            }

            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    enabled: true,
                    type: 'image',
                    model_name: effectiveModel,
                    provider: effectiveProvider ?? chatMediaPreference.provider,
                    aspect_ratio: effectiveAspectRatio,
                    resolution: effectiveResolution,
                    mini_tools: {
                        id: tool.id,
                        name: tool.name
                    }
                })
            )
        },
        [chatMediaPreference, dispatch, getModelsForMediaType]
    )

    return {
        chatMediaPreference,
        hasMiniToolSelection,
        isMediaModelsLoading,
        selectMediaType,
        clearMediaPreference,
        selectMediaModel,
        changeAspectRatio,
        changeResolution,
        changePageCount,
        changeTextPosition,
        changeLanguage,
        changeGenre,
        changeMangaLayout,
        changeRichDialogue,
        changeVoiceEnabled,
        changeVideoSettings,
        addVideoFrame,
        removeVideoFrame,
        clearVideoFrames,
        clearMiniToolSelection,
        applyMiniToolSelection
    }
}
