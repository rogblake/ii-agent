import { ChatMediaPreference } from '@/typings/agent'
import { type ChatMediaType } from '@/constants/media-type-config'
import { type ChatMediaModel } from '@/constants/media-models'

type MediaModelInfo = Pick<ChatMediaModel, 'type' | 'model_name' | 'provider'>

/**
 * Get default chat media preference from first available model
 */
const buildDefaultMediaPreference = (
    models: MediaModelInfo[],
    fallbackType: ChatMediaType,
    persisted?: Partial<ChatMediaPreference>
): ChatMediaPreference => {
    const defaultModel = models[0]

    if (!defaultModel) {
        // Return a disabled preference when no models are available
        return {
            enabled: false,
            type: fallbackType,
            model_name: '',
            provider: '',
            voice_enabled: persisted?.voice_enabled ?? true,
            rich_dialogue: persisted?.rich_dialogue ?? false
        }
    }

    return {
        enabled: false,
        type: defaultModel.type ?? fallbackType,
        model_name: defaultModel.model_name,
        provider: defaultModel.provider,
        // template_* intentionally undefined
        aspect_ratio: '1:1',
        resolution: '1K',
        voice_enabled: persisted?.voice_enabled ?? true,
        rich_dialogue: persisted?.rich_dialogue ?? false
    }
}

export const getDefaultChatImagePreference = (
    imageModels: MediaModelInfo[],
    persisted?: Partial<ChatMediaPreference>
): ChatMediaPreference => {
    return buildDefaultMediaPreference(imageModels, 'image', persisted)
}

export const getDefaultChatVideoPreference = (
    videoModels: MediaModelInfo[],
    persisted?: Partial<ChatMediaPreference>
): ChatMediaPreference => {
    return buildDefaultMediaPreference(videoModels, 'video', persisted)
}

export const getDefaultChatMediaPreference = (
    imageModels: MediaModelInfo[] = [],
    videoModels: MediaModelInfo[] = [],
    persisted?: Partial<ChatMediaPreference>
): ChatMediaPreference => {
    if (imageModels.length > 0) {
        return getDefaultChatImagePreference(imageModels, persisted)
    }

    if (videoModels.length > 0) {
        return getDefaultChatVideoPreference(videoModels, persisted)
    }

    // Return a default disabled preference when no models are available
    return {
        enabled: false,
        type: 'image',
        model_name: '',
        provider: '',
        voice_enabled: persisted?.voice_enabled ?? true,
        rich_dialogue: persisted?.rich_dialogue ?? false
    }
}
