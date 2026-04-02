export type ChatMediaType = 'image' | 'storybook' | 'video' | 'infographic' | 'poster'

type MediaTypeConfig = {
    icon: string
    label: string
    supportSuggestions: boolean
    supportsStyles: boolean
    supportsMiniTools: boolean
}

const MEDIA_TYPE_CONFIG: Record<ChatMediaType, MediaTypeConfig> = {
    image: {
        icon: 'gallery',
        label: 'Image',
        supportSuggestions: true,
        supportsStyles: true,
        supportsMiniTools: true
    },
    infographic: {
        icon: 'mode-infographic',
        label: 'Infographic',
        supportSuggestions: true,
        supportsStyles: true,
        supportsMiniTools: false
    },
    poster: {
        icon: 'mode-poster',
        label: 'Poster',
        supportSuggestions: true,
        supportsStyles: true,
        supportsMiniTools: false
    },
    storybook: {
        icon: 'mode-storybook',
        label: 'Storybook',
        supportSuggestions: true,
        supportsStyles: true,
        supportsMiniTools: true
    },
    video: {
        icon: 'mode-video',
        label: 'Video',
        supportSuggestions: true,
        supportsStyles: false,
        supportsMiniTools: false
    }
}

export const getMediaTypeConfig = (
    type: ChatMediaType
): MediaTypeConfig => MEDIA_TYPE_CONFIG[type] ?? {}
