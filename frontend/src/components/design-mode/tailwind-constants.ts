/**
 * Tailwind CSS constants for the design mode inspector
 */

export const FONT_FAMILIES = [
    { label: 'Arial', value: 'Arial, sans-serif' },
    { label: 'Calibri', value: 'Calibri, sans-serif' },
    { label: 'Comic Sans MS', value: 'Comic Sans MS, cursive' },
    { label: 'Courier New', value: 'Courier New, monospace' },
    { label: 'Georgia', value: 'Georgia, serif' },
    { label: 'Helvetica', value: 'Helvetica, sans-serif' },
    { label: 'Impact', value: 'Impact, sans-serif' },
    { label: 'Lato', value: 'Lato, sans-serif' },
    { label: 'Montserrat', value: 'Montserrat, sans-serif' },
    { label: 'Nunito Sans', value: 'Nunito Sans, sans-serif' },
    { label: 'Open Sans', value: 'Open Sans, sans-serif' },
    { label: 'Oswald', value: 'Oswald, sans-serif' },
    { label: 'Playfair Display', value: 'Playfair Display, serif' },
    { label: 'Poppins', value: 'Poppins, sans-serif' },
    { label: 'Roboto', value: 'Roboto, sans-serif' },
    { label: 'Times New Roman', value: 'Times New Roman, serif' },
    { label: 'Trebuchet MS', value: 'Trebuchet MS, sans-serif' },
    { label: 'Verdana', value: 'Verdana, sans-serif' }
]

export const FONT_WEIGHTS = [
    { label: 'Default', value: '' },
    { label: 'Thin', value: '100' },
    { label: 'Extra Light', value: '200' },
    { label: 'Light', value: '300' },
    { label: 'Normal', value: '400' },
    { label: 'Medium', value: '500' },
    { label: 'Semi Bold', value: '600' },
    { label: 'Bold', value: '700' },
    { label: 'Extra Bold', value: '800' },
    { label: 'Black', value: '900' }
]

export const FONT_SIZES = {
    min: 8,
    max: 96,
    default: 16
}

export const BORDER_RADIUS = {
    min: 0,
    max: 50,
    default: 0
}

export const SPACING = {
    min: 0,
    max: 64,
    default: 0
}

// Tailwind color palette for quick selection
export const TAILWIND_COLORS = [
    // Grays
    '#000000',
    '#1f2937',
    '#4b5563',
    '#9ca3af',
    '#d1d5db',
    '#f3f4f6',
    '#ffffff',
    // Reds
    '#fef2f2',
    '#fee2e2',
    '#fca5a5',
    '#f87171',
    '#ef4444',
    '#dc2626',
    '#991b1b',
    // Oranges
    '#fff7ed',
    '#ffedd5',
    '#fdba74',
    '#fb923c',
    '#f97316',
    '#ea580c',
    '#9a3412',
    // Yellows
    '#fefce8',
    '#fef9c3',
    '#fde047',
    '#facc15',
    '#eab308',
    '#ca8a04',
    '#713f12',
    // Greens
    '#f0fdf4',
    '#dcfce7',
    '#86efac',
    '#4ade80',
    '#22c55e',
    '#16a34a',
    '#14532d',
    // Blues
    '#eff6ff',
    '#dbeafe',
    '#93c5fd',
    '#60a5fa',
    '#3b82f6',
    '#2563eb',
    '#1e3a8a',
    // Purples
    '#faf5ff',
    '#f3e8ff',
    '#d8b4fe',
    '#c084fc',
    '#a855f7',
    '#9333ea',
    '#581c87',
    // Pinks
    '#fdf2f8',
    '#fce7f3',
    '#f9a8d4',
    '#f472b6',
    '#ec4899',
    '#db2777',
    '#831843'
]

// Quick color palette for text - standard vibrant colors
export const TEXT_QUICK_COLORS = [
    '#ef4444', // Red
    '#f97316', // Orange
    '#eab308', // Yellow
    '#84cc16', // Lime
    '#22c55e', // Green
    '#10b981', // Mint
    '#14b8a6', // Teal
    '#06b6d4', // Cyan
    '#3b82f6', // Blue
    '#6366f1', // Indigo
    '#8b5cf6', // Violet
    '#a855f7', // Purple
    '#ec4899', // Pink
    '#f43f5e', // Rose
    '#78716c', // Gray
    '#92400e', // Brown
    '#ffffff', // White
    '#000000' // Black
]

// Quick color palette for background - grayscale shadings
export const BG_QUICK_COLORS = [
    '#18181b', // Dark thick
    '#27272a', // Dark regular
    '#3f3f46', // Dark thin
    '#71717a', // Medium dark
    '#a1a1aa', // Medium
    '#d4d4d8', // Medium light
    '#e4e4e7', // Light thin
    '#f4f4f5', // Light regular
    '#fafafa' // Light thick
    // '#ffffff' // White
]

// Full color palette for expanded picker (8x10 grid)
export const FULL_COLOR_PALETTE = [
    // Row 1: Reds
    '#fef2f2',
    '#fee2e2',
    '#fecaca',
    '#fca5a5',
    '#f87171',
    '#ef4444',
    '#dc2626',
    '#b91c1c',
    '#991b1b',
    '#7f1d1d',
    // Row 2: Oranges
    '#fff7ed',
    '#ffedd5',
    '#fed7aa',
    '#fdba74',
    '#fb923c',
    '#f97316',
    '#ea580c',
    '#c2410c',
    '#9a3412',
    '#7c2d12',
    // Row 3: Yellows
    '#fefce8',
    '#fef9c3',
    '#fef08a',
    '#fde047',
    '#facc15',
    '#eab308',
    '#ca8a04',
    '#a16207',
    '#854d0e',
    '#713f12',
    // Row 4: Greens
    '#f0fdf4',
    '#dcfce7',
    '#bbf7d0',
    '#86efac',
    '#4ade80',
    '#22c55e',
    '#16a34a',
    '#15803d',
    '#166534',
    '#14532d',
    // Row 5: Teals
    '#f0fdfa',
    '#ccfbf1',
    '#99f6e4',
    '#5eead4',
    '#2dd4bf',
    '#14b8a6',
    '#0d9488',
    '#0f766e',
    '#115e59',
    '#134e4a',
    // Row 6: Cyans
    '#ecfeff',
    '#cffafe',
    '#a5f3fc',
    '#67e8f9',
    '#22d3ee',
    '#06b6d4',
    '#0891b2',
    '#0e7490',
    '#155e75',
    '#164e63',
    // Row 7: Blues
    '#eff6ff',
    '#dbeafe',
    '#bfdbfe',
    '#93c5fd',
    '#60a5fa',
    '#3b82f6',
    '#2563eb',
    '#1d4ed8',
    '#1e40af',
    '#1e3a8a',
    // Row 8: Purples
    '#faf5ff',
    '#f3e8ff',
    '#e9d5ff',
    '#d8b4fe',
    '#c084fc',
    '#a855f7',
    '#9333ea',
    '#7e22ce',
    '#6b21a8',
    '#581c87',
    // Row 9: Pinks
    '#fdf2f8',
    '#fce7f3',
    '#fbcfe8',
    '#f9a8d4',
    '#f472b6',
    '#ec4899',
    '#db2777',
    '#be185d',
    '#9d174d',
    '#831843',
    // Row 10: Grays
    '#f9fafb',
    '#f3f4f6',
    '#e5e7eb',
    '#d1d5db',
    '#9ca3af',
    '#6b7280',
    '#4b5563',
    '#374151',
    '#1f2937',
    '#111827'
]
