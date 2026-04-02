import type { ChatMediaModel } from './media-models'

// Video-specific types
export type VideoDuration = '4s' | '6s' | '8s' | '10s' | '12s' | '18s' | '24s' | '30s'
export type VideoResolution = '720p' | '1080p'
export type VideoAspectRatio = '16:9' | '9:16'

export interface VideoSettings {
    duration: VideoDuration
    resolution: VideoResolution
    aspect_ratio: VideoAspectRatio
    audio_included: boolean
    multishot_mode: boolean
}

export interface VideoModelCapabilities {
    supported_durations: VideoDuration[]
    supported_resolutions: VideoResolution[]
    supported_aspect_ratios: VideoAspectRatio[]
    supports_audio: boolean
    supports_multishot: boolean
    supports_start_frame: boolean
    supports_end_frame: boolean
    supports_text_to_video: boolean
    supports_image_to_video: boolean
}

export interface ChatVideoModel extends ChatMediaModel {
    type: 'video'
    capabilities: VideoModelCapabilities
    is_pro?: boolean
}

// Duration options with Pro Plan restrictions
export const VIDEO_DURATION_OPTIONS: Array<{
    value: VideoDuration
    label: string
    isPro: boolean
}> = [
    { value: '4s', label: '4s', isPro: false },
    { value: '6s', label: '6s', isPro: false },
    { value: '8s', label: '8s', isPro: false },
    { value: '10s', label: '10s', isPro: false },
    { value: '12s', label: '12s', isPro: true },
    { value: '18s', label: '18s', isPro: true },
    { value: '24s', label: '24s', isPro: true },
    { value: '30s', label: '30s', isPro: true }
]

// Resolution options with Pro Plan restrictions
export const VIDEO_RESOLUTION_OPTIONS: Array<{
    value: VideoResolution
    label: string
    isPro: boolean
}> = [
    { value: '720p', label: '720p', isPro: false },
    { value: '1080p', label: '1080p', isPro: true }
]

// Aspect ratio options for video
export const VIDEO_ASPECT_RATIO_OPTIONS: Array<{
    value: VideoAspectRatio
    label: string
    icon: 'landscape' | 'portrait'
}> = [
    { value: '16:9', label: '16:9', icon: 'landscape' },
    { value: '9:16', label: '9:16', icon: 'portrait' }
]

// Default video settings
export const DEFAULT_VIDEO_SETTINGS: VideoSettings = {
    duration: '6s',
    resolution: '720p',
    aspect_ratio: '16:9',
    audio_included: true,
    multishot_mode: true
}

// Video models from Figma design
// NOTE: Temporarily only Veo 3.1 is enabled for chat mode video generation
export const CHAT_VIDEO_MODELS_EXTENDED: ChatVideoModel[] = [
    {
        id: 'veo-3.1-premium',
        label: 'VEO 3.1 Premium',
        model_name: 'veo-3.1-premium',
        provider: 'vertex',
        type: 'video',
        description: "Ultimate video quality with native audio - Google's most advanced model",
        icon: 'google',
        is_pro: false,
        capabilities: {
            supported_durations: ['4s', '6s', '8s', '10s', '12s', '18s', '24s', '30s'],
            supported_resolutions: ['720p', '1080p'],
            supported_aspect_ratios: ['16:9', '9:16'],
            supports_audio: true,
            supports_multishot: true,
            supports_start_frame: true,
            supports_end_frame: true,
            supports_text_to_video: true,
            supports_image_to_video: true
        }
    }
]

// Video templates from Figma design
export interface VideoTemplate {
    id: string
    name: string
    thumbnail: string
    description?: string
    default_prompt?: string
}

export const VIDEO_TEMPLATES: VideoTemplate[] = [
    {
        id: 'red-carpet',
        name: 'Red Carpet',
        thumbnail: '/templates/video/red-carpet.jpg',
        description: 'Walk on red carpet with paparazzi',
        default_prompt: 'Create a video of me walking on Red Carpet at the Night Premier and surrounded by crowded paparazzi'
    },
    {
        id: 'video-game',
        name: 'Video Game',
        thumbnail: '/templates/video/video-game.jpg',
        description: 'Pixel style game video with neon effects',
        default_prompt: 'Create for a game video with pixel style and neon color effect'
    },
    {
        id: 'asmr-video',
        name: 'ASMR Video',
        thumbnail: '/templates/video/asmr.jpg',
        description: 'Close-up ASMR style video',
        default_prompt: 'Make a close-up ASMR of peeling an apple'
    },
    {
        id: 'cinematic-action',
        name: 'Cinematic Action',
        thumbnail: '/templates/video/cinematic-action.jpg',
        description: 'Action hero scene in urban environment',
        default_prompt: 'Turn me into an action hero scene inside urban city'
    }
]

// Video prompt suggestions from Figma design
export const VIDEO_PROMPT_SUGGESTIONS: string[] = [
    'Create a of me walking on Red Carpet at the Night Premier and surrounded by crowded paparazzi',
    'Create for a game video with pixel style and neon color effect',
    'Make a close-up ASMR of peeling an apple',
    'Generate a video of a mini racetrack on a table with mini furniture around',
    'Turn me into an action hero scene inside urban city',
    'Make a daily vlog video style in a pov of a king from civilization century'
]

// Capability badges/tags shown on model cards
export type VideoCapabilityTag =
    | '200-800'
    | '720p-1080p'
    | '4s-12s'
    | '6s-12s'
    | 'Audio'
    | 'Text to Video'
    | 'Frames to Video'

export const getVideoModelCapabilityTags = (
    model: ChatVideoModel
): VideoCapabilityTag[] => {
    const tags: VideoCapabilityTag[] = []
    const caps = model.capabilities

    // Resolution range
    const resolutions = caps.supported_resolutions
    if (resolutions.length > 0) {
        const minRes = resolutions[0]
        const maxRes = resolutions[resolutions.length - 1]
        tags.push(`${minRes}-${maxRes}` as VideoCapabilityTag)
    }

    // Duration range
    const durations = caps.supported_durations
    if (durations.length > 0) {
        const minDur = durations[0]
        const maxDur = durations[durations.length - 1]
        tags.push(`${minDur}-${maxDur}` as VideoCapabilityTag)
    }

    // Audio support
    if (caps.supports_audio) {
        tags.push('Audio')
    }

    // Text to Video
    if (caps.supports_text_to_video) {
        tags.push('Text to Video')
    }

    // Frames to Video (start/end frame support)
    if (caps.supports_start_frame || caps.supports_end_frame) {
        tags.push('Frames to Video')
    }

    return tags
}
