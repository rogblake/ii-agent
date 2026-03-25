/**
 * Design Inspector Panel Component
 *
 * A panel for editing element properties in Design Mode.
 * Adapted from the Storybook inspector UI.
 */

import {
    type ChangeEvent,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState
} from 'react'
import {
    AlignCenter,
    AlignJustify,
    AlignLeft,
    AlignRight,
    Loader2,
    Square
} from 'lucide-react'
import { Icon } from '@/components/ui/icon'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import axiosInstance from '@/lib/axios'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '@/components/ui/select'
import {
    BORDER_RADIUS,
    FONT_FAMILIES,
    FONT_WEIGHTS,
    FONT_SIZES,
    SPACING
} from '@/components/design-mode/tailwind-constants'
import type { ElementInfo } from '@/components/design-mode/types'

const FONT_SIZE_OPTIONS = [
    { label: 'Xs', value: 12 },
    { label: 'Sm', value: 14 },
    { label: 'Md', value: 16 },
    { label: 'Lg', value: 18 },
    { label: 'Xl', value: 20 },
    { label: '2xl', value: 24 },
    { label: '3xl', value: 30 },
    { label: '4xl', value: 36 },
    { label: '5xl', value: 48 },
    { label: '6xl', value: 60 },
    { label: '7xl', value: 72 },
    { label: '8xl', value: 96 }
]

const OPACITY_OPTIONS = Array.from({ length: 11 }, (_, i) => ({
    label: `${i * 10}%`,
    value: (i / 10).toFixed(1)
}))

const BORDER_WIDTH_OPTIONS = [
    { label: 'None', value: '0px' },
    { label: 'Xs', value: '1px' },
    { label: 'Sm', value: '2px' },
    { label: 'Md', value: '4px' },
    { label: 'Lg', value: '8px' }
]
const BORDER_RADIUS_OPTIONS = [
    { label: 'None', value: 0 },
    { label: 'Xs', value: 4 },
    { label: 'Sm', value: 8 },
    { label: 'Md', value: 12 },
    { label: 'Lg', value: 16 },
    { label: 'Xl', value: 24 },
    { label: 'Full', value: 9999 }
]
const BORDER_STYLE_OPTIONS = ['none', 'solid', 'dashed', 'dotted', 'double']
const SPACING_OPTIONS = [0, 4, 8, 12, 16, 24, 32, 40, 48, 64]
const SHADOW_PRESETS: Array<{ label: string; value: string }> = [
    { label: 'None', value: 'none' },
    { label: 'Small', value: '0 1px 2px 0 rgb(0 0 0 / 0.18)' },
    { label: 'Medium', value: '0 4px 12px rgb(0 0 0 / 0.2)' },
    { label: 'Large', value: '0 12px 32px rgb(0 0 0 / 0.24)' }
]

const STORYBOOK_TEXT_COLORS = [
    '#FF3B30',
    '#FF9500',
    '#FFCC00',
    '#34C759',
    '#00C7BE',
    '#30B0C7',
    '#32ADE6',
    '#007AFF',
    '#5856D6',
    '#AF52DE',
    '#FF2D55',
    '#A2845E',
    '#FFFFFF',
    '#000000',
    '#AEAEB2',
    '#BEE6F0'
]

const TEXT_EDITABLE_TAGS = new Set([
    'p',
    'span',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'li',
    'a',
    'button',
    'label',
    'blockquote',
    'figcaption'
])

type StyleChangeGroup = {
    groupId: string
    groupLabel?: string
}

interface DesignInspectorPanelProps {
    selectedElement: ElementInfo | null
    onStyleChange: (
        property: string,
        value: string,
        options?: StyleChangeGroup
    ) => void
    onTextChange: (text: string) => void
    className?: string
    sessionId?: string
}

function parsePx(value: string | undefined): number {
    if (!value) return 0
    const match = value.match(/-?\d+(\.\d+)?/)
    if (!match) return 0
    return Number(match[0])
}

function parseBoxShorthand(value: string | undefined): number {
    if (!value) return 0
    const parts = value.split(/\s+/).filter(Boolean)
    const px = parts.map((part) => parsePx(part))
    return px[0] ?? 0
}

function extractBackgroundUrl(value: string | undefined): string {
    if (!value || value === 'none') return ''
    const match = value.match(/url\(("|')?(.*?)\1\)/)
    return match?.[2] ?? ''
}

function clampNumber(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value))
}

function parseBackgroundPosition(value: string | undefined): {
    x: number
    y: number
} {
    if (!value) return { x: 50, y: 50 }
    const parts = value
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((part) => part.toLowerCase())

    const parseToken = (token: string | undefined, axis: 'x' | 'y') => {
        if (!token) return null
        const percentMatch = token.match(/(-?\d+(\.\d+)?)%/)
        if (percentMatch) return clampNumber(Number(percentMatch[1]), 0, 100)
        if (token === 'center') return 50
        if (axis === 'x') {
            if (token === 'left') return 0
            if (token === 'right') return 100
        }
        if (axis === 'y') {
            if (token === 'top') return 0
            if (token === 'bottom') return 100
        }
        return null
    }

    const horizontal = new Set(['left', 'center', 'right'])
    const vertical = new Set(['top', 'center', 'bottom'])

    if (parts.length === 1) {
        const token = parts[0]
        const x = parseToken(token, 'x')
        const y = parseToken(token, 'y')
        if (x !== null && y !== null) return { x, y }
        if (x !== null) return { x, y: 50 }
        if (y !== null) return { x: 50, y }
        return { x: 50, y: 50 }
    }

    let first = parts[0]
    let second = parts[1]

    const firstIsVerticalOnly = vertical.has(first) && !horizontal.has(first)
    const secondIsHorizontalOnly =
        horizontal.has(second) && !vertical.has(second)
    if (firstIsVerticalOnly && secondIsHorizontalOnly) {
        ;[first, second] = [second, first]
    }

    const x = parseToken(first, 'x') ?? 50
    const y = parseToken(second, 'y') ?? 50
    return { x, y }
}

function parseBackgroundSizePercent(value: string | undefined): number | null {
    if (!value) return null
    if (value.includes('cover') || value.includes('contain')) return null
    const match = value.match(/(-?\d+(\.\d+)?)%/)
    return match ? Number(match[1]) : null
}

const COLOR_TOKEN_REGEX = /(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)|hsla?\([^)]+\))/

// Helper to extract hex and opacity from css color
function extractColorAndOpacity(color: string): {
    hex: string
    opacity: string
} {
    if (!color || color === 'transparent')
        return { hex: '#ffffff', opacity: '0.0' }
    if (color.startsWith('#')) {
        if (color.length === 9) {
            // #RRGGBBAA
            const alpha = parseInt(color.slice(7), 16) / 255
            // If fully transparent, default to white
            if (alpha === 0) {
                return { hex: '#ffffff', opacity: '0.0' }
            }
            return { hex: color.slice(0, 7), opacity: alpha.toFixed(1) }
        }
        return { hex: color, opacity: '1.0' }
    }
    const matches = color.match(/(\d+(\.\d+)?)/g)
    if (!matches || matches.length < 3)
        return { hex: '#ffffff', opacity: '1.0' }

    const [r, g, b, a] = matches
    const toHex = (value: string) =>
        Math.max(0, Math.min(255, parseInt(value, 10)))
            .toString(16)
            .padStart(2, '0')
    const hex = `#${toHex(r)}${toHex(g)}${toHex(b)}`
    const opacity = a !== undefined ? parseFloat(a).toFixed(1) : '1.0'

    // If fully transparent (opacity 0), default to white
    if (opacity === '0.0') {
        return { hex: '#ffffff', opacity: '0.0' }
    }

    return { hex, opacity }
}

// Helper to combine hex and opacity
function combineColorAndOpacity(hex: string, opacity: string): string {
    if (opacity === '1.0') return hex
    const alpha = Math.round(parseFloat(opacity) * 255)
        .toString(16)
        .padStart(2, '0')
    return `${hex}${alpha}`
}

function splitCssLayers(value: string): string[] {
    if (!value) return []
    const layers: string[] = []
    let current = ''
    let depth = 0

    for (let i = 0; i < value.length; i += 1) {
        const char = value[i]
        if (char === '(') depth += 1
        if (char === ')') depth = Math.max(0, depth - 1)
        if (char === ',' && depth === 0) {
            const trimmed = current.trim()
            if (trimmed) layers.push(trimmed)
            current = ''
            continue
        }
        current += char
    }

    const trimmed = current.trim()
    if (trimmed) layers.push(trimmed)
    return layers
}

function extractColorToken(value: string): string | null {
    const match = value.match(COLOR_TOKEN_REGEX)
    return match?.[1] ?? null
}

function normalizeColorToHex(value: string): string | null {
    if (!value) return null
    const info = extractColorAndOpacity(value.trim())
    return info.hex
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
    const cleaned = hex.replace('#', '')
    if (cleaned.length !== 6) return null
    const r = parseInt(cleaned.slice(0, 2), 16)
    const g = parseInt(cleaned.slice(2, 4), 16)
    const b = parseInt(cleaned.slice(4, 6), 16)
    if ([r, g, b].some((value) => Number.isNaN(value))) return null
    return { r, g, b }
}

function normalizeShadowColor(value: string): string {
    const info = extractColorAndOpacity(value)
    const rgb = hexToRgb(info.hex)
    if (!rgb) return value.trim()
    if (info.opacity === '1.0') {
        return `rgb(${rgb.r},${rgb.g},${rgb.b})`
    }
    const alpha = Number(info.opacity)
    return `rgba(${rgb.r},${rgb.g},${rgb.b},${Number.isNaN(alpha) ? info.opacity : alpha})`
}

function parseLinearGradient(
    value: string
): { from: string; to: string } | null {
    if (!value) return null
    const match = value.match(/linear-gradient\((.*)\)/i)
    if (!match) return null
    const parts = splitCssLayers(match[1])
    if (!parts.length) return null

    let startIndex = 0
    const first = parts[0]?.trim().toLowerCase()
    if (first && (first.endsWith('deg') || first.startsWith('to '))) {
        startIndex = 1
    }

    const fromPart = parts[startIndex]
    const toPart = parts[startIndex + 1]
    if (!fromPart || !toPart) return null

    const fromToken = extractColorToken(fromPart)
    const toToken = extractColorToken(toPart)
    if (!fromToken || !toToken) return null

    const from = normalizeColorToHex(fromToken)
    const to = normalizeColorToHex(toToken)
    if (!from || !to) return null

    return { from, to }
}

function normalizeFontWeight(value: string | undefined): string {
    if (!value) return '400'
    const normalized = value.trim().toLowerCase()
    if (normalized === 'normal') return '400'
    if (normalized === 'bold') return '700'
    const numeric = parseInt(normalized, 10)
    if (!Number.isNaN(numeric)) return String(numeric)
    return '400'
}

function normalizeSingleShadow(value: string): string {
    let working = value.trim()
    if (!working) return ''

    const colorMatch = working.match(COLOR_TOKEN_REGEX)
    let color = ''
    if (colorMatch) {
        color = colorMatch[1]
        working = working.replace(colorMatch[1], '').trim()
    }

    const tokens = working.split(/\s+/).filter(Boolean)
    let inset = ''
    const lengths: string[] = []
    tokens.forEach((token) => {
        if (token.toLowerCase() === 'inset') {
            inset = 'inset'
        } else {
            lengths.push(token)
        }
    })

    const normalizedLengths = lengths
        .map((token) => token.replace(/px/g, '').trim())
        .filter(Boolean)

    while (normalizedLengths.length < 4) {
        normalizedLengths.push('0')
    }

    const normalizedColor = color ? normalizeShadowColor(color) : ''
    return [inset, ...normalizedLengths, normalizedColor]
        .filter(Boolean)
        .join(' ')
}

function normalizeShadowValue(value: string): string {
    if (!value) return 'none'
    const trimmed = value.trim()
    if (trimmed === 'none') return 'none'
    const layers = splitCssLayers(trimmed)
    const normalizedLayers = layers
        .map((layer) => normalizeSingleShadow(layer))
        .filter(Boolean)
    return normalizedLayers.length ? normalizedLayers.join(', ') : 'none'
}

function isPaletteColor(value: string, palette: string[]): boolean {
    const normalized = value.trim().toUpperCase()
    return palette.some((color) => color.toUpperCase() === normalized)
}

const TEXT_GRADIENT_ANGLE = '90deg'
const BACKGROUND_GRADIENT_ANGLE = '135deg'
const DEFAULT_TEXT_GRADIENT = { from: '#a6ffff', to: '#bee6f0' }
const DEFAULT_BG_GRADIENT = { from: '#0f1412', to: '#1a2220' }
const DEFAULT_BORDER_GRADIENT = { from: '#a6ffff', to: '#65e3d3' }
const TEXT_CLIP_HELPER_LAYER =
    'linear-gradient(0deg, rgba(0,0,0,0), rgba(0,0,0,0))'

