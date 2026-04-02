/**
 * Device presets for responsive preview - similar to Chrome DevTools
 */

export interface DevicePreset {
    id: string
    name: string
    width: number
    height: number
    type: 'desktop' | 'tablet' | 'mobile'
    userAgent?: string
}

export const DEVICE_PRESETS: DevicePreset[] = [
    // Desktop (responsive, fills container)
    {
        id: 'responsive',
        name: 'Desktop',
        width: 0,
        height: 0,
        type: 'desktop'
    },

    // Tablet (portrait + landscape)
    {
        id: 'tablet-portrait',
        name: 'Tablet (Vertical)',
        width: 834,
        height: 1194,
        type: 'tablet'
    },
    {
        id: 'tablet-landscape',
        name: 'Tablet (Horizontal)',
        width: 1194,
        height: 834,
        type: 'tablet'
    },

    // Phone (portrait + landscape)
    {
        id: 'phone-portrait',
        name: 'Phone (Vertical)',
        width: 390,
        height: 844,
        type: 'mobile'
    },
    {
        id: 'phone-landscape',
        name: 'Phone (Horizontal)',
        width: 844,
        height: 390,
        type: 'mobile'
    }
]

// Zoom presets
export const ZOOM_PRESETS = [25, 50, 75, 100, 125, 150, 200]

// Tracked CSS properties for design mode
export const TRACKED_PROPERTIES = [
    'font-family',
    'font-size',
    'font-weight',
    'color',
    'background-color',
    'border-radius',
    'padding',
    'margin'
]