function buildLinearGradient(angle: string, from: string, to: string): string {
    return `linear-gradient(${angle}, ${from}, ${to})`
}

function composeBackgroundImage(
    layers: Array<string | null | undefined>
): string {
    const filtered = layers
        .map((layer) => (layer ?? '').trim())
        .filter((layer) => layer && layer !== 'none')
    return filtered.length ? filtered.join(', ') : 'none'
}

export function DesignInspectorPanel({
    selectedElement,
    onStyleChange,
    onTextChange,
    className,
    sessionId
}: DesignInspectorPanelProps) {
    const contentRef = useRef<HTMLDivElement | null>(null)
    const typographyRef = useRef<HTMLDivElement | null>(null)
    const textColorRef = useRef<HTMLDivElement | null>(null)
    const backgroundRef = useRef<HTMLDivElement | null>(null)
    const borderRef = useRef<HTMLDivElement | null>(null)
    const spacingRef = useRef<HTMLDivElement | null>(null)
    const shadowRef = useRef<HTMLDivElement | null>(null)
    const fileInputRef = useRef<HTMLInputElement | null>(null)

    const [fontFamily, setFontFamily] = useState('')
    const [textContent, setTextContent] = useState('')
    const [fontSize, setFontSize] = useState(FONT_SIZES.default)
    const [fontWeight, setFontWeight] = useState('400')
    const [lineHeight, setLineHeight] = useState('1.5')
    const [letterSpacing, setLetterSpacing] = useState('0')
    const [textAlign, setTextAlign] = useState('left')
    const [textColor, setTextColor] = useState('#ffffff')
    const [textColorMode, setTextColorMode] = useState<
        'solid' | 'custom' | 'gradient'
    >('solid')
    const [textGradient, setTextGradient] = useState(DEFAULT_TEXT_GRADIENT)
    const [bgColor, setBgColor] = useState('#ffffff')
    const [bgColorMode, setBgColorMode] = useState<
        'solid' | 'custom' | 'gradient'
    >('solid')
    const [bgGradient, setBgGradient] = useState(DEFAULT_BG_GRADIENT)
    const [borderColor, setBorderColor] = useState('#ffffff')
    const [borderColorMode, setBorderColorMode] = useState<
        'solid' | 'custom' | 'gradient'
    >('solid')
    const [borderGradient, setBorderGradient] = useState(
        DEFAULT_BORDER_GRADIENT
    )
    const [borderWidth, setBorderWidth] = useState('1px')
    const [borderStyle, setBorderStyle] = useState('solid')
    const [borderRadius, setBorderRadius] = useState(BORDER_RADIUS.default)
    const [padding, setPadding] = useState(SPACING.default)
    const [margin, setMargin] = useState(SPACING.default)
    const [shadow, setShadow] = useState(SHADOW_PRESETS[0].value)
    const [backgroundTab, setBackgroundTab] = useState<'color' | 'image'>(
        'color'
    )
    const [backgroundImageTab, setBackgroundImageTab] = useState<
        'upload' | 'link' | 'prompt'
    >('upload')
    const [imagePrompt, setImagePrompt] = useState('')
    const [backgroundImageUrl, setBackgroundImageUrl] = useState('')
    const [backgroundImageInput, setBackgroundImageInput] = useState('')
    const backgroundImageDirtyRef = useRef(false)
    const backgroundImageDebounceRef = useRef<number | null>(null)
    const [isUploadingBackground, setIsUploadingBackground] = useState(false)
    const [backgroundCropZoom, setBackgroundCropZoom] = useState(1)
    const [backgroundCropPosition, setBackgroundCropPosition] = useState({
        x: 50,
        y: 50
    })
    const [backgroundImageNaturalSize, setBackgroundImageNaturalSize] =
        useState<{
            width: number
            height: number
        } | null>(null)
    const backgroundCropGroupRef = useRef<StyleChangeGroup | null>(null)
    const backgroundCropDragRef = useRef<{
        pointerId: number
        startClientX: number
        startClientY: number
        startXPercent: number
        startYPercent: number
        containerWidth: number
        containerHeight: number
    } | null>(null)
    const backgroundCropHasUserAdjustedRef = useRef(false)
    const [activeRail, setActiveRail] = useState('content')
    const [decorations, setDecorations] = useState<
        Set<'underline' | 'line-through' | 'overline'>
    >(new Set())
    const [isItalic, setIsItalic] = useState(false)
    const [isBold, setIsBold] = useState(false)
    const [textTransform, setTextTransform] = useState('none')

    const [textOpacity, setTextOpacity] = useState('1.0')
    const [bgOpacity, setBgOpacity] = useState('1.0')
    const [borderOpacity, setBorderOpacity] = useState('1.0')
    const [isGeneratingBackground, setIsGeneratingBackground] = useState(false)
    const selectedElementWasTextGradientRef = useRef(false)
    const clearedTextGradientRef = useRef(false)
    const textGradientLayerRef = useRef<string | null>(null)
    const selectedElementHadBgGradientRef = useRef(false)
    const selectedElementHadBorderGradientRef = useRef(false)

    const buildStyleGroup = useCallback((label: string): StyleChangeGroup => {
        return {
            groupId: `ui-${Date.now()}-${Math.floor(Math.random() * 1000000)}`,
            groupLabel: label
        }
    }, [])

    const applyStyleBatch = useCallback(
        (
            label: string,
            updates: Array<{ property: string; value: string }>,
            group?: StyleChangeGroup
        ) => {
            const groupMeta = group ?? buildStyleGroup(label)
            updates.forEach((update) => {
                onStyleChange(update.property, update.value, groupMeta)
            })
        },
        [buildStyleGroup, onStyleChange]
    )

    function findClosestFontSize(px: number): number {
        const closest = FONT_SIZE_OPTIONS.reduce((prev, curr) => {
            return Math.abs(curr.value - px) < Math.abs(prev.value - px)
                ? curr
                : prev
        })

        // If within 1px, snap to the option
        if (Math.abs(closest.value - px) <= 1) {
            return closest.value
        }
        return px
    }

    // Track original values to avoid triggering changes when nothing changed
    const originalTextContentRef = useRef('')
    const originalLineHeightRef = useRef('')
    const originalLetterSpacingRef = useRef('')

    useEffect(() => {
        if (!selectedElement) return

        const styles = selectedElement.computedStyles
        const sizePx = parsePx(styles.fontSize)

        const initialTextContent = selectedElement.textContent || ''
        setTextContent(initialTextContent)
        originalTextContentRef.current = initialTextContent

        const computedFontFamily = styles.fontFamily || ''
        if (computedFontFamily) {
            const found = FONT_FAMILIES.find((font) =>
                computedFontFamily
                    .toLowerCase()
                    .includes(font.value.split(',')[0].toLowerCase().trim())
            )
            setFontFamily(found?.value || computedFontFamily)
        } else {
            setFontFamily('')
        }

        if (styles.fontSize) {
            const parsed = parsePx(styles.fontSize)
            const snapped = findClosestFontSize(parsed)
            setFontSize(
                Math.max(FONT_SIZES.min, Math.min(FONT_SIZES.max, snapped))
            )
        } else {
            setFontSize(FONT_SIZES.default)
        }

        const normalizedWeight = normalizeFontWeight(styles.fontWeight)
        setFontWeight(normalizedWeight)
        setIsBold(Number(normalizedWeight) >= 600)

        let initialLineHeight = '1.5'
        if (styles.lineHeight) {
            if (styles.lineHeight.includes('px') && sizePx) {
                const ratio = parsePx(styles.lineHeight) / sizePx
                initialLineHeight = ratio
                    .toFixed(2)
                    .replace(/0+$/, '')
                    .replace(/\.$/, '')
            } else {
                initialLineHeight = styles.lineHeight
            }
        }
        setLineHeight(initialLineHeight)
        originalLineHeightRef.current = initialLineHeight

        let initialLetterSpacing = '0'
        if (styles.letterSpacing) {
            const ls = styles.letterSpacing
            if (ls === 'normal') {
                initialLetterSpacing = '0'
            } else if (ls.endsWith('px') && sizePx) {
                const em = parsePx(ls) / sizePx
                initialLetterSpacing = Number.isFinite(em)
                    ? em.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
                    : '0'
            } else if (ls.endsWith('em')) {
                initialLetterSpacing = String(parsePx(ls))
            }
        }
        setLetterSpacing(initialLetterSpacing)
        originalLetterSpacingRef.current = initialLetterSpacing

        if (styles.textAlign) {
            const align = styles.textAlign.toLowerCase()
            if (['left', 'center', 'right', 'justify'].includes(align)) {
                setTextAlign(align)
            } else {
                setTextAlign('left')
            }
        } else {
            setTextAlign('left')
        }

        setIsItalic((styles.fontStyle || '').toLowerCase() === 'italic')
        setTextTransform((styles.textTransform || 'none').toLowerCase())

        const deco = (styles.textDecorationLine || '').toLowerCase()
        const nextDecorations = new Set<
            'underline' | 'line-through' | 'overline'
        >()
        if (deco.includes('underline')) nextDecorations.add('underline')
        if (deco.includes('line-through')) nextDecorations.add('line-through')
        if (deco.includes('overline')) nextDecorations.add('overline')
        setDecorations(nextDecorations)

        const textInfo = extractColorAndOpacity(styles.color)
        setTextColor(textInfo.hex)
        setTextOpacity(textInfo.opacity)

        const bgInfo = extractColorAndOpacity(styles.backgroundColor)
        setBgColor(bgInfo.hex)
        setBgOpacity(bgInfo.opacity)

        const borderStyleValue = (styles.borderStyle || 'none')
            .toLowerCase()
            .split(' ')[0]
        const borderWidthPx = parseBoxShorthand(styles.borderWidth)
        const borderWidthValue = `${borderWidthPx}px`
        const hasBorder = borderStyleValue !== 'none' && borderWidthPx > 0

        let borderInfo = { hex: '#ffffff', opacity: '0.0' }
        if (hasBorder) {
            borderInfo = extractColorAndOpacity(styles.borderColor || '')
            setBorderColor(borderInfo.hex)
            setBorderOpacity(borderInfo.opacity)
        } else {
            setBorderColor('#ffffff')
            setBorderOpacity('0.0')
        }

        const borderImageSource = styles.borderImageSource || ''
        const hasBorderGradient =
            Boolean(borderImageSource) && /gradient/i.test(borderImageSource)
        selectedElementHadBorderGradientRef.current = hasBorderGradient
        if (hasBorderGradient) {
            const parsedBorderGradient = parseLinearGradient(borderImageSource)
            setBorderColorMode('gradient')
            setBorderGradient(parsedBorderGradient ?? DEFAULT_BORDER_GRADIENT)
        } else {
            const isBorderCustom =
                hasBorder &&
                isPaletteColor(borderInfo.hex, STORYBOOK_TEXT_COLORS)
            setBorderColorMode(isBorderCustom ? 'custom' : 'solid')
            setBorderGradient(DEFAULT_BORDER_GRADIENT)
        }

        setBorderStyle(borderStyleValue)
        setBorderWidth(borderWidthValue)

        setPadding(parseBoxShorthand(styles.padding))
        setMargin(parseBoxShorthand(styles.margin))

        const radiusMatch = styles.borderRadius?.match(/(\d+)/)
        if (radiusMatch) {
            setBorderRadius(
                Math.max(
                    BORDER_RADIUS.min,
                    Math.min(BORDER_RADIUS.max, parseInt(radiusMatch[1], 10))
                )
            )
        } else {
            setBorderRadius(BORDER_RADIUS.default)
        }

        const bgImage = styles.backgroundImage || ''
        const layers = splitCssLayers(bgImage).filter(
            (layer) => layer && layer !== 'none'
        )
        const gradientLayers = layers.filter((layer) => /gradient/i.test(layer))
        const backgroundClipValue = (
            styles.backgroundClip ||
            styles.webkitBackgroundClip ||
            ''
        ).toLowerCase()
        const textFillValue = (styles.webkitTextFillColor || '').toLowerCase()
        const hasTextClip = backgroundClipValue.includes('text')
        const textFillTransparent =
            textFillValue.includes('transparent') ||
            textFillValue.includes('rgba(0,0,0,0)') ||
            textFillValue.includes('rgba(0, 0, 0, 0)')
        const shouldUseOpacityFallback = !backgroundClipValue && !textFillValue
        const isTextGradient =
            gradientLayers.length > 0 &&
            (hasTextClip ||
                textFillTransparent ||
                (shouldUseOpacityFallback && textInfo.opacity === '0.0'))

        selectedElementWasTextGradientRef.current = isTextGradient
        clearedTextGradientRef.current = false
        textGradientLayerRef.current = isTextGradient
            ? (gradientLayers[0] ?? null)
            : null

        if (isTextGradient) {
            const parsedTextGradient = parseLinearGradient(gradientLayers[0])
            setTextColorMode('gradient')
            setTextGradient(parsedTextGradient ?? DEFAULT_TEXT_GRADIENT)
            // When the text is gradient, computed `color` is often transparent; keep a sensible
            // non-transparent opacity in state so switching tabs doesn't make the text disappear.
            setTextOpacity('1.0')
            if (parsedTextGradient?.from) {
                setTextColor(parsedTextGradient.from)
            }
        } else {
            const isTextCustom = isPaletteColor(
                textInfo.hex,
                STORYBOOK_TEXT_COLORS
            )
            setTextColorMode(isTextCustom ? 'custom' : 'solid')
            setTextGradient(DEFAULT_TEXT_GRADIENT)
        }

        const remainingLayers = isTextGradient ? layers.slice(1) : layers
        const backgroundGradientLayer = remainingLayers.find((layer) =>
            /gradient/i.test(layer)
        )
        const backgroundUrlLayer = remainingLayers.find((layer) =>
            /url\(/i.test(layer)
        )

        const parsedBgGradient = backgroundGradientLayer
            ? parseLinearGradient(backgroundGradientLayer)
            : null
        const hasBgGradient =
            Boolean(backgroundGradientLayer) &&
            (!parsedBgGradient || parsedBgGradient.from !== parsedBgGradient.to)
        selectedElementHadBgGradientRef.current = hasBgGradient
        if (hasBgGradient) {
            setBgColorMode('gradient')
            setBgGradient(parsedBgGradient ?? DEFAULT_BG_GRADIENT)
        } else {
            const isBackgroundCustom = isPaletteColor(
                bgInfo.hex,
                STORYBOOK_TEXT_COLORS
            )
            setBgColorMode(isBackgroundCustom ? 'custom' : 'solid')
            setBgGradient(DEFAULT_BG_GRADIENT)
        }

        const bgUrl = backgroundUrlLayer
            ? extractBackgroundUrl(backgroundUrlLayer)
            : ''
        if (bgUrl) {
            setBackgroundTab('image')
            setBackgroundImageUrl(bgUrl)
            setBackgroundImageInput(bgUrl)
            backgroundImageDirtyRef.current = false
            if (backgroundImageDebounceRef.current) {
                window.clearTimeout(backgroundImageDebounceRef.current)
                backgroundImageDebounceRef.current = null
            }
        } else {
            setBackgroundTab('color')
            setBackgroundImageUrl('')
            setBackgroundImageInput('')
            backgroundImageDirtyRef.current = false
            if (backgroundImageDebounceRef.current) {
                window.clearTimeout(backgroundImageDebounceRef.current)
                backgroundImageDebounceRef.current = null
            }
        }

        const bs = styles.boxShadow || 'none'
        const normalizedShadow = normalizeShadowValue(bs)
        const preset = SHADOW_PRESETS.find(
            (item) => normalizeShadowValue(item.value) === normalizedShadow
        )
        setShadow(preset?.value ?? bs)
    }, [selectedElement])

    const handleTextContentChange = useCallback(
        (value: string) => {
            setTextContent(value)
            // Apply changes directly when text changes
            onTextChange(value)
            originalTextContentRef.current = value
        },
        [onTextChange]
    )

    const handleTextContentBlur = useCallback(() => {
        // Only trigger change if text actually changed
        if (textContent !== originalTextContentRef.current) {
            onTextChange(textContent)
            originalTextContentRef.current = textContent
        }
    }, [onTextChange, textContent])

    const handleFontFamilyChange = useCallback(
        (value: string) => {
            setFontFamily(value)
            onStyleChange('font-family', value)
        },
        [onStyleChange]
    )

    const handleFontSizeChange = useCallback(
        (value: string) => {
            const next = Number(value)
            setFontSize(next)
            onStyleChange('font-size', `${next}px`)
        },
        [onStyleChange]
    )

    const handleFontWeightChange = useCallback(
        (value: string) => {
            setFontWeight(value)
            setIsBold(Number(value) >= 600)
            onStyleChange('font-weight', value)
        },
        [onStyleChange]
    )

    const handleLineHeightBlur = useCallback(() => {
        const next = lineHeight.trim()
        // Only trigger change if value actually changed
        if (next !== originalLineHeightRef.current) {
            onStyleChange('line-height', next)
            originalLineHeightRef.current = next
        }
    }, [lineHeight, onStyleChange])

    const handleLineHeightChange = useCallback(
        (value: string) => {
            setLineHeight(value)
            // Apply changes directly when value changes
            const next = value.trim()
            if (next) {
                onStyleChange('line-height', next)
                originalLineHeightRef.current = next
            }
        },
        [onStyleChange]
    )

    const handleLetterSpacingBlur = useCallback(() => {
        const next = letterSpacing.trim()
        // Only trigger change if value actually changed
        if (next !== originalLetterSpacingRef.current) {
            if (!next) {
                onStyleChange('letter-spacing', '')
            } else {
                onStyleChange('letter-spacing', `${next}em`)
            }
            originalLetterSpacingRef.current = next
        }
    }, [letterSpacing, onStyleChange])

    const handleLetterSpacingChange = useCallback(
        (value: string) => {
            setLetterSpacing(value)
            // Apply changes directly when value changes
            const next = value.trim()
            if (!next) {
                onStyleChange('letter-spacing', '')
            } else {
                onStyleChange('letter-spacing', `${next}em`)
            }
            originalLetterSpacingRef.current = next
        },
        [onStyleChange]
    )

    const handleTextAlignChange = useCallback(
        (value: string) => {
            setTextAlign(value)
            onStyleChange('text-align', value)
        },
        [onStyleChange]
    )

    const applyTextGradient = useCallback(
        (from: string, to: string, group?: StyleChangeGroup) => {
            const textLayer = buildLinearGradient(TEXT_GRADIENT_ANGLE, from, to)
            textGradientLayerRef.current = textLayer
            selectedElementWasTextGradientRef.current = true
            clearedTextGradientRef.current = false
            let backgroundLayer = 'none'
            if (bgColorMode === 'gradient') {
                backgroundLayer = buildLinearGradient(
                    BACKGROUND_GRADIENT_ANGLE,
                    bgGradient.from,
                    bgGradient.to
                )
            } else if (backgroundImageUrl) {
                backgroundLayer = `url("${backgroundImageUrl}")`
            } else if (bgOpacity !== '0.0') {
                // Add a transparent helper layer so `background-color` uses the last
                // `background-clip` value (border-box) instead of being clipped to text.
                backgroundLayer = TEXT_CLIP_HELPER_LAYER
            }
            const backgroundImageValue = composeBackgroundImage([
                textLayer,
                backgroundLayer
            ])
            applyStyleBatch(
                'Text gradient',
                [
                    {
                        property: 'background-image',
                        value: backgroundImageValue
                    },
                    { property: 'background-clip', value: 'text, border-box' },
                    {
                        property: '-webkit-background-clip',
                        value: 'text, border-box'
                    },
                    {
                        property: '-webkit-text-fill-color',
                        value: 'transparent'
                    },
                    { property: 'color', value: 'transparent' }
                ],
                group
            )
        },
        [
            applyStyleBatch,
            bgColor,
            bgColorMode,
            bgGradient,
            bgOpacity,
            backgroundImageUrl
        ]
    )

    const clearTextGradient = useCallback(
        (group?: StyleChangeGroup, preserveBackground?: boolean) => {
            // Determine what to set for background-image
            let bgImageValue = 'none'
            if (preserveBackground) {
                if (bgColorMode === 'gradient') {
                    bgImageValue = buildLinearGradient(
                        BACKGROUND_GRADIENT_ANGLE,
                        bgGradient.from,
                        bgGradient.to
                    )
                } else if (backgroundImageUrl) {
                    bgImageValue = `url("${backgroundImageUrl}")`
                }
            }

            applyStyleBatch(
                'Text gradient',
                [
                    { property: 'background-image', value: bgImageValue },
                    // Force-disable text clipping even when classes like `bg-clip-text` are present.
                    { property: 'background-clip', value: 'border-box' },
                    {
                        property: '-webkit-background-clip',
                        value: 'border-box'
                    },
                    // Ensure Safari uses `color` again.
                    {
                        property: '-webkit-text-fill-color',
                        value: 'currentColor'
                    }
                ],
                group
            )
        },
        [applyStyleBatch, bgColorMode, bgGradient, backgroundImageUrl]
    )

    const handleTextColorChange = useCallback(
        (value: string) => {
            setTextColor(value)
            if (textColorMode === 'gradient') return

            const group = buildStyleGroup('Text color')
            if (
                !clearedTextGradientRef.current &&
                selectedElementWasTextGradientRef.current
            ) {
                clearTextGradient(group, true)
                clearedTextGradientRef.current = true
            }

            const nextOpacity = textOpacity === '0.0' ? '1.0' : textOpacity
            if (nextOpacity !== textOpacity) {
                setTextOpacity(nextOpacity)
            }
            onStyleChange(
                'color',
                combineColorAndOpacity(value, nextOpacity),
                group
            )
        },
        [
            buildStyleGroup,
            clearTextGradient,
            onStyleChange,
            textColorMode,
            textOpacity
        ]
    )

    const handleTextOpacityChange = useCallback(
        (value: string) => {
            setTextOpacity(value)
            // Only apply color opacity change - don't modify global opacity
            if (textColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }

            const group = buildStyleGroup('Text color')
            if (
                !clearedTextGradientRef.current &&
                selectedElementWasTextGradientRef.current
            ) {
                clearTextGradient(group, true)
                clearedTextGradientRef.current = true
            }

            onStyleChange(
                'color',
                combineColorAndOpacity(textColor, value),
                group
            )
        },
        [
            buildStyleGroup,
            clearTextGradient,
            onStyleChange,
            textColor,
            textColorMode
        ]
    )

    const handleTextColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            if (value === textColorMode) return
            setTextColorMode(value)
            // Switching tabs should not apply changes automatically.
            // Keep a non-transparent opacity in state for non-gradient modes.
            if (value !== 'gradient' && textOpacity === '0.0') {
                setTextOpacity('1.0')
            }
        },
        [textColorMode, textOpacity]
    )

    const handleTextGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setTextGradient(next)
            if (textColorMode === 'gradient') {
                applyTextGradient(
                    next.from,
                    next.to,
                    buildStyleGroup('Text gradient')
                )
            }
        },
        [applyTextGradient, buildStyleGroup, textColorMode]
    )

    const applyBackgroundGradient = useCallback(
        (from: string, to: string, group?: StyleChangeGroup) => {
            selectedElementHadBgGradientRef.current = true
            const backgroundLayer = buildLinearGradient(
                BACKGROUND_GRADIENT_ANGLE,
                from,
                to
            )
            const textLayer =
                textColorMode === 'gradient'
                    ? buildLinearGradient(
                          TEXT_GRADIENT_ANGLE,
                          textGradient.from,
                          textGradient.to
                      )
                    : null
            const backgroundImageValue = composeBackgroundImage([
                textLayer,
                backgroundLayer
            ])
            applyStyleBatch(
                'Background gradient',
                [
                    {
                        property: 'background-image',
                        value: backgroundImageValue
                    },
                    { property: 'background-color', value: 'transparent' }
                ],
                group
            )
        },
        [applyStyleBatch, textColorMode, textGradient]
    )

    const handleBgColorChange = useCallback(
        (value: string) => {
            setBgColor(value)
            if (bgColorMode === 'gradient') return

            // If the current background is fully transparent, make it visible when the user picks a color.
            const nextOpacity = bgOpacity === '0.0' ? '1.0' : bgOpacity
            if (nextOpacity !== bgOpacity) {
                setBgOpacity(nextOpacity)
            }

            const group = buildStyleGroup('Background color')
            const rgba = combineColorAndOpacity(value, nextOpacity)

            // If the element uses gradient text (`bg-clip-text`), `background-color` can appear
            // as if it changes text color. Preserve the text gradient and apply the background
            // as a second layer clipped to the box.
            const shouldTreatAsTextGradient =
                !clearedTextGradientRef.current &&
                (textColorMode === 'gradient' ||
                    selectedElementWasTextGradientRef.current)

            if (shouldTreatAsTextGradient) {
                const textLayer =
                    (textGradientLayerRef.current ||
                        buildLinearGradient(
                            TEXT_GRADIENT_ANGLE,
                            textGradient.from,
                            textGradient.to
                        )) ??
                    'none'
                const helperLayer = TEXT_CLIP_HELPER_LAYER
                const urlLayer = backgroundImageUrl
                    ? `url("${backgroundImageUrl}")`
                    : null
                const clips = urlLayer
                    ? 'text, border-box, border-box'
                    : 'text, border-box'

                applyStyleBatch(
                    'Background color',
                    [
                        {
                            property: 'background-image',
                            value: composeBackgroundImage([
                                textLayer,
                                urlLayer,
                                helperLayer
                            ])
                        },
                        {
                            property: 'background-clip',
                            value: clips
                        },
                        {
                            property: '-webkit-background-clip',
                            value: clips
                        },
                        { property: 'background-color', value: rgba }
                    ],
                    group
                )
                selectedElementHadBgGradientRef.current = false
                return
            }

            if (selectedElementHadBgGradientRef.current) {
                const nextBackgroundImage = backgroundImageUrl
                    ? `url("${backgroundImageUrl}")`
                    : 'none'
                applyStyleBatch(
                    'Background color',
                    [
                        {
                            property: 'background-image',
                            value: nextBackgroundImage
                        },
                        { property: 'background-color', value: rgba }
                    ],
                    group
                )
                selectedElementHadBgGradientRef.current = false
                return
            }

            applyStyleBatch(
                'Background color',
                [{ property: 'background-color', value: rgba }],
                group
            )
        },
        [
            applyStyleBatch,
            backgroundImageUrl,
            bgColorMode,
            bgOpacity,
            buildStyleGroup,
            textColorMode,
            textGradient
        ]
    )

    const handleBgOpacityChange = useCallback(
        (value: string) => {
            setBgOpacity(value)
            // Only apply background-color opacity change - don't modify global opacity
            if (bgColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }
            const group = buildStyleGroup('Background color')
            const rgba = combineColorAndOpacity(bgColor, value)
            const shouldTreatAsTextGradient =
                !clearedTextGradientRef.current &&
                (textColorMode === 'gradient' ||
                    selectedElementWasTextGradientRef.current)

            if (shouldTreatAsTextGradient) {
                const textLayer =
                    (textGradientLayerRef.current ||
                        buildLinearGradient(
                            TEXT_GRADIENT_ANGLE,
                            textGradient.from,
                            textGradient.to
                        )) ??
                    'none'
                const helperLayer = TEXT_CLIP_HELPER_LAYER
                const urlLayer = backgroundImageUrl
                    ? `url("${backgroundImageUrl}")`
                    : null
                const clips = urlLayer
                    ? 'text, border-box, border-box'
                    : 'text, border-box'
                applyStyleBatch(
                    'Background color',
                    [
                        {
                            property: 'background-image',
                            value: composeBackgroundImage([
                                textLayer,
                                urlLayer,
                                helperLayer
                            ])
                        },
                        {
                            property: 'background-clip',
                            value: clips
                        },
                        {
                            property: '-webkit-background-clip',
                            value: clips
                        },
                        { property: 'background-color', value: rgba }
                    ],
                    group
                )
                selectedElementHadBgGradientRef.current = false
                return
            }

            if (selectedElementHadBgGradientRef.current) {
                const nextBackgroundImage = backgroundImageUrl
                    ? `url("${backgroundImageUrl}")`
                    : 'none'
                applyStyleBatch(
                    'Background color',
                    [
                        {
                            property: 'background-image',
                            value: nextBackgroundImage
                        },
                        { property: 'background-color', value: rgba }
                    ],
                    group
                )
                selectedElementHadBgGradientRef.current = false
                return
            }

            onStyleChange('background-color', rgba, group)
        },
        [
            applyStyleBatch,
            backgroundImageUrl,
            bgColor,
            bgColorMode,
            buildStyleGroup,
            onStyleChange,
            textColorMode,
            textGradient
        ]
    )

    const handleBgColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            if (value === bgColorMode) return
            // Switching tabs should not apply changes automatically.
            setBgColorMode(value)
        },
        [bgColorMode]
    )

    const handleBgGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setBgGradient(next)
            if (bgColorMode === 'gradient') {
                applyBackgroundGradient(
                    next.from,
                    next.to,
                    buildStyleGroup('Background gradient')
                )
            }
        },
        [applyBackgroundGradient, buildStyleGroup, bgColorMode]
    )

    const applyBorderGradient = useCallback(
        (from: string, to: string, group?: StyleChangeGroup) => {
            selectedElementHadBorderGradientRef.current = true
            applyStyleBatch(
                'Border gradient',
                [
                    {
                        property: 'border-image',
                        value: `linear-gradient(90deg, ${from}, ${to})`
                    },
                    { property: 'border-image-slice', value: '1' }
                ],
                group
            )
        },
        [applyStyleBatch]
    )

    const handleBorderColorChange = useCallback(
        (value: string) => {
            setBorderColor(value)
            if (borderColorMode === 'gradient') return

            const group = buildStyleGroup('Border color')
            const nextBorderColor = combineColorAndOpacity(value, borderOpacity)

            if (selectedElementHadBorderGradientRef.current) {
                applyStyleBatch(
                    'Border color',
                    [
                        { property: 'border-image', value: 'none' },
                        { property: 'border-image-slice', value: '' },
                        { property: 'border-color', value: nextBorderColor }
                    ],
                    group
                )
                selectedElementHadBorderGradientRef.current = false
                return
            }

            onStyleChange('border-color', nextBorderColor, group)
        },
        [
            applyStyleBatch,
            borderColorMode,
            borderOpacity,
            buildStyleGroup,
            onStyleChange
        ]
    )

    const handleBorderOpacityChange = useCallback(
        (value: string) => {
            setBorderOpacity(value)
            // Only apply border-color opacity change - don't modify global opacity
            if (borderColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }

            const group = buildStyleGroup('Border color')
            const nextBorderColor = combineColorAndOpacity(borderColor, value)

            if (selectedElementHadBorderGradientRef.current) {
                applyStyleBatch(
                    'Border color',
                    [
                        { property: 'border-image', value: 'none' },
                        { property: 'border-image-slice', value: '' },
                        { property: 'border-color', value: nextBorderColor }
                    ],
                    group
                )
                selectedElementHadBorderGradientRef.current = false
                return
            }

            onStyleChange('border-color', nextBorderColor, group)
        },
        [
            applyStyleBatch,
            borderColor,
            borderColorMode,
            buildStyleGroup,
            onStyleChange
        ]
    )

    const handleBorderColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            if (value === borderColorMode) return
            // Switching tabs should not apply changes automatically.
            setBorderColorMode(value)
        },
        [borderColorMode]
    )

    const handleBorderGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setBorderGradient(next)
            if (borderColorMode === 'gradient') {
                applyBorderGradient(
                    next.from,
                    next.to,
                    buildStyleGroup('Border gradient')
                )
            }
        },
        [applyBorderGradient, buildStyleGroup, borderColorMode]
    )

    const handleBorderRadiusChange = useCallback(
        (value: string) => {
            const next = Math.max(
                BORDER_RADIUS.min,
                Math.min(BORDER_RADIUS.max, parseInt(value || '0', 10))
            )
            setBorderRadius(next)
            onStyleChange('border-radius', `${next}px`)
        },
        [onStyleChange]
    )

    const handleBorderStyleChange = useCallback(
        (value: string) => {
            setBorderStyle(value)
            onStyleChange('border-style', value)
        },
        [onStyleChange]
    )

    const handleBorderWidthChange = useCallback(
        (value: string) => {
            setBorderWidth(value)
            onStyleChange('border-width', value)
        },
        [onStyleChange]
    )

    const handlePaddingChange = useCallback(
        (value: string) => {
            const next = Number(value)
            setPadding(next)
            onStyleChange('padding', `${next}px`)
        },
        [onStyleChange]
    )

    const handleMarginChange = useCallback(
        (value: string) => {
            const next = Number(value)
            setMargin(next)
            onStyleChange('margin', `${next}px`)
        },
        [onStyleChange]
    )

    const handleShadowChange = useCallback(
        (value: string) => {
            setShadow(value)
            onStyleChange('box-shadow', value)
        },
        [onStyleChange]
    )

    const toggleDecoration = useCallback(
        (kind: 'underline' | 'line-through' | 'overline') => {
            setDecorations((prev) => {
                const next = new Set(prev)
                if (next.has(kind)) {
                    next.delete(kind)
                } else {
                    next.add(kind)
                }
                const value =
                    next.size === 0 ? 'none' : Array.from(next).join(' ')
                onStyleChange('text-decoration-line', value)
                return next
            })
        },
        [onStyleChange]
    )

    const handleItalicToggle = useCallback(() => {
        setIsItalic((prev) => {
            const next = !prev
            onStyleChange('font-style', next ? 'italic' : 'normal')
            return next
        })
    }, [onStyleChange])

    const handleBoldToggle = useCallback(() => {
        setIsBold((prev) => {
            const next = !prev
            const nextWeight = next ? '700' : '400'
            setFontWeight(nextWeight)
            onStyleChange('font-weight', nextWeight)
            return next
        })
    }, [onStyleChange])

    const handleTextTransformToggle = useCallback(() => {
        setTextTransform((prev) => {
            const next = prev === 'uppercase' ? 'none' : 'uppercase'
            onStyleChange('text-transform', next)
            return next
        })
    }, [onStyleChange])

    const handleBackgroundTabChange = useCallback(
        (value: 'color' | 'image') => {
            setBackgroundTab(value)
            if (value === 'color') {
                const currentBgImage =
                    selectedElement?.computedStyles?.backgroundImage
                const hasImageOrGradient =
                    (currentBgImage && currentBgImage !== 'none') ||
                    !!backgroundImageUrl

                if (bgColorMode !== 'gradient' && !hasImageOrGradient) {
                    return
                }

                if (bgColorMode === 'gradient') {
                    applyBackgroundGradient(
                        bgGradient.from,
                        bgGradient.to,
                        buildStyleGroup('Background gradient')
                    )
                    return
                }
                setBackgroundImageUrl('')
                setBackgroundImageInput('')

                // Determine background-image value - preserve text gradient if active
                const textLayer =
                    textColorMode === 'gradient'
                        ? buildLinearGradient(
                              TEXT_GRADIENT_ANGLE,
                              textGradient.from,
                              textGradient.to
                          )
                        : null
                const helperLayer =
                    textLayer && bgOpacity !== '0.0'
                        ? TEXT_CLIP_HELPER_LAYER
                        : null
                const bgImageValue = composeBackgroundImage([
                    textLayer,
                    helperLayer
                ])

                applyStyleBatch('Background color', [
                    { property: 'background-image', value: bgImageValue },
                    {
                        property: 'background-color',
                        value: combineColorAndOpacity(bgColor, bgOpacity)
                    }
                ])
            }
        },
        [
            applyBackgroundGradient,
            applyStyleBatch,
            backgroundImageUrl,
            bgColor,
            bgColorMode,
            bgGradient,
            bgOpacity,
            buildStyleGroup,
            selectedElement,
            textColorMode,
            textGradient
        ]
    )

    const handleBackgroundImageApply = useCallback(
        (url: string) => {
            const label = 'Background image'
            if (!url) {
                setBackgroundImageUrl('')
                setBackgroundCropZoom(1)
                setBackgroundCropPosition({ x: 50, y: 50 })
                setBackgroundImageNaturalSize(null)
                backgroundCropGroupRef.current = null
                backgroundCropDragRef.current = null

                if (bgColorMode === 'gradient') {
                    applyBackgroundGradient(
                        bgGradient.from,
                        bgGradient.to,
                        buildStyleGroup('Background gradient')
                    )
                    return
                }

                // Determine background-image value - preserve text gradient if active
                const textLayer =
                    textColorMode === 'gradient'
                        ? buildLinearGradient(
                              TEXT_GRADIENT_ANGLE,
                              textGradient.from,
                              textGradient.to
                          )
                        : null
                const helperLayer =
                    textLayer && bgOpacity !== '0.0'
                        ? TEXT_CLIP_HELPER_LAYER
                        : null
                const bgImageValue = composeBackgroundImage([
                    textLayer,
                    helperLayer
                ])

                applyStyleBatch(label, [
                    { property: 'background-image', value: bgImageValue }
                ])
                return
            }
            setBackgroundImageUrl(url)
            setBackgroundCropZoom(1)
            setBackgroundCropPosition({ x: 50, y: 50 })
            setBackgroundImageNaturalSize(null)
            backgroundCropGroupRef.current = null
            backgroundCropDragRef.current = null
            const textLayer =
                textColorMode === 'gradient'
                    ? buildLinearGradient(
                          TEXT_GRADIENT_ANGLE,
                          textGradient.from,
                          textGradient.to
                      )
                    : null
            const bgImageValue = composeBackgroundImage([
                textLayer,
                `url("${url}")`
            ])
            applyStyleBatch(label, [
                { property: 'background-image', value: bgImageValue },
                { property: 'background-size', value: 'cover' },
                { property: 'background-position', value: 'center' },
                { property: 'background-repeat', value: 'no-repeat' }
            ])
        },
        [
            applyBackgroundGradient,
            applyStyleBatch,
            bgColorMode,
            bgGradient,
            bgOpacity,
            buildStyleGroup,
            textColorMode,
            textGradient
        ]
    )

    const handleAIGenerateBackground = useCallback(async () => {
        if (!imagePrompt.trim() || isGeneratingBackground) return
        if (!sessionId) {
            toast.error('Missing session ID.')
            return
        }

        setIsGeneratingBackground(true)
        try {
            const rect = selectedElement?.rect
            const ratio =
                rect && rect.width > 0 && rect.height > 0
                    ? rect.width / rect.height
                    : 1
            const aspectRatio =
                ratio > 1.3
                    ? ('16:9' as const)
                    : ratio < 0.77
                      ? ('9:16' as const)
                      : ratio > 1.05
                        ? ('4:3' as const)
                        : ratio < 0.95
                          ? ('3:4' as const)
                          : ('1:1' as const)

            const response = await axiosInstance.post(
                '/media/reference-image',
                {
                    prompt: imagePrompt,
                    type: 'scene',
                    session_id: sessionId,
                    aspect_ratio: aspectRatio
                }
            )

            const data = response?.data as
                | { success?: boolean; url?: string | null; error?: string }
                | undefined

            if (data?.success && data.url) {
                setBackgroundImageInput(data.url)
                handleBackgroundImageApply(data.url)
                toast.success('Background image generated successfully')
            } else {
                toast.error(
                    data?.error || 'Failed to generate background image'
                )
            }
        } catch (error) {
            console.error('AI generate background error:', error)
            toast.error('Failed to generate background image')
        } finally {
            setIsGeneratingBackground(false)
        }
    }, [
        handleBackgroundImageApply,
        imagePrompt,
        isGeneratingBackground,
        selectedElement?.rect,
        sessionId
    ])

    useEffect(() => {
        if (!backgroundImageUrl) {
            setBackgroundImageNaturalSize(null)
            return
        }

        let canceled = false
        const img = new Image()
        img.onload = () => {
            if (canceled) return
            setBackgroundImageNaturalSize({
                width: img.naturalWidth,
                height: img.naturalHeight
            })
        }
        img.onerror = () => {
            if (canceled) return
            setBackgroundImageNaturalSize(null)
        }
        img.src = backgroundImageUrl

        return () => {
            canceled = true
        }
    }, [backgroundImageUrl])

    const backgroundPreviewAspectRatio = useMemo(() => {
        const rect = selectedElement?.rect
        if (rect && rect.width > 0 && rect.height > 0) {
            return rect.width / rect.height
        }
        return 16 / 9
    }, [selectedElement?.rect?.height, selectedElement?.rect?.width])

    const backgroundCoverWidthPercent = useMemo(() => {
        if (!backgroundImageNaturalSize) return 100
        const { width, height } = backgroundImageNaturalSize
        if (width <= 0 || height <= 0) return 100
        const imageAspect = width / height
        if (!Number.isFinite(imageAspect) || imageAspect <= 0) return 100

        const elementAspect = backgroundPreviewAspectRatio
        if (!Number.isFinite(elementAspect) || elementAspect <= 0) return 100

        return Math.max(100, (imageAspect / elementAspect) * 100)
    }, [backgroundImageNaturalSize, backgroundPreviewAspectRatio])

    const backgroundContainWidthPercent = useMemo(() => {
        if (!backgroundImageNaturalSize) return 100
        const { width, height } = backgroundImageNaturalSize
        if (width <= 0 || height <= 0) return 100
        const imageAspect = width / height
        if (!Number.isFinite(imageAspect) || imageAspect <= 0) return 100

        const elementAspect = backgroundPreviewAspectRatio
        if (!Number.isFinite(elementAspect) || elementAspect <= 0) return 100

        return clampNumber((imageAspect / elementAspect) * 100, 0, 100)
    }, [backgroundImageNaturalSize, backgroundPreviewAspectRatio])

    const backgroundCropSizeValue = useMemo(() => {
        const sizePercent = backgroundCoverWidthPercent * backgroundCropZoom
        return `${sizePercent.toFixed(2)}% auto`
    }, [backgroundCoverWidthPercent, backgroundCropZoom])

    const backgroundCropPositionValue = useMemo(() => {
        return `${backgroundCropPosition.x.toFixed(2)}% ${backgroundCropPosition.y.toFixed(2)}%`
    }, [backgroundCropPosition.x, backgroundCropPosition.y])

    const backgroundCropPreviewStyle = useMemo(() => {
        if (!backgroundImageUrl) return {}
        return {
            backgroundImage: `url("${backgroundImageUrl}")`,
            backgroundSize: backgroundCropSizeValue,
            backgroundPosition: backgroundCropPositionValue,
            backgroundRepeat: 'no-repeat'
        }
    }, [
        backgroundCropPositionValue,
        backgroundCropSizeValue,
        backgroundImageUrl
    ])

    const applyBackgroundCropStyles = useCallback(
        (nextZoom: number, nextPosition: { x: number; y: number }) => {
            if (!backgroundImageUrl) return

            const group =
                backgroundCropGroupRef.current ??
                buildStyleGroup('Background crop')
            backgroundCropGroupRef.current = group

            const sizePercent = backgroundCoverWidthPercent * nextZoom
            const sizeValue = `${sizePercent.toFixed(2)}% auto`
            const positionValue = `${nextPosition.x.toFixed(
                2
            )}% ${nextPosition.y.toFixed(2)}%`

            applyStyleBatch(
                'Background crop',
                [
                    { property: 'background-size', value: sizeValue },
                    { property: 'background-position', value: positionValue },
                    { property: 'background-repeat', value: 'no-repeat' }
                ],
                group
            )
        },
        [
            applyStyleBatch,
            backgroundCoverWidthPercent,
            backgroundImageUrl,
            buildStyleGroup
        ]
    )

    const handleBackgroundCropPointerDown = useCallback(
        (event: React.PointerEvent<HTMLDivElement>) => {
            if (!backgroundImageUrl) return
            backgroundCropHasUserAdjustedRef.current = true
            backgroundCropGroupRef.current =
                backgroundCropGroupRef.current ??
                buildStyleGroup('Background crop')

            const rect = event.currentTarget.getBoundingClientRect()
            backgroundCropDragRef.current = {
                pointerId: event.pointerId,
                startClientX: event.clientX,
                startClientY: event.clientY,
                startXPercent: backgroundCropPosition.x,
                startYPercent: backgroundCropPosition.y,
                containerWidth: rect.width,
                containerHeight: rect.height
            }

            event.currentTarget.setPointerCapture(event.pointerId)
            event.preventDefault()
        },
        [
            backgroundCropPosition.x,
            backgroundCropPosition.y,
            backgroundImageUrl,
            buildStyleGroup
        ]
    )

    const handleBackgroundCropPointerMove = useCallback(
        (event: React.PointerEvent<HTMLDivElement>) => {
            const drag = backgroundCropDragRef.current
            if (!drag || drag.pointerId !== event.pointerId) return

            const dx = event.clientX - drag.startClientX
            const dy = event.clientY - drag.startClientY
            const dxPercent = (dx / Math.max(1, drag.containerWidth)) * 100
            const dyPercent = (dy / Math.max(1, drag.containerHeight)) * 100

            const nextPosition = {
                x: clampNumber(drag.startXPercent - dxPercent, 0, 100),
                y: clampNumber(drag.startYPercent - dyPercent, 0, 100)
            }

            setBackgroundCropPosition(nextPosition)
            applyBackgroundCropStyles(backgroundCropZoom, nextPosition)
            event.preventDefault()
        },
        [applyBackgroundCropStyles, backgroundCropZoom]
    )

    const handleBackgroundCropPointerEnd = useCallback(
        (event: React.PointerEvent<HTMLDivElement>) => {
            const drag = backgroundCropDragRef.current
            if (!drag || drag.pointerId !== event.pointerId) return
            backgroundCropDragRef.current = null
            backgroundCropGroupRef.current = null
            try {
                event.currentTarget.releasePointerCapture(event.pointerId)
            } catch {
                // ignore
            }
        },
        []
    )

    const handleBackgroundCropZoomPointerDown = useCallback(() => {
        if (!backgroundImageUrl) return
        backgroundCropHasUserAdjustedRef.current = true
        backgroundCropGroupRef.current = buildStyleGroup('Background crop')
    }, [backgroundImageUrl, buildStyleGroup])

    const handleBackgroundCropZoomPointerEnd = useCallback(() => {
        backgroundCropGroupRef.current = null
    }, [])

    const handleBackgroundCropZoomChange = useCallback(
        (event: ChangeEvent<HTMLInputElement>) => {
            const raw = Number(event.target.value) / 100
            const nextZoom = clampNumber(raw, 0.05, 2.5)
            setBackgroundCropZoom(nextZoom)
            applyBackgroundCropStyles(nextZoom, backgroundCropPosition)
        },
        [applyBackgroundCropStyles, backgroundCropPosition]
    )

    const handleBackgroundCropReset = useCallback(() => {
        const nextPosition = { x: 50, y: 50 }
        const nextZoom = 1
        backgroundCropHasUserAdjustedRef.current = true
        backgroundCropGroupRef.current = buildStyleGroup('Background crop')
        setBackgroundCropPosition(nextPosition)
        setBackgroundCropZoom(nextZoom)
        applyBackgroundCropStyles(nextZoom, nextPosition)
        backgroundCropGroupRef.current = null
    }, [applyBackgroundCropStyles, buildStyleGroup])

    useEffect(() => {
        backgroundCropGroupRef.current = null
        backgroundCropDragRef.current = null
        backgroundCropHasUserAdjustedRef.current = false

        if (!selectedElement) return
        const styles = selectedElement.computedStyles
        setBackgroundCropPosition(
            parseBackgroundPosition(styles.backgroundPosition)
        )
        setBackgroundCropZoom(1)
    }, [selectedElement?.designId])

    useEffect(() => {
        if (!selectedElement) return
        if (!backgroundImageNaturalSize) return
        if (backgroundCropHasUserAdjustedRef.current) return

        const bgImage = selectedElement.computedStyles.backgroundImage || ''
        const layers = splitCssLayers(bgImage).filter(
            (layer) => layer && layer !== 'none'
        )
        const urlLayer = layers.find((layer) => /url\(/i.test(layer))
        const computedUrl = urlLayer ? extractBackgroundUrl(urlLayer) : ''
        if (!computedUrl) return
        if (!backgroundImageUrl) return
        if (computedUrl !== backgroundImageUrl) return

        const size = (
            selectedElement.computedStyles.backgroundSize || ''
        ).toLowerCase()
        if (!size) return
        if (size.includes('contain')) {
            setBackgroundCropZoom(
                clampNumber(
                    backgroundContainWidthPercent / backgroundCoverWidthPercent,
                    0.05,
                    2.5
                )
            )
            return
        }

        const sizePercent = parseBackgroundSizePercent(size)
        if (sizePercent === null) return
        setBackgroundCropZoom(
            clampNumber(sizePercent / backgroundCoverWidthPercent, 0.05, 2.5)
        )
    }, [
        backgroundContainWidthPercent,
        backgroundCoverWidthPercent,
        backgroundImageNaturalSize,
        backgroundImageUrl,
        selectedElement?.designId
    ])

    useEffect(() => {
        if (backgroundImageTab !== 'link') return
        if (!backgroundImageDirtyRef.current) return

        if (backgroundImageDebounceRef.current) {
            window.clearTimeout(backgroundImageDebounceRef.current)
        }

        const timeoutId = window.setTimeout(() => {
            backgroundImageDirtyRef.current = false
            backgroundImageDebounceRef.current = null
            handleBackgroundImageApply(backgroundImageInput.trim())
        }, 400)
        backgroundImageDebounceRef.current = timeoutId

        return () => {
            if (backgroundImageDebounceRef.current) {
                window.clearTimeout(backgroundImageDebounceRef.current)
                backgroundImageDebounceRef.current = null
            }
        }
    }, [backgroundImageInput, backgroundImageTab, handleBackgroundImageApply])

    const handleUploadClick = useCallback(() => {
        fileInputRef.current?.click()
    }, [])

    const handleUploadChange = useCallback(
        async (event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0]
            if (!file) return
            event.target.value = ''

            if (!file.type.startsWith('image/')) {
                toast.error('Please select a valid image file.')
                return
            }

            setIsUploadingBackground(true)
            const reader = new FileReader()
            reader.onload = () => {
                const result =
                    typeof reader.result === 'string' ? reader.result : ''
                if (result) {
                    handleBackgroundImageApply(result)
                    setBackgroundImageInput(result)
                }
                setIsUploadingBackground(false)
            }
            reader.onerror = () => {
                setIsUploadingBackground(false)
                toast.error('Failed to read image file.')
            }
            reader.readAsDataURL(file)
        },
        [handleBackgroundImageApply]
    )

    const showTextControls = useMemo(() => {
        if (!selectedElement) return false
        const tag = (selectedElement.tagName || '').toLowerCase()
        if (selectedElement.attributes?.['data-editable'] === 'text')
            return true
        if (selectedElement.attributes?.contenteditable === 'true') return true
        if (TEXT_EDITABLE_TAGS.has(tag)) return true

        const inner = selectedElement.innerHTML || ''
        const hasChildTags = /<[^>]+>/.test(inner)
        const hasText = Boolean((selectedElement.textContent || '').trim())
        return hasText && !hasChildTags
    }, [selectedElement])

    const railItems = useMemo(() => {
        const items: Array<{
            id: string
            label: string
            iconName?: string
            icon?: typeof Square
            ref: React.RefObject<HTMLDivElement | null>
        }> = []
        if (showTextControls) {
            items.push(
                {
                    id: 'content',
                    label: 'Content',
                    iconName: 'content',
                    ref: contentRef
                },
                {
                    id: 'typography',
                    label: 'Typography',
                    iconName: 'alargesmall',
                    ref: typographyRef
                },
                {
                    id: 'text',
                    label: 'Text Color',
                    iconName: 'textcolor',
                    ref: textColorRef
                }
            )
        }
        items.push(
            {
                id: 'background',
                label: 'Background',
                iconName: 'background-icon',
                ref: backgroundRef
            },
            { id: 'border', label: 'Border', icon: Square, ref: borderRef },
            {
                id: 'spacing',
                label: 'Spacing',
                iconName: 'margin-padding',
                ref: spacingRef
            },
            {
                id: 'shadow',
                label: 'Shadow',
                iconName: 'shadow',
                ref: shadowRef
            }
        )
        return items
    }, [showTextControls])

    const scrollContainerRef = useRef<HTMLDivElement | null>(null)
    const railClickLockRef = useRef<number | null>(null)

    const containerClassName = cn(
        'flex h-full w-full flex-shrink-0 relative overflow-hidden bg-[#181e1c] min-h-0',
        className
    )

    const sectionTitleClassName = 'text-xs font-semibold text-white'
    const fieldLabelClassName = 'text-[13px] text-white'
    const inputClassName =
        '!h-12 w-full rounded-xl border border-white/10 bg-[#202927] px-4 text-sm text-white placeholder:text-white/30 focus-visible:ring-1 focus-visible:ring-[#a6ffff]/40 transition-all'
    const textareaClassName =
        'min-h-[110px] resize-none rounded-xl border border-white/10 bg-[#202927] px-3 py-2 text-sm text-white placeholder:text-white/30 focus-visible:ring-2 focus-visible:ring-[#a6ffff] focus-visible:border-[#a6ffff]'
    const dividerClassName = 'my-4 border-t border-dashed border-white/30'

    useEffect(() => {
        if (showTextControls) {
            setActiveRail('content')
        } else if (
            activeRail === 'content' ||
            activeRail === 'typography' ||
            activeRail === 'text'
        ) {
            setActiveRail('background')
        }
    }, [showTextControls])

    useEffect(() => {
        const container = scrollContainerRef.current
        if (!container) return
        if (!selectedElement) return
        if (railItems.length === 0) return

        let rafId: number | null = null

        const syncActiveRail = () => {
            // Skip scroll-based sync while a rail click is animating
            if (railClickLockRef.current) return

            const containerRect = container.getBoundingClientRect()
            const maxScrollTop = Math.max(
                0,
                container.scrollHeight - container.clientHeight
            )
            const scrollProgress =
                maxScrollTop > 0 ? container.scrollTop / maxScrollTop : 0

            // When scrolled to (near) the bottom, activate the last rail item
            if (scrollProgress > 0.95 && railItems.length > 0) {
                const lastId = railItems[railItems.length - 1].id
                if (lastId !== activeRail) setActiveRail(lastId)
                return
            }

            // Choose the most "in view" section, using intersection ratio.
            // We add a tiny bias toward lower sections as the user scrolls down so
            // short sections near the bottom can still become active.
            let nextActive = railItems[0]?.id
            let bestScore = -1

            for (const item of railItems) {
                const el = item.ref.current
                if (!el) continue

                const rect = el.getBoundingClientRect()
                const visibleHeight =
                    Math.min(rect.bottom, containerRect.bottom) -
                    Math.max(rect.top, containerRect.top)

                if (visibleHeight <= 0 || rect.height <= 0) continue

                const intersectionRatio = visibleHeight / rect.height
                const positionFactor = Math.min(
                    1,
                    Math.max(
                        0,
                        (rect.top - containerRect.top) / containerRect.height
                    )
                )
                const score =
                    intersectionRatio + scrollProgress * positionFactor * 0.01

                if (score > bestScore) {
                    bestScore = score
                    nextActive = item.id
                }
            }

            if (nextActive && nextActive !== activeRail)
                setActiveRail(nextActive)
        }

        const onScroll = () => {
            if (rafId !== null) return
            rafId = window.requestAnimationFrame(() => {
                rafId = null
                syncActiveRail()
            })
        }

        container.addEventListener('scroll', onScroll, { passive: true })
        syncActiveRail()

        return () => {
            container.removeEventListener('scroll', onScroll)
            if (rafId !== null) {
                window.cancelAnimationFrame(rafId)
            }
        }
    }, [activeRail, railItems, selectedElement])

    const renderOpacitySection = (
        value: string,
        onChange: (val: string) => void
    ) => (
        <div className="space-y-1.5">
            <Label className={cn(sectionTitleClassName, 'text-[13px]')}>
                Opacity
            </Label>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className={inputClassName}>
                    <SelectValue placeholder="Select opacity" />
                </SelectTrigger>
                <SelectContent>
                    {OPACITY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    )

    const renderColorSection = (
        label: string,
        mode: 'solid' | 'custom' | 'gradient',
        onModeChange: (value: 'solid' | 'custom' | 'gradient') => void,
        colorValue: string,
        onColorChange: (value: string) => void,
        gradientValue: { from: string; to: string },
        onGradientChange: (value: { from: string; to: string }) => void,
        customPalette: string[]
    ) => {
        const normalizedColorValue = colorValue.trim().toUpperCase()
        return (
            <div className="space-y-4">
                <Label className={cn(sectionTitleClassName, 'text-[13px]')}>
                    {label}
                </Label>
                <div className="grid grid-cols-3 gap-2">
                    {(['solid', 'custom', 'gradient'] as const).map((tab) => (
                        <button
                            key={tab}
                            type="button"
                            onClick={() => onModeChange(tab)}
                            className={cn(
                                'h-12 rounded-xl border text-sm transition-colors',
                                mode === tab
                                    ? 'border-[#a6ffff] bg-[#24302e] text-white font-semibold'
                                    : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30 hover:text-white'
                            )}
                        >
                            {tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    ))}
                </div>

                {mode === 'gradient' ? (
                    <div className="grid grid-cols-2 gap-3">
                        {(['from', 'to'] as const).map((key) => (
                            <div key={key} className="space-y-1.5">
                                <Label className={fieldLabelClassName}>
                                    {key === 'from' ? 'From' : 'To'}
                                </Label>
                                <div className="relative flex items-center">
                                    <div className="absolute left-3 flex items-center pointer-events-none">
                                        <div
                                            className="h-7 w-7 rounded border border-white/20"
                                            style={{
                                                backgroundColor:
                                                    gradientValue[key]
                                            }}
                                        />
                                    </div>
                                    <Input
                                        value={gradientValue[key]
                                            .replace('#', '')
                                            .toUpperCase()}
                                        onChange={(event) => {
                                            let val = event.target.value
                                            if (val && !val.startsWith('#'))
                                                val = '#' + val
                                            onGradientChange({
                                                ...gradientValue,
                                                [key]: val || '#000000'
                                            })
                                        }}
                                        className={cn(inputClassName, 'pl-12')}
                                    />
                                    <input
                                        type="color"
                                        value={gradientValue[key]}
                                        onChange={(event) =>
                                            onGradientChange({
                                                ...gradientValue,
                                                [key]: event.target.value
                                            })
                                        }
                                        className="absolute left-3 h-7 w-7 cursor-pointer opacity-0"
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : mode === 'solid' ? (
                    <div className="relative flex items-center">
                        <div className="absolute left-3 flex items-center pointer-events-none">
                            <div
                                className="h-7 w-7 rounded-md border border-white/20"
                                style={{ backgroundColor: colorValue }}
                            />
                        </div>
                        <Input
                            value={colorValue.replace('#', '').toUpperCase()}
                            onChange={(event) => {
                                let val = event.target.value
                                if (val && !val.startsWith('#')) val = '#' + val
                                onColorChange(val || '#000000')
                            }}
                            className={cn(
                                inputClassName,
                                'pl-12 font-medium tracking-wider'
                            )}
                        />
                        <input
                            type="color"
                            value={colorValue}
                            onChange={(event) =>
                                onColorChange(event.target.value)
                            }
                            className="absolute left-3 h-7 w-7 cursor-pointer opacity-0"
                        />
                    </div>
                ) : (
                    <div className="grid grid-cols-8 gap-2">
                        {customPalette.map((color) => {
                            const normalizedPalette = color.toUpperCase()
                            const isSelected =
                                normalizedPalette === normalizedColorValue
                            return (
                                <button
                                    key={color}
                                    type="button"
                                    onClick={() => onColorChange(color)}
                                    className={cn(
                                        'aspect-square rounded-xl border border-white/10 transition-colors',
                                        isSelected
                                            ? 'ring-2 ring-[#a6ffff] ring-offset-2 ring-offset-[#181e1c]'
                                            : 'hover:border-white/40'
                                    )}
                                    style={{ backgroundColor: color }}
                                    title={color}
                                />
                            )
                        })}
                    </div>
                )}
            </div>
        )
    }

    const panelContent = !selectedElement ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/5">
                <Icon name="content" className="size-5 text-white/40" />
            </div>
            <p className="text-sm text-white/70">No element selected</p>
            <p className="text-xs text-white/40">
                Click on any element in the preview to edit its styles
            </p>
        </div>
    ) : (
        <div className="space-y-4 pr-12">
            {showTextControls && selectedElement.textContent && (
                <div
                    ref={contentRef}
                    className="space-y-2"
                    onClick={() => setActiveRail('content')}
                >
                    <Label className={sectionTitleClassName}>Content</Label>
                    <Textarea
                        value={textContent}
                        onChange={(event) =>
                            handleTextContentChange(event.target.value)
                        }
                        onBlur={handleTextContentBlur}
                        className={textareaClassName}
                        placeholder="Enter text content..."
                    />
                </div>
            )}

            {showTextControls && selectedElement.textContent && (
                <div className={dividerClassName} />
            )}

            {showTextControls && (
                <>
                    <div
                        ref={typographyRef}
                        className="space-y-3"
                        onClick={() => setActiveRail('typography')}
                    >
                        <div className="space-y-1.5">
                            <Label className={sectionTitleClassName}>
                                Font Family
                            </Label>
                            <Select
                                value={fontFamily}
                                onValueChange={handleFontFamilyChange}
                            >
                                <SelectTrigger className={inputClassName}>
                                    <SelectValue placeholder="Select font..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {FONT_FAMILIES.map((font) => (
                                        <SelectItem
                                            key={font.value}
                                            value={font.value}
                                        >
                                            <span
                                                style={{
                                                    fontFamily: font.value
                                                }}
                                            >
                                                {font.label}
                                            </span>
                                        </SelectItem>
                                    ))}
                                    {fontFamily &&
                                        !FONT_FAMILIES.some(
                                            (font) => font.value === fontFamily
                                        ) && (
                                            <SelectItem value={fontFamily}>
                                                <span
                                                    style={{
                                                        fontFamily
                                                    }}
                                                >
                                                    {fontFamily
                                                        .split(',')[0]
                                                        .replace(/['"]/g, '')
                                                        .trim()}
                                                </span>
                                            </SelectItem>
                                        )}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <Label className={fieldLabelClassName}>
                                    Font Weight
                                </Label>
                                <Select
                                    value={fontWeight}
                                    onValueChange={handleFontWeightChange}
                                >
                                    <SelectTrigger className={inputClassName}>
                                        <SelectValue placeholder="Weight" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {FONT_WEIGHTS.filter(
                                            (weight) => weight.value !== ''
                                        ).map((weight) => (
                                            <SelectItem
                                                key={weight.value}
                                                value={weight.value}
                                            >
                                                {weight.label}
                                            </SelectItem>
                                        ))}
                                        {fontWeight &&
                                            !FONT_WEIGHTS.some(
                                                (weight) =>
                                                    weight.value === fontWeight
                                            ) && (
                                                <SelectItem value={fontWeight}>
                                                    {fontWeight}
                                                </SelectItem>
                                            )}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-1.5">
                                <Label className={fieldLabelClassName}>
                                    Font Size
                                </Label>
                                <Select
                                    value={String(fontSize)}
                                    onValueChange={handleFontSizeChange}
                                >
                                    <SelectTrigger className={inputClassName}>
                                        <SelectValue placeholder="Size" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {FONT_SIZE_OPTIONS.map((size) => (
                                            <SelectItem
                                                key={size.value}
                                                value={String(size.value)}
                                            >
                                                {size.label}
                                            </SelectItem>
                                        ))}
                                        {!FONT_SIZE_OPTIONS.some(
                                            (option) =>
                                                option.value === fontSize
                                        ) && (
                                            <SelectItem
                                                value={String(fontSize)}
                                            >
                                                {fontSize}px
                                            </SelectItem>
                                        )}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <Label className={fieldLabelClassName}>
                                    Line Height (rem)
                                </Label>
                                <Input
                                    value={lineHeight}
                                    onChange={(event) =>
                                        handleLineHeightChange(
                                            event.target.value
                                        )
                                    }
                                    onBlur={handleLineHeightBlur}
                                    className={inputClassName}
                                    placeholder="1.75"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className={fieldLabelClassName}>
                                    Letter Spacing (em)
                                </Label>
                                <Input
                                    value={letterSpacing}
                                    onChange={(event) =>
                                        handleLetterSpacingChange(
                                            event.target.value
                                        )
                                    }
                                    onBlur={handleLetterSpacingBlur}
                                    className={inputClassName}
                                    placeholder="0"
                                />
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className={sectionTitleClassName}>
                                Text Alignment
                            </Label>
                            <div className="flex gap-1">
                                {[
                                    { value: 'left', icon: AlignLeft },
                                    { value: 'center', icon: AlignCenter },
                                    { value: 'right', icon: AlignRight },
                                    { value: 'justify', icon: AlignJustify }
                                ].map(({ value, icon: Icon }) => (
                                    <button
                                        key={value}
                                        type="button"
                                        onClick={() =>
                                            handleTextAlignChange(value)
                                        }
                                        className={cn(
                                            'flex-1 h-12 flex items-center justify-center rounded-xl border text-white/70 transition-colors',
                                            textAlign === value
                                                ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                                : 'bg-[#202927] border-white/10 hover:border-white/30 hover:text-white'
                                        )}
                                    >
                                        <Icon className="h-5 w-5" />
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className={sectionTitleClassName}>
                                Text Decoration
                            </Label>
                            <div className="grid grid-cols-6 gap-2">
                                <button
                                    type="button"
                                    onClick={handleBoldToggle}
                                    className={cn(
                                        'h-12 rounded-xl border text-sm font-semibold',
                                        isBold
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                >
                                    B
                                </button>
                                <button
                                    type="button"
                                    onClick={handleItalicToggle}
                                    className={cn(
                                        'h-12 rounded-xl border text-sm italic',
                                        isItalic
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                >
                                    I
                                </button>
                                <button
                                    type="button"
                                    onClick={() =>
                                        toggleDecoration('underline')
                                    }
                                    className={cn(
                                        'h-12 rounded-xl border text-sm underline',
                                        decorations.has('underline')
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                >
                                    U
                                </button>
                                <button
                                    type="button"
                                    onClick={() =>
                                        toggleDecoration('line-through')
                                    }
                                    className={cn(
                                        'h-12 rounded-xl border text-sm line-through',
                                        decorations.has('line-through')
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                >
                                    S
                                </button>
                                <button
                                    type="button"
                                    onClick={() => toggleDecoration('overline')}
                                    className={cn(
                                        'h-12 rounded-xl border text-sm',
                                        decorations.has('overline')
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                    style={{ textDecoration: 'overline' }}
                                >
                                    O
                                </button>
                                <button
                                    type="button"
                                    onClick={handleTextTransformToggle}
                                    className={cn(
                                        'h-12 rounded-xl border text-sm',
                                        textTransform === 'uppercase'
                                            ? 'border-[#a6ffff] bg-[#24302e] text-white'
                                            : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30'
                                    )}
                                >
                                    <span
                                        style={{
                                            textTransform: 'uppercase',
                                            textDecoration: 'line-through'
                                        }}
                                    >
                                        o
                                    </span>
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className={dividerClassName} />

                    <div
                        ref={textColorRef}
                        className="space-y-4"
                        onClick={() => setActiveRail('text')}
                    >
                        {renderColorSection(
                            'Text Color',
                            textColorMode,
                            handleTextColorModeChange,
                            textColor,
                            handleTextColorChange,
                            textGradient,
                            handleTextGradientChange,
                            STORYBOOK_TEXT_COLORS
                        )}
                        {textColorMode !== 'gradient' &&
                            renderOpacitySection(
                                textOpacity,
                                handleTextOpacityChange
                            )}
                    </div>

                    <div className={dividerClassName} />
                </>
            )}

            <div
                ref={backgroundRef}
                className="space-y-4"
                onClick={() => setActiveRail('background')}
            >
                <Label className={sectionTitleClassName}>Background</Label>
                <div className="grid grid-cols-2 gap-2">
                    {(['color', 'image'] as const).map((tab) => (
                        <button
                            key={tab}
                            type="button"
                            onClick={() => handleBackgroundTabChange(tab)}
                            className={cn(
                                'h-12 rounded-xl border text-sm transition-colors',
                                backgroundTab === tab
                                    ? 'border-[#a6ffff] bg-[#24302e] text-white font-semibold'
                                    : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30 hover:text-white'
                            )}
                        >
                            {tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    ))}
                </div>

                {backgroundTab === 'color' ? (
                    <div className="space-y-4">
                        {renderColorSection(
                            'Color',
                            bgColorMode,
                            handleBgColorModeChange,
                            bgColor,
                            handleBgColorChange,
                            bgGradient,
                            handleBgGradientChange,
                            STORYBOOK_TEXT_COLORS
                        )}
                        {bgColorMode !== 'gradient' &&
                            renderOpacitySection(
                                bgOpacity,
                                handleBgOpacityChange
                            )}
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="space-y-3">
                            <Label className={sectionTitleClassName}>
                                Image Sources
                            </Label>
                            <div className="grid grid-cols-3 gap-2">
                                {(['upload', 'link', 'prompt'] as const).map(
                                    (tab) => (
                                        <button
                                            key={tab}
                                            type="button"
                                            onClick={() =>
                                                setBackgroundImageTab(tab)
                                            }
                                            className={cn(
                                                'h-12 rounded-xl border text-sm transition-colors',
                                                backgroundImageTab === tab
                                                    ? 'border-[#a6ffff] bg-[#24302e] text-white font-semibold'
                                                    : 'bg-[#202927] border-white/10 text-white/70 hover:border-white/30 hover:text-white'
                                            )}
                                        >
                                            {tab.charAt(0).toUpperCase() +
                                                tab.slice(1)}
                                        </button>
                                    )
                                )}
                            </div>
                        </div>

                        {backgroundImageTab === 'upload' && (
                            <div className="space-y-4">
                                {backgroundImageUrl ? (
                                    <div className="space-y-3">
                                        <div
                                            className="w-full rounded-2xl border border-white/10 bg-[#202927] overflow-hidden relative group touch-none select-none cursor-grab active:cursor-grabbing"
                                            style={{
                                                aspectRatio:
                                                    backgroundPreviewAspectRatio
                                            }}
                                            onPointerDown={
                                                handleBackgroundCropPointerDown
                                            }
                                            onPointerMove={
                                                handleBackgroundCropPointerMove
                                            }
                                            onPointerUp={
                                                handleBackgroundCropPointerEnd
                                            }
                                            onPointerCancel={
                                                handleBackgroundCropPointerEnd
                                            }
                                        >
                                            <div
                                                className="absolute inset-0"
                                                style={
                                                    backgroundCropPreviewStyle
                                                }
                                            />
                                            <button
                                                type="button"
                                                className="absolute top-2 right-2 h-6 w-6 rounded-full bg-black/60 flex items-center justify-center text-white/80 opacity-0 scale-90 pointer-events-none transition-all duration-150 ease-out group-hover:opacity-100 group-hover:scale-100 group-hover:-translate-y-0.5 group-hover:pointer-events-auto hover:bg-black/80"
                                                onPointerDown={(e) =>
                                                    e.stopPropagation()
                                                }
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    handleBackgroundImageApply(
                                                        ''
                                                    )
                                                    setBackgroundImageInput('')
                                                }}
                                            >
                                                ×
                                            </button>
                                            <div className="absolute bottom-2 left-2 rounded-lg bg-black/50 px-2 py-1 text-[10px] text-white/80">
                                                Drag to crop
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={handleUploadClick}
                                                disabled={isUploadingBackground}
                                                className={cn(
                                                    'h-10 flex-1 rounded-xl border border-white/10 bg-[#202927] text-sm text-white/80 hover:border-white/30 hover:text-white transition-colors',
                                                    isUploadingBackground &&
                                                        'cursor-not-allowed opacity-70'
                                                )}
                                            >
                                                Replace
                                            </button>
                                            <button
                                                type="button"
                                                onClick={
                                                    handleBackgroundCropReset
                                                }
                                                className="h-10 rounded-xl border border-white/10 bg-[#202927] px-4 text-sm text-white/70 hover:border-white/30 hover:text-white transition-colors"
                                            >
                                                Reset
                                            </button>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            <span className="w-10 text-xs text-white/60">
                                                Zoom
                                            </span>
                                            <input
                                                type="range"
                                                min={5}
                                                max={250}
                                                step={1}
                                                value={Math.round(
                                                    backgroundCropZoom * 100
                                                )}
                                                onChange={
                                                    handleBackgroundCropZoomChange
                                                }
                                                onPointerDown={
                                                    handleBackgroundCropZoomPointerDown
                                                }
                                                onPointerUp={
                                                    handleBackgroundCropZoomPointerEnd
                                                }
                                                onPointerCancel={
                                                    handleBackgroundCropZoomPointerEnd
                                                }
                                                className="flex-1 accent-[#a6ffff]"
                                            />
                                            <span className="w-12 text-right text-xs text-white/60 tabular-nums">
                                                {Math.round(
                                                    backgroundCropZoom * 100
                                                )}
                                                %
                                            </span>
                                        </div>
                                    </div>
                                ) : (
                                    <button
                                        onClick={handleUploadClick}
                                        className={cn(
                                            'w-full aspect-video rounded-2xl border border-white/10 bg-[#202927] flex flex-col items-center justify-center gap-2 text-white/40 hover:border-[#a6ffff]/30 hover:text-white/60 transition-all group overflow-hidden relative',
                                            isUploadingBackground &&
                                                'cursor-not-allowed opacity-70'
                                        )}
                                        disabled={isUploadingBackground}
                                    >
                                        {isUploadingBackground ? (
                                            <Loader2 className="h-8 w-8 animate-spin" />
                                        ) : (
                                            <Icon
                                                name="image"
                                                className="size-8 group-hover:scale-110 transition-transform"
                                            />
                                        )}
                                        <span className="text-xs">
                                            {isUploadingBackground
                                                ? 'Uploading image...'
                                                : 'Click to upload image'}
                                        </span>
                                    </button>
                                )}
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".jpg,.jpeg,.png,.gif,.webp,.bmp,.heic,.heif"
                                    className="hidden"
                                    disabled={isUploadingBackground}
                                    onChange={handleUploadChange}
                                />
                            </div>
                        )}

                        {backgroundImageTab === 'link' && (
                            <div className="space-y-4">
                                <Input
                                    value={backgroundImageInput}
                                    onChange={(event) => {
                                        backgroundImageDirtyRef.current = true
                                        setBackgroundImageInput(
                                            event.target.value
                                        )
                                    }}
                                    onBlur={() => {
                                        backgroundImageDirtyRef.current = false
                                        if (
                                            backgroundImageDebounceRef.current
                                        ) {
                                            window.clearTimeout(
                                                backgroundImageDebounceRef.current
                                            )
                                            backgroundImageDebounceRef.current =
                                                null
                                        }
                                        handleBackgroundImageApply(
                                            backgroundImageInput.trim()
                                        )
                                    }}
                                    className={inputClassName}
                                    placeholder="https://example.com/image.png"
                                />
                                {backgroundImageUrl && (
                                    <div className="space-y-3">
                                        <div
                                            className="w-full rounded-2xl border border-white/10 bg-[#202927] overflow-hidden relative group touch-none select-none cursor-grab active:cursor-grabbing"
                                            style={{
                                                aspectRatio:
                                                    backgroundPreviewAspectRatio
                                            }}
                                            onPointerDown={
                                                handleBackgroundCropPointerDown
                                            }
                                            onPointerMove={
                                                handleBackgroundCropPointerMove
                                            }
                                            onPointerUp={
                                                handleBackgroundCropPointerEnd
                                            }
                                            onPointerCancel={
                                                handleBackgroundCropPointerEnd
                                            }
                                        >
                                            <div
                                                className="absolute inset-0"
                                                style={
                                                    backgroundCropPreviewStyle
                                                }
                                            />
                                            <button
                                                type="button"
                                                className="absolute top-2 right-2 h-6 w-6 rounded-full bg-black/60 flex items-center justify-center text-white/80 opacity-0 scale-90 pointer-events-none transition-all duration-150 ease-out group-hover:opacity-100 group-hover:scale-100 group-hover:-translate-y-0.5 group-hover:pointer-events-auto hover:bg-black/80"
                                                onPointerDown={(e) =>
                                                    e.stopPropagation()
                                                }
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    handleBackgroundImageApply(
                                                        ''
                                                    )
                                                    setBackgroundImageInput('')
                                                }}
                                            >
                                                ×
                                            </button>
                                            <div className="absolute bottom-2 left-2 rounded-lg bg-black/50 px-2 py-1 text-[10px] text-white/80">
                                                Drag to crop
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={
                                                    handleBackgroundCropReset
                                                }
                                                className="h-10 flex-1 rounded-xl border border-white/10 bg-[#202927] text-sm text-white/70 hover:border-white/30 hover:text-white transition-colors"
                                            >
                                                Reset
                                            </button>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            <span className="w-10 text-xs text-white/60">
                                                Zoom
                                            </span>
                                            <input
                                                type="range"
                                                min={5}
                                                max={250}
                                                step={1}
                                                value={Math.round(
                                                    backgroundCropZoom * 100
                                                )}
                                                onChange={
                                                    handleBackgroundCropZoomChange
                                                }
                                                onPointerDown={
                                                    handleBackgroundCropZoomPointerDown
                                                }
                                                onPointerUp={
                                                    handleBackgroundCropZoomPointerEnd
                                                }
                                                onPointerCancel={
                                                    handleBackgroundCropZoomPointerEnd
                                                }
                                                className="flex-1 accent-[#a6ffff]"
                                            />
                                            <span className="w-12 text-right text-xs text-white/60 tabular-nums">
                                                {Math.round(
                                                    backgroundCropZoom * 100
                                                )}
                                                %
                                            </span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {backgroundImageTab === 'prompt' && (
                            <div className="space-y-4">
                                <div className="relative">
                                    <Textarea
                                        value={imagePrompt}
                                        onChange={(e) =>
                                            setImagePrompt(e.target.value)
                                        }
                                        className={cn(
                                            textareaClassName,
                                            'min-h-[160px]'
                                        )}
                                        placeholder="Describe the background you want to generate..."
                                    />
                                    {/* AI Generating Background Overlay */}
                                    {isGeneratingBackground && (
                                        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50 backdrop-blur-sm rounded-lg">
                                            <div className="flex flex-col items-center gap-2">
                                                <Loader2 className="h-6 w-6 animate-spin text-[#a6ffff]" />
                                                <span className="text-xs font-medium text-white">
                                                    II is generating...
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                    <button
                                        type="button"
                                        onClick={handleAIGenerateBackground}
                                        disabled={
                                            !imagePrompt.trim() ||
                                            isGeneratingBackground
                                        }
                                        className={cn(
                                            'absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-xl border border-[#a6ffff]/50 bg-[#bfefff] text-[#0f1511] transition-all',
                                            !imagePrompt.trim() ||
                                                isGeneratingBackground
                                                ? 'opacity-50 cursor-not-allowed'
                                                : 'hover:scale-105'
                                        )}
                                        title={
                                            isGeneratingBackground
                                                ? 'Generating...'
                                                : 'Generate background with AI'
                                        }
                                    >
                                        {isGeneratingBackground ? (
                                            <Loader2 className="size-5 animate-spin" />
                                        ) : (
                                            <Icon
                                                name="ai-magic"
                                                className="size-5 stroke-black"
                                            />
                                        )}
                                    </button>
                                </div>
                                {/* Preview of generated background */}
                                {backgroundImageUrl &&
                                    !isGeneratingBackground && (
                                        <div className="space-y-3">
                                            <div
                                                className="w-full rounded-2xl border border-white/10 bg-[#202927] overflow-hidden relative group touch-none select-none cursor-grab active:cursor-grabbing"
                                                style={{
                                                    aspectRatio:
                                                        backgroundPreviewAspectRatio
                                                }}
                                                onPointerDown={
                                                    handleBackgroundCropPointerDown
                                                }
                                                onPointerMove={
                                                    handleBackgroundCropPointerMove
                                                }
                                                onPointerUp={
                                                    handleBackgroundCropPointerEnd
                                                }
                                                onPointerCancel={
                                                    handleBackgroundCropPointerEnd
                                                }
                                            >
                                                <div
                                                    className="absolute inset-0"
                                                    style={
                                                        backgroundCropPreviewStyle
                                                    }
                                                />
                                                <button
                                                    type="button"
                                                    className="absolute top-2 right-2 h-6 w-6 rounded-full bg-black/60 flex items-center justify-center text-white/80 opacity-0 scale-90 pointer-events-none transition-all duration-150 ease-out group-hover:opacity-100 group-hover:scale-100 group-hover:-translate-y-0.5 group-hover:pointer-events-auto hover:bg-black/80"
                                                    onPointerDown={(e) =>
                                                        e.stopPropagation()
                                                    }
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        handleBackgroundImageApply(
                                                            ''
                                                        )
                                                        setBackgroundImageInput(
                                                            ''
                                                        )
                                                    }}
                                                >
                                                    ×
                                                </button>
                                                <div className="absolute bottom-2 left-2 rounded-lg bg-black/50 px-2 py-1 text-[10px] text-white/80">
                                                    Drag to crop
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={
                                                        handleBackgroundCropReset
                                                    }
                                                    className="h-10 flex-1 rounded-xl border border-white/10 bg-[#202927] text-sm text-white/70 hover:border-white/30 hover:text-white transition-colors"
                                                >
                                                    Reset
                                                </button>
                                            </div>

                                            <div className="flex items-center gap-3">
                                                <span className="w-10 text-xs text-white/60">
                                                    Zoom
                                                </span>
                                                <input
                                                    type="range"
                                                    min={5}
                                                    max={250}
                                                    step={1}
                                                    value={Math.round(
                                                        backgroundCropZoom * 100
                                                    )}
                                                    onChange={
                                                        handleBackgroundCropZoomChange
                                                    }
                                                    onPointerDown={
                                                        handleBackgroundCropZoomPointerDown
                                                    }
                                                    onPointerUp={
                                                        handleBackgroundCropZoomPointerEnd
                                                    }
                                                    onPointerCancel={
                                                        handleBackgroundCropZoomPointerEnd
                                                    }
                                                    className="flex-1 accent-[#a6ffff]"
                                                />
                                                <span className="w-12 text-right text-xs text-white/60 tabular-nums">
                                                    {Math.round(
                                                        backgroundCropZoom * 100
                                                    )}
                                                    %
                                                </span>
                                            </div>
                                        </div>
                                    )}
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className={dividerClassName} />

            <div
                ref={borderRef}
                className="space-y-4"
                onClick={() => setActiveRail('border')}
            >
                {renderColorSection(
                    'Border Color',
                    borderColorMode,
                    handleBorderColorModeChange,
                    borderColor,
                    handleBorderColorChange,
                    borderGradient,
                    handleBorderGradientChange,
                    STORYBOOK_TEXT_COLORS
                )}

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>
                            Border Style
                        </Label>
                        <Select
                            value={borderStyle}
                            onValueChange={handleBorderStyleChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue placeholder="Style" />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_STYLE_OPTIONS.map((opt) => (
                                    <SelectItem key={opt} value={opt}>
                                        {opt.charAt(0).toUpperCase() +
                                            opt.slice(1)}
                                    </SelectItem>
                                ))}
                                {borderStyle &&
                                    !BORDER_STYLE_OPTIONS.includes(
                                        borderStyle
                                    ) && (
                                        <SelectItem value={borderStyle}>
                                            {borderStyle}
                                        </SelectItem>
                                    )}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>
                            Border Width
                        </Label>
                        <Select
                            value={borderWidth}
                            onValueChange={handleBorderWidthChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue placeholder="Width" />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_WIDTH_OPTIONS.map((opt) => (
                                    <SelectItem
                                        key={opt.value}
                                        value={opt.value}
                                    >
                                        {opt.label}
                                    </SelectItem>
                                ))}
                                {!BORDER_WIDTH_OPTIONS.some(
                                    (opt) => opt.value === borderWidth
                                ) && (
                                    <SelectItem value={borderWidth}>
                                        {borderWidth}
                                    </SelectItem>
                                )}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>
                            Border Radius
                        </Label>
                        <Select
                            value={String(borderRadius)}
                            onValueChange={handleBorderRadiusChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue placeholder="Radius" />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_RADIUS_OPTIONS.map((opt) => (
                                    <SelectItem
                                        key={opt.value}
                                        value={String(opt.value)}
                                    >
                                        {opt.label}
                                    </SelectItem>
                                ))}
                                {!BORDER_RADIUS_OPTIONS.some(
                                    (o) => o.value === borderRadius
                                ) && (
                                    <SelectItem value={String(borderRadius)}>
                                        {borderRadius}px
                                    </SelectItem>
                                )}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        {renderOpacitySection(
                            borderOpacity,
                            handleBorderOpacityChange
                        )}
                    </div>
                </div>
            </div>

            <div className={dividerClassName} />

            <div
                ref={spacingRef}
                className="space-y-3"
                onClick={() => setActiveRail('spacing')}
            >
                <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>Padding</Label>
                        <Select
                            value={String(padding)}
                            onValueChange={handlePaddingChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue placeholder="Padding" />
                            </SelectTrigger>
                            <SelectContent>
                                {SPACING_OPTIONS.map((value) => (
                                    <SelectItem
                                        key={value}
                                        value={String(value)}
                                    >
                                        {value}px
                                    </SelectItem>
                                ))}
                                {Number.isFinite(padding) &&
                                    !SPACING_OPTIONS.includes(padding) && (
                                        <SelectItem value={String(padding)}>
                                            {padding}px
                                        </SelectItem>
                                    )}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>Margin</Label>
                        <Select
                            value={String(margin)}
                            onValueChange={handleMarginChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue placeholder="Margin" />
                            </SelectTrigger>
                            <SelectContent>
                                {SPACING_OPTIONS.map((value) => (
                                    <SelectItem
                                        key={value}
                                        value={String(value)}
                                    >
                                        {value}px
                                    </SelectItem>
                                ))}
                                {Number.isFinite(margin) &&
                                    !SPACING_OPTIONS.includes(margin) && (
                                        <SelectItem value={String(margin)}>
                                            {margin}px
                                        </SelectItem>
                                    )}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            <div className={dividerClassName} />

            <div
                ref={shadowRef}
                className="space-y-3"
                onClick={() => setActiveRail('shadow')}
            >
                <Label className={sectionTitleClassName}>Shadow Effect</Label>
                <Select value={shadow} onValueChange={handleShadowChange}>
                    <SelectTrigger className={inputClassName}>
                        <SelectValue placeholder="Shadow" />
                    </SelectTrigger>
                    <SelectContent>
                        {SHADOW_PRESETS.map((preset) => (
                            <SelectItem key={preset.value} value={preset.value}>
                                {preset.label}
                            </SelectItem>
                        ))}
                        {shadow &&
                            !SHADOW_PRESETS.some(
                                (preset) => preset.value === shadow
                            ) && (
                                <SelectItem value={shadow}>{shadow}</SelectItem>
                            )}
                    </SelectContent>
                </Select>
            </div>
        </div>
    )

    return (
        <div className={containerClassName}>
            <div className="flex min-w-0 flex-1 flex-col min-h-0">
                <div
                    ref={scrollContainerRef}
                    className="flex flex-1 min-h-0 flex-col overflow-y-auto no-scrollbar pl-4 pr-4 pt-4 pb-[140px]"
                >
                    {panelContent}
                </div>
            </div>

            {selectedElement && (
                <div className="absolute right-3 top-3 hidden flex-col items-center gap-1 rounded-xl bg-[#181e1c] p-1 shadow-2xl lg:flex">
                    {railItems.map(
                        ({ id, label, iconName, icon: LucideIcon, ref }) => (
                            <button
                                key={id}
                                type="button"
                                onClick={() => {
                                    // Lock scroll-based sync while smooth scroll animates
                                    if (railClickLockRef.current) {
                                        window.clearTimeout(
                                            railClickLockRef.current
                                        )
                                    }
                                    railClickLockRef.current =
                                        window.setTimeout(() => {
                                            railClickLockRef.current = null
                                        }, 600)

                                    setActiveRail(id)
                                    ref.current?.scrollIntoView({
                                        behavior: 'smooth',
                                        block: 'start'
                                    })
                                }}
                                className={cn(
                                    'flex h-8 w-8 items-center justify-center rounded-lg transition-colors',
                                    activeRail === id
                                        ? 'bg-[#a6ffff] text-[#181e1c]'
                                        : 'bg-[#263533] text-white/70 hover:bg-[#2e3f3d] hover:text-white'
                                )}
                                title={label}
                            >
                                {iconName ? (
                                    <Icon name={iconName} className="size-4" />
                                ) : LucideIcon ? (
                                    <LucideIcon className="h-4 w-4" />
                                ) : null}
                            </button>
                        )
                    )}
                </div>
            )}
        </div>
    )
}
