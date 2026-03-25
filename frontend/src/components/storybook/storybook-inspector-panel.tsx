/**
 * Storybook Inspector Panel Component
 *
 * A panel for editing element properties in storybook edit mode.
 * Adapted from the design mode inspector sidebar.
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
import { useTranslation } from 'react-i18next'
import { Icon } from '@/components/ui/icon'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
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
import { useStorybookEdit } from '@/contexts/storybook-edit-context'
import { storybookService } from '@/services/storybook.service'
import { useAppDispatch, userApi } from '@/state'

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

const BORDER_WIDTH_OPTIONS: Array<{
    label: string
    labelKey?: string
    value: string
}> = [
    {
        label: 'None',
        labelKey: 'storybook.inspector.options.none',
        value: '0px'
    },
    { label: 'Xs', value: '1px' },
    { label: 'Sm', value: '2px' },
    { label: 'Md', value: '4px' },
    { label: 'Lg', value: '8px' }
]
const BORDER_RADIUS_OPTIONS: Array<{
    label: string
    labelKey?: string
    value: number
}> = [
    {
        label: 'None',
        labelKey: 'storybook.inspector.options.none',
        value: 0
    },
    { label: 'Xs', value: 4 },
    { label: 'Sm', value: 8 },
    { label: 'Md', value: 12 },
    { label: 'Lg', value: 16 },
    { label: 'Xl', value: 24 },
    {
        label: 'Full',
        labelKey: 'storybook.inspector.options.full',
        value: 9999
    }
]
const BORDER_STYLE_OPTIONS = ['none', 'solid', 'dashed', 'dotted', 'double']
const SPACING_OPTIONS = [0, 4, 8, 12, 16, 24, 32, 40, 48, 64]
const SHADOW_PRESETS: Array<{
    label: string
    labelKey?: string
    value: string
}> = [
    {
        label: 'None',
        labelKey: 'storybook.inspector.shadow.none',
        value: 'none'
    },
    {
        label: 'Small',
        labelKey: 'storybook.inspector.shadow.small',
        value: '0 1px 2px 0 rgb(0 0 0 / 0.18)'
    },
    {
        label: 'Medium',
        labelKey: 'storybook.inspector.shadow.medium',
        value: '0 4px 12px rgb(0 0 0 / 0.2)'
    },
    {
        label: 'Large',
        labelKey: 'storybook.inspector.shadow.large',
        value: '0 12px 32px rgb(0 0 0 / 0.24)'
    }
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

interface StorybookInspectorPanelProps {
    selectedElement: ElementInfo | null
    onStyleChange: (
        property: string,
        value: string,
        options?: StyleChangeGroup
    ) => void
    onTextChange: (text: string) => void
    className?: string
    pageImageUrl?: string | null
    textPosition?: string | null
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

const COLOR_TOKEN_REGEX =
    /(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)|hsla?\([^)]+\))/

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

function parseLinearGradient(value: string): { from: string; to: string } | null {
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

export function StorybookInspectorPanel({
    selectedElement,
    onStyleChange,
    onTextChange,
    className,
    pageImageUrl,
    textPosition
}: StorybookInspectorPanelProps) {
    const contentRef = useRef<HTMLDivElement | null>(null)
    const typographyRef = useRef<HTMLDivElement | null>(null)
    const textColorRef = useRef<HTMLDivElement | null>(null)
    const backgroundRef = useRef<HTMLDivElement | null>(null)
    const borderRef = useRef<HTMLDivElement | null>(null)
    const spacingRef = useRef<HTMLDivElement | null>(null)
    const shadowRef = useRef<HTMLDivElement | null>(null)
    const fileInputRef = useRef<HTMLInputElement | null>(null)

    const { editingStorybookId } = useStorybookEdit()
    const { t } = useTranslation()
    const dispatch = useAppDispatch()

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
    const [borderGradient, setBorderGradient] =
        useState(DEFAULT_BORDER_GRADIENT)
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
    const [isRewritingContent, setIsRewritingContent] = useState(false)
    const [isGeneratingBackground, setIsGeneratingBackground] = useState(false)

    const colorModeLabels = useMemo(
        () => ({
            solid: t('storybook.inspector.colorMode.solid'),
            custom: t('storybook.inspector.colorMode.custom'),
            gradient: t('storybook.inspector.colorMode.gradient')
        }),
        [t]
    )

    const backgroundTabLabels = useMemo(
        () => ({
            color: t('storybook.inspector.background.tabColor'),
            image: t('storybook.inspector.background.tabImage')
        }),
        [t]
    )

    const backgroundImageTabLabels = useMemo(
        () => ({
            upload: t('storybook.inspector.background.sourceUpload'),
            link: t('storybook.inspector.background.sourceLink'),
            prompt: t('storybook.inspector.background.sourcePrompt')
        }),
        [t]
    )

    const changeGroupLabels = useMemo(
        () => ({
            textGradient: t('storybook.inspector.changeGroups.textGradient'),
            textColor: t('storybook.inspector.changeGroups.textColor'),
            backgroundGradient: t(
                'storybook.inspector.changeGroups.backgroundGradient'
            ),
            backgroundColor: t(
                'storybook.inspector.changeGroups.backgroundColor'
            ),
            backgroundImage: t(
                'storybook.inspector.changeGroups.backgroundImage'
            ),
            borderGradient: t('storybook.inspector.changeGroups.borderGradient'),
            borderColor: t('storybook.inspector.changeGroups.borderColor')
        }),
        [t]
    )

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
        if (borderImageSource && /gradient/i.test(borderImageSource)) {
            const parsedBorderGradient =
                parseLinearGradient(borderImageSource)
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
        const shouldUseOpacityFallback =
            !backgroundClipValue && !textFillValue
        const isTextGradient =
            gradientLayers.length > 0 &&
            (hasTextClip ||
                textFillTransparent ||
                (shouldUseOpacityFallback && textInfo.opacity === '0.0'))

        if (isTextGradient) {
            const parsedTextGradient = parseLinearGradient(gradientLayers[0])
            setTextColorMode('gradient')
            setTextGradient(parsedTextGradient ?? DEFAULT_TEXT_GRADIENT)
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

        if (backgroundGradientLayer) {
            const parsedBgGradient =
                parseLinearGradient(backgroundGradientLayer)
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

    const handleAIRewrite = useCallback(async () => {
        if (!textContent.trim() || !editingStorybookId || isRewritingContent)
            return

        setIsRewritingContent(true)
        try {
            const response = await storybookService.aiRewriteContent(
                editingStorybookId,
                textContent,
                pageImageUrl ?? undefined
            )

            if (response.success && response.rewritten_content) {
                setTextContent(response.rewritten_content)
                onTextChange(response.rewritten_content)
                originalTextContentRef.current = response.rewritten_content
                // Invalidate credit cache to refresh balance after rewrite
                dispatch(
                    userApi.util.invalidateTags(['CreditBalance', 'CreditUsage'])
                )
                toast.success(t('storybook.inspector.toasts.rewriteSuccess'))
            } else {
                toast.error(
                    response.error ||
                        t('storybook.inspector.toasts.rewriteFailed')
                )
            }
        } catch (error) {
            console.error('AI rewrite error:', error)
            toast.error(t('storybook.inspector.toasts.rewriteFailed'))
        } finally {
            setIsRewritingContent(false)
        }
    }, [
        textContent,
        editingStorybookId,
        pageImageUrl,
        isRewritingContent,
        onTextChange,
        dispatch,
        t
    ])

    const handleAIGenerateBackground = useCallback(async () => {
        if (
            !imagePrompt.trim() ||
            !editingStorybookId ||
            isGeneratingBackground
        )
            return

        setIsGeneratingBackground(true)
        try {
            const response = await storybookService.aiGenerateBackground(
                editingStorybookId,
                imagePrompt,
                pageImageUrl ?? undefined,
                textPosition ?? undefined
            )

            if (response.success && response.image_url) {
                // Set the generated image as background
                setBackgroundImageUrl(response.image_url)
                setBackgroundImageInput(response.image_url)
                // Apply the background image style
                onStyleChange('background-image', `url("${response.image_url}")`)
                onStyleChange('background-size', 'cover')
                onStyleChange('background-position', 'center')
                // Invalidate credit cache to refresh balance after background generation
                dispatch(
                    userApi.util.invalidateTags(['CreditBalance', 'CreditUsage'])
                )
                toast.success(
                    t('storybook.inspector.toasts.generateSuccess')
                )
            } else {
                toast.error(
                    response.error ||
                        t('storybook.inspector.toasts.generateFailed')
                )
            }
        } catch (error) {
            console.error('AI generate background error:', error)
            toast.error(t('storybook.inspector.toasts.generateFailed'))
        } finally {
            setIsGeneratingBackground(false)
        }
    }, [
        imagePrompt,
        editingStorybookId,
        pageImageUrl,
        textPosition,
        isGeneratingBackground,
        onStyleChange,
        dispatch,
        t
    ])

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
            const textLayer = buildLinearGradient(
                TEXT_GRADIENT_ANGLE,
                from,
                to
            )
            let backgroundLayer = 'none'
            if (bgColorMode === 'gradient') {
                backgroundLayer = buildLinearGradient(
                    BACKGROUND_GRADIENT_ANGLE,
                    bgGradient.from,
                    bgGradient.to
                )
            } else if (backgroundImageUrl) {
                backgroundLayer = `url("${backgroundImageUrl}")`
            }
            const backgroundImageValue = composeBackgroundImage([
                textLayer,
                backgroundLayer
            ])
            applyStyleBatch(
                changeGroupLabels.textGradient,
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
            bgColorMode,
            bgGradient,
            backgroundImageUrl,
            changeGroupLabels
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
                changeGroupLabels.textGradient,
                [
                    { property: 'background-image', value: bgImageValue },
                    { property: 'background-clip', value: '' },
                    { property: '-webkit-background-clip', value: '' },
                    { property: '-webkit-text-fill-color', value: '' }
                ],
                group
            )
        },
        [
            applyStyleBatch,
            bgColorMode,
            bgGradient,
            backgroundImageUrl,
            changeGroupLabels
        ]
    )

    const handleTextColorChange = useCallback(
        (value: string) => {
            setTextColor(value)
            if (textColorMode !== 'gradient') {
                onStyleChange(
                    'color',
                    combineColorAndOpacity(value, textOpacity)
                )
            }
        },
        [onStyleChange, textColorMode, textOpacity]
    )

    const handleTextOpacityChange = useCallback(
        (value: string) => {
            setTextOpacity(value)
            // Only apply color opacity change - don't modify global opacity
            if (textColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }
            onStyleChange('color', combineColorAndOpacity(textColor, value))
        },
        [onStyleChange, textColor, textColorMode]
    )

    const handleTextColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            setTextColorMode(value)
            if (value === 'gradient') {
                applyTextGradient(
                    textGradient.from,
                    textGradient.to,
                    buildStyleGroup(changeGroupLabels.textGradient)
                )
                return
            }
            const group = buildStyleGroup(changeGroupLabels.textColor)
            // Preserve background image/gradient when clearing text gradient
            clearTextGradient(group, true)
            onStyleChange(
                'color',
                combineColorAndOpacity(textColor, textOpacity),
                group
            )
        },
        [
            applyTextGradient,
            clearTextGradient,
            buildStyleGroup,
            changeGroupLabels,
            onStyleChange,
            textColor,
            textOpacity,
            textGradient
        ]
    )

    const handleTextGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setTextGradient(next)
            if (textColorMode === 'gradient') {
                applyTextGradient(
                    next.from,
                    next.to,
                    buildStyleGroup(changeGroupLabels.textGradient)
                )
            }
        },
        [applyTextGradient, buildStyleGroup, changeGroupLabels, textColorMode]
    )

    const applyBackgroundGradient = useCallback(
        (from: string, to: string, group?: StyleChangeGroup) => {
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
                changeGroupLabels.backgroundGradient,
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
        [applyStyleBatch, changeGroupLabels, textColorMode, textGradient]
    )

    const handleBgColorChange = useCallback(
        (value: string) => {
            setBgColor(value)
            if (bgColorMode !== 'gradient') {
                // Only change background-color, don't reset background-image
                // (it will be reset when switching modes if needed)
                onStyleChange(
                    'background-color',
                    combineColorAndOpacity(value, bgOpacity)
                )
            }
        },
        [bgColorMode, bgOpacity, onStyleChange]
    )

    const handleBgOpacityChange = useCallback(
        (value: string) => {
            setBgOpacity(value)
            // Only apply background-color opacity change - don't modify global opacity
            if (bgColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }
            onStyleChange(
                'background-color',
                combineColorAndOpacity(bgColor, value)
            )
        },
        [onStyleChange, bgColorMode, bgColor]
    )

    const handleBgColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            setBgColorMode(value)
            if (value === 'gradient') {
                applyBackgroundGradient(
                    bgGradient.from,
                    bgGradient.to,
                    buildStyleGroup(changeGroupLabels.backgroundGradient)
                )
                return
            }
            const group = buildStyleGroup(changeGroupLabels.backgroundColor)

            // Determine background-image value - preserve text gradient if active
            const textLayer =
                textColorMode === 'gradient'
                    ? buildLinearGradient(
                          TEXT_GRADIENT_ANGLE,
                          textGradient.from,
                          textGradient.to
                      )
                    : null
            const bgImageValue = composeBackgroundImage([textLayer])

            applyStyleBatch(
                changeGroupLabels.backgroundColor,
                [
                    { property: 'background-image', value: bgImageValue },
                    {
                        property: 'background-color',
                        value: combineColorAndOpacity(bgColor, bgOpacity)
                    }
                ],
                group
            )
        },
        [
            applyBackgroundGradient,
            applyStyleBatch,
            bgColor,
            bgOpacity,
            bgGradient,
            buildStyleGroup,
            changeGroupLabels,
            textColorMode,
            textGradient
        ]
    )

    const handleBgGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setBgGradient(next)
            if (bgColorMode === 'gradient') {
                applyBackgroundGradient(
                    next.from,
                    next.to,
                    buildStyleGroup(changeGroupLabels.backgroundGradient)
                )
            }
        },
        [
            applyBackgroundGradient,
            buildStyleGroup,
            changeGroupLabels,
            bgColorMode
        ]
    )

    const applyBorderGradient = useCallback(
        (from: string, to: string, group?: StyleChangeGroup) => {
            applyStyleBatch(
                changeGroupLabels.borderGradient,
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
        [applyStyleBatch, changeGroupLabels]
    )

    const handleBorderColorChange = useCallback(
        (value: string) => {
            setBorderColor(value)
            if (borderColorMode !== 'gradient') {
                // Only change border-color, don't reset border-image
                // (it will be reset when switching modes if needed)
                onStyleChange(
                    'border-color',
                    combineColorAndOpacity(value, borderOpacity)
                )
            }
        },
        [borderColorMode, borderOpacity, onStyleChange]
    )

    const handleBorderOpacityChange = useCallback(
        (value: string) => {
            setBorderOpacity(value)
            // Only apply border-color opacity change - don't modify global opacity
            if (borderColorMode === 'gradient') {
                // Gradient mode doesn't support opacity changes via color alpha
                return
            }
            onStyleChange(
                'border-color',
                combineColorAndOpacity(borderColor, value)
            )
        },
        [onStyleChange, borderColorMode, borderColor]
    )

    const handleBorderColorModeChange = useCallback(
        (value: 'solid' | 'custom' | 'gradient') => {
            const prevMode = borderColorMode
            setBorderColorMode(value)

            if (value !== 'gradient' && prevMode !== 'gradient') {
                return
            }

            if (value === 'gradient') {
                applyBorderGradient(
                    borderGradient.from,
                    borderGradient.to,
                    buildStyleGroup(changeGroupLabels.borderGradient)
                )
                return
            }
            const group = buildStyleGroup(changeGroupLabels.borderColor)
            applyStyleBatch(
                changeGroupLabels.borderColor,
                [
                    { property: 'border-image', value: 'none' },
                    { property: 'border-image-slice', value: '' },
                    {
                        property: 'border-color',
                        value: combineColorAndOpacity(
                            borderColor,
                            borderOpacity
                        )
                    }
                ],
                group
            )
        },
        [
            applyBorderGradient,
            applyStyleBatch,
            borderColor,
            borderOpacity,
            borderGradient,
            buildStyleGroup,
            changeGroupLabels,
            borderColorMode
        ]
    )

    const handleBorderGradientChange = useCallback(
        (next: { from: string; to: string }) => {
            setBorderGradient(next)
            if (borderColorMode === 'gradient') {
                applyBorderGradient(
                    next.from,
                    next.to,
                    buildStyleGroup(changeGroupLabels.borderGradient)
                )
            }
        },
        [applyBorderGradient, buildStyleGroup, changeGroupLabels, borderColorMode]
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
                        buildStyleGroup(changeGroupLabels.backgroundGradient)
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
                const bgImageValue = composeBackgroundImage([textLayer])

                applyStyleBatch(changeGroupLabels.backgroundColor, [
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
            changeGroupLabels,
            selectedElement,
            textColorMode,
            textGradient
        ]
    )

    const handleBackgroundImageApply = useCallback(
        (url: string) => {
            const label = changeGroupLabels.backgroundImage
            if (!url) {
                setBackgroundImageUrl('')

                // Determine background-image value - preserve text gradient if active
                const textLayer =
                    textColorMode === 'gradient'
                        ? buildLinearGradient(
                              TEXT_GRADIENT_ANGLE,
                              textGradient.from,
                              textGradient.to
                          )
                        : null
                const bgImageValue = composeBackgroundImage([textLayer])

                applyStyleBatch(label, [
                    { property: 'background-image', value: bgImageValue }
                ])
                return
            }
            setBackgroundImageUrl(url)
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
        [applyStyleBatch, changeGroupLabels, textColorMode, textGradient]
    )

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
                toast.error(t('storybook.inspector.toasts.invalidImageFile'))
                return
            }

            if (!editingStorybookId) {
                const reader = new FileReader()
                reader.onload = () => {
                    const result =
                        typeof reader.result === 'string' ? reader.result : ''
                    if (result) {
                        handleBackgroundImageApply(result)
                        setBackgroundImageInput(result)
                    }
                }
                reader.readAsDataURL(file)
                return
            }

            setIsUploadingBackground(true)
            try {
                const result = await storybookService.uploadBackgroundImage(
                    editingStorybookId,
                    file
                )
                handleBackgroundImageApply(result.url)
                setBackgroundImageInput(result.url)
            } catch (error) {
                console.error(
                    '[StorybookInspectorPanel] Failed to upload background image:',
                    error
                )
                toast.error(t('storybook.inspector.toasts.uploadFailed'))
            } finally {
                setIsUploadingBackground(false)
            }
        },
        [editingStorybookId, handleBackgroundImageApply, t]
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
                    label: t('storybook.inspector.sections.content'),
                    iconName: 'content',
                    ref: contentRef
                },
                {
                    id: 'typography',
                    label: t('storybook.inspector.sections.typography'),
                    iconName: 'alargesmall',
                    ref: typographyRef
                },
                {
                    id: 'text',
                    label: t('storybook.inspector.sections.textColor'),
                    iconName: 'textcolor',
                    ref: textColorRef
                }
            )
        }
        items.push(
            {
                id: 'background',
                label: t('storybook.inspector.sections.background'),
                iconName: 'background-icon',
                ref: backgroundRef
            },
            {
                id: 'border',
                label: t('storybook.inspector.sections.border'),
                icon: Square,
                ref: borderRef
            },
            {
                id: 'spacing',
                label: t('storybook.inspector.sections.spacing'),
                iconName: 'margin-padding',
                ref: spacingRef
            },
            {
                id: 'shadow',
                label: t('storybook.inspector.sections.shadow'),
                iconName: 'shadow',
                ref: shadowRef
            }
        )
        return items
    }, [showTextControls, t])

    const containerClassName = cn(
        'hidden md:flex h-full w-full flex-shrink-0 relative overflow-hidden bg-white text-black dark:bg-[#181e1c] dark:text-white',
        className
    )

    const sectionTitleClassName = 'text-xs font-semibold text-black/70 dark:text-white'
    const fieldLabelClassName = 'text-[13px] text-black/60 dark:text-white'
    const inputClassName =
        '!h-12 w-full rounded-xl border border-grey bg-white px-4 text-sm text-black placeholder:text-black/40 focus-visible:ring-1 focus-visible:ring-sky-blue/40 focus-visible:border-sky-blue transition-all dark:border-white/10 dark:bg-[#202927] dark:text-white dark:placeholder:text-white/30 dark:focus-visible:ring-[#a6ffff]/40 dark:focus-visible:border-[#a6ffff]'
    const textareaClassName =
        'min-h-[110px] resize-none rounded-xl border border-grey bg-white px-3 py-2 text-sm text-black placeholder:text-black/40 focus-visible:ring-2 focus-visible:ring-sky-blue/40 focus-visible:border-sky-blue dark:border-white/10 dark:bg-[#202927] dark:text-white dark:placeholder:text-white/30 dark:focus-visible:ring-[#a6ffff] dark:focus-visible:border-[#a6ffff]'
    const dividerClassName = 'my-4 border-t border-dashed border-grey/70 dark:border-white/30'
    const tabButtonBaseClassName =
        'h-12 rounded-xl border text-sm transition-colors'
    const tabButtonActiveClassName =
        'border-sky-blue bg-sky-blue/30 text-black font-semibold dark:border-[#a6ffff] dark:bg-[#24302e] dark:text-white'
    const tabButtonInactiveClassName =
        'bg-grey-3 border-grey text-black/60 hover:border-grey-2 hover:text-black dark:bg-[#202927] dark:border-white/10 dark:text-white/70 dark:hover:border-white/30 dark:hover:text-white'
    const toggleButtonBaseClassName =
        'flex-1 h-12 flex items-center justify-center rounded-xl border transition-colors'
    const toggleButtonActiveClassName =
        'border-sky-blue bg-sky-blue/30 text-black dark:border-[#a6ffff] dark:bg-[#24302e] dark:text-white'
    const toggleButtonInactiveClassName =
        'bg-grey-3 border-grey text-black/60 hover:border-grey-2 hover:text-black dark:bg-[#202927] dark:border-white/10 dark:text-white/70 dark:hover:border-white/30 dark:hover:text-white'

    const isImage = selectedElement?.tagName.toLowerCase() === 'img'
    const imageSrc = isImage ? selectedElement?.attributes?.src : null

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

    const renderOpacitySection = (
        value: string,
        onChange: (val: string) => void
    ) => (
        <div className="space-y-1.5">
            <Label className={cn(sectionTitleClassName, 'text-[13px]')}>
                {t('storybook.inspector.opacity.label')}
            </Label>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className={inputClassName}>
                    <SelectValue
                        placeholder={t('storybook.inspector.opacity.placeholder')}
                    />
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
                            tabButtonBaseClassName,
                            mode === tab
                                ? tabButtonActiveClassName
                                : tabButtonInactiveClassName
                        )}
                    >
                        {colorModeLabels[tab]}
                    </button>
                ))}
            </div>

            {mode === 'gradient' ? (
                <div className="grid grid-cols-2 gap-3">
                    {(['from', 'to'] as const).map((key) => (
                        <div key={key} className="space-y-1.5">
                            <Label className={fieldLabelClassName}>
                                {key === 'from'
                                    ? t('storybook.inspector.gradient.from')
                                    : t('storybook.inspector.gradient.to')}
                            </Label>
                            <div className="relative flex items-center">
                                <div className="absolute left-3 flex items-center pointer-events-none">
                                    <div
                                        className="h-7 w-7 rounded border border-grey/60 dark:border-white/20"
                                        style={{
                                            backgroundColor: gradientValue[key]
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
                            className="h-7 w-7 rounded-md border border-grey/60 dark:border-white/20"
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
                        onChange={(event) => onColorChange(event.target.value)}
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
                                    'aspect-square rounded-xl border border-grey transition-colors dark:border-white/10',
                                    isSelected
                                        ? 'ring-2 ring-sky-blue/60 ring-offset-2 ring-offset-white dark:ring-[#a6ffff] dark:ring-offset-[#181e1c]'
                                        : 'hover:border-grey-2 dark:hover:border-white/40'
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
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-grey bg-grey-3 dark:border-white/10 dark:bg-white/5">
                <Icon name="content" className="size-5 text-black/40 dark:text-white/40" />
            </div>
            <p className="text-sm text-black/60 dark:text-white/70">
                {t('storybook.inspector.empty.title')}
            </p>
            <p className="text-xs text-black/40 dark:text-white/40">
                {t('storybook.inspector.empty.description')}
            </p>
        </div>
    ) : isImage && imageSrc ? (
        <div className="space-y-5">
            <div className="pt-6 px-6 pb-2">
                <img
                    src="https://storage.googleapis.com/ii-agent-public/generate-media/storybook/pirate-generated-2.png"
                    alt={t('storybook.inspector.imageMode.previewAlt')}
                    className="h-60 w-full rounded-2xl border border-grey object-cover dark:border-white/10"
                />
            </div>

            <div className="text-center">
                <p className="text-sm text-black/70 leading-relaxed dark:text-white/80">
                    {t('storybook.inspector.imageMode.promptLine1')}
                    <br />
                    {t('storybook.inspector.imageMode.promptLine2')}
                </p>
            </div>

            <div className="relative flex h-32 items-center justify-center">
                <svg
                    width="212"
                    height="160"
                    viewBox="0 0 212 160"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-full"
                    style={{ width: '190px' }}
                >
                    <path
                        d="M106.002 4L106.001 47.0225C106 69.1574 123.977 87.0843 146.111 87.0232L154.5 87L167.9 86.9664C190.03 86.911 208 104.836 208 126.966V156.5"
                        stroke="#A6FFFF"
                    />
                    <path
                        d="M105.998 4L105.999 47.0225C106 69.1574 88.0235 87.0843 65.8887 87.0232L57.5 87L44.1002 86.9664C21.9697 86.911 4 104.836 4 126.966V156.5"
                        stroke="#A6FFFF"
                    />
                    <circle cx="106" cy="4" r="4" fill="#BEE6F0" />
                    <circle cx="208" cy="156" r="4" fill="#BEE6F0" />
                    <circle cx="4" cy="156" r="4" fill="#BEE6F0" />
                </svg>
            </div>

            <div className="px-6 pb-6 pt-1">
                <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                        <img
                            src="https://storage.googleapis.com/ii-agent-public/generate-media/storybook/pirate-generated-3.png"
                            alt={t('storybook.inspector.imageMode.examples.face')}
                            className="h-30 w-full rounded-2xl border border-grey object-cover dark:border-white/10"
                        />
                        <div className="rounded-full bg-[#a6ffff] px-2 py-1 text-center text-[11px] text-[#181e1c]">
                            {t('storybook.inspector.imageMode.examples.face')}
                        </div>
                    </div>
                    <div className="space-y-2">
                        <img
                            src="https://storage.googleapis.com/ii-agent-public/generate-media/storybook/pirate-generated-1.png"
                            alt={t('storybook.inspector.imageMode.examples.hat')}
                            className="h-30 w-full rounded-2xl border border-grey object-cover dark:border-white/10"
                        />
                        <div className="rounded-full bg-[#a6ffff] px-2 py-1 text-center text-[11px] text-[#181e1c]">
                            {t('storybook.inspector.imageMode.examples.hat')}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    ) : (
        <div className="space-y-4 pr-12">
            {showTextControls && selectedElement.textContent && (
                <div ref={contentRef} className="space-y-2" onClick={() => setActiveRail('content')}>
                    <Label className={sectionTitleClassName}>
                        {t('storybook.inspector.sections.content')}
                    </Label>
                    <div className="relative">
                        <Textarea
                            value={textContent}
                            onChange={(event) =>
                                handleTextContentChange(event.target.value)
                            }
                            onBlur={handleTextContentBlur}
                            className={textareaClassName}
                            placeholder={t(
                                'storybook.inspector.content.placeholder'
                            )}
                        />
                        {/* AI Rewriting Overlay - only covers the content box */}
                        {isRewritingContent && (
                            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50 backdrop-blur-sm rounded-lg">
                                <div className="flex flex-col items-center gap-2">
                                    <Loader2 className="h-6 w-6 animate-spin text-sky-blue dark:text-[#a6ffff]" />
                                    <span className="text-xs font-medium text-white">
                                        {t(
                                            'storybook.inspector.status.generating'
                                        )}
                                    </span>
                                </div>
                            </div>
                        )}
                        <button
                            type="button"
                            onClick={handleAIRewrite}
                            disabled={!textContent.trim() || isRewritingContent}
                            className={cn(
                                "absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-md border border-[#a6ffff]/50 bg-[#bfefff] text-[#0f1511] transition-opacity",
                                (!textContent.trim() || isRewritingContent) && "opacity-50 cursor-not-allowed"
                            )}
                            title={
                                isRewritingContent
                                    ? t(
                                          'storybook.inspector.content.aiRewriting'
                                      )
                                    : t('storybook.inspector.content.aiRewrite')
                            }
                        >
                            {isRewritingContent ? (
                                <Loader2 className="size-4 animate-spin" />
                            ) : (
                                <Icon name="ai-magic" className="size-5 stroke-black" />
                            )}
                        </button>
                    </div>
                </div>
            )}

            {showTextControls && selectedElement.textContent && (
                <div className={dividerClassName} />
            )}

            {showTextControls && (
                <>
                    <div ref={typographyRef} className="space-y-3" onClick={() => setActiveRail('typography')}>
                        <div className="space-y-1.5">
                            <Label className={sectionTitleClassName}>
                                {t('storybook.inspector.typography.fontFamily')}
                            </Label>
                            <Select
                                value={fontFamily}
                                onValueChange={handleFontFamilyChange}
                            >
                                <SelectTrigger className={inputClassName}>
                                    <SelectValue
                                        placeholder={t(
                                            'storybook.inspector.typography.fontPlaceholder'
                                        )}
                                    />
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
                                    {t(
                                        'storybook.inspector.typography.fontWeight'
                                    )}
                                </Label>
                                <Select
                                    value={fontWeight}
                                    onValueChange={handleFontWeightChange}
                                >
                                <SelectTrigger className={inputClassName}>
                                    <SelectValue
                                        placeholder={t(
                                            'storybook.inspector.placeholders.weight'
                                        )}
                                    />
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
                                    {t('storybook.inspector.typography.fontSize')}
                                </Label>
                                <Select
                                    value={String(fontSize)}
                                    onValueChange={handleFontSizeChange}
                                >
                                    <SelectTrigger className={inputClassName}>
                                        <SelectValue
                                            placeholder={t(
                                                'storybook.inspector.placeholders.size'
                                            )}
                                        />
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
                                    {t(
                                        'storybook.inspector.typography.lineHeight'
                                    )}
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
                                    {t(
                                        'storybook.inspector.typography.letterSpacing'
                                    )}
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
                                {t(
                                    'storybook.inspector.typography.textAlignment'
                                )}
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
                                            toggleButtonBaseClassName,
                                            textAlign === value
                                                ? toggleButtonActiveClassName
                                                : toggleButtonInactiveClassName
                                        )}
                                    >
                                        <Icon className="h-5 w-5" />
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className={sectionTitleClassName}>
                                {t(
                                    'storybook.inspector.typography.textDecoration'
                                )}
                            </Label>
                            <div className="grid grid-cols-6 gap-2">
                                <button
                                    type="button"
                                    onClick={handleBoldToggle}
                                    className={cn(
                                        tabButtonBaseClassName,
                                        'font-semibold',
                                        isBold
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
                                    )}
                                >
                                    B
                                </button>
                                <button
                                    type="button"
                                    onClick={handleItalicToggle}
                                    className={cn(
                                        tabButtonBaseClassName,
                                        'italic',
                                        isItalic
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
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
                                        tabButtonBaseClassName,
                                        'underline',
                                        decorations.has('underline')
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
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
                                        tabButtonBaseClassName,
                                        'line-through',
                                        decorations.has('line-through')
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
                                    )}
                                >
                                    S
                                </button>
                                <button
                                    type="button"
                                    onClick={() => toggleDecoration('overline')}
                                    className={cn(
                                        tabButtonBaseClassName,
                                        decorations.has('overline')
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
                                    )}
                                    style={{ textDecoration: 'overline' }}
                                >
                                    O
                                </button>
                                <button
                                    type="button"
                                    onClick={handleTextTransformToggle}
                                    className={cn(
                                        tabButtonBaseClassName,
                                        textTransform === 'uppercase'
                                            ? tabButtonActiveClassName
                                            : tabButtonInactiveClassName
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

                    <div ref={textColorRef} className="space-y-4" onClick={() => setActiveRail('text')}>
                        {renderColorSection(
                            t('storybook.inspector.textColor.label'),
                            textColorMode,
                            handleTextColorModeChange,
                            textColor,
                            handleTextColorChange,
                            textGradient,
                            handleTextGradientChange,
                            STORYBOOK_TEXT_COLORS
                        )}
                        {textColorMode === 'solid' &&
                            renderOpacitySection(
                                textOpacity,
                                handleTextOpacityChange
                            )}
                    </div>

                    <div className={dividerClassName} />
                </>
            )}

            <div ref={backgroundRef} className="space-y-4" onClick={() => setActiveRail('background')}>
                <Label className={sectionTitleClassName}>
                    {t('storybook.inspector.sections.background')}
                </Label>
                <div className="grid grid-cols-2 gap-2">
                    {(['color', 'image'] as const).map((tab) => (
                        <button
                            key={tab}
                            type="button"
                            onClick={() => handleBackgroundTabChange(tab)}
                            className={cn(
                                tabButtonBaseClassName,
                                backgroundTab === tab
                                    ? tabButtonActiveClassName
                                    : tabButtonInactiveClassName
                            )}
                        >
                            {backgroundTabLabels[tab]}
                        </button>
                    ))}
                </div>

                {backgroundTab === 'color' ? (
                    <div className="space-y-4">
                        {renderColorSection(
                            t('storybook.inspector.background.colorLabel'),
                            bgColorMode,
                            handleBgColorModeChange,
                            bgColor,
                            handleBgColorChange,
                            bgGradient,
                            handleBgGradientChange,
                            STORYBOOK_TEXT_COLORS
                        )}
                        {bgColorMode === 'solid' &&
                            renderOpacitySection(
                                bgOpacity,
                                handleBgOpacityChange
                            )}
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="space-y-3">
                            <Label className={sectionTitleClassName}>
                                {t('storybook.inspector.background.imageSources')}
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
                                                tabButtonBaseClassName,
                                                backgroundImageTab === tab
                                                    ? tabButtonActiveClassName
                                                    : tabButtonInactiveClassName
                                            )}
                                        >
                                            {backgroundImageTabLabels[tab]}
                                        </button>
                                    )
                                )}
                            </div>
                        </div>

                        {backgroundImageTab === 'upload' && (
                            <div className="space-y-4">
                                <button
                                    onClick={handleUploadClick}
                                    className={cn(
                                        "w-full aspect-video rounded-2xl border border-grey bg-grey-3 flex flex-col items-center justify-center gap-2 text-black/40 transition-all group overflow-hidden relative hover:border-sky-blue/40 hover:text-black/60 dark:border-white/10 dark:bg-[#202927] dark:text-white/40 dark:hover:border-[#a6ffff]/30 dark:hover:text-white/60",
                                        isUploadingBackground &&
                                            "cursor-not-allowed opacity-70"
                                    )}
                                    disabled={isUploadingBackground}
                                >
                                    {backgroundImageUrl ? (
                                        <>
                                            <img
                                                src={backgroundImageUrl}
                                                alt={t(
                                                    'storybook.inspector.imageMode.previewAlt'
                                                )}
                                                className="w-full h-full object-cover"
                                            />
                                            <div
                                                className="absolute top-2 right-2 h-6 w-6 rounded-full bg-black/60 flex items-center justify-center text-white/80 hover:bg-black/80"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    handleBackgroundImageApply(
                                                        ''
                                                    )
                                                    setBackgroundImageInput('')
                                                }}
                                            >
                                                ×
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            {isUploadingBackground ? (
                                                <Loader2 className="h-8 w-8 animate-spin" />
                                            ) : (
                                                <Icon name="image" className="size-8 group-hover:scale-110 transition-transform" />
                                            )}
                                            <span className="text-xs">
                                                {isUploadingBackground
                                                    ? t(
                                                          'storybook.inspector.background.uploading'
                                                      )
                                                    : t(
                                                          'storybook.inspector.background.uploadCta'
                                                      )}
                                            </span>
                                        </>
                                    )}
                                </button>
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
                                        if (backgroundImageDebounceRef.current) {
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
                                    placeholder={t(
                                        'storybook.inspector.background.linkPlaceholder'
                                    )}
                                />
                                {backgroundImageUrl && (
                                    <div
                                        className="aspect-video rounded-2xl border border-grey bg-cover bg-center dark:border-white/10"
                                        style={{
                                            backgroundImage: `url("${backgroundImageUrl}")`
                                        }}
                                    />
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
                                        placeholder={t(
                                            'storybook.inspector.background.promptPlaceholder'
                                        )}
                                    />
                                    {/* AI Generating Background Overlay */}
                                    {isGeneratingBackground && (
                                        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50 backdrop-blur-sm rounded-lg">
                                            <div className="flex flex-col items-center gap-2">
                                                <Loader2 className="h-6 w-6 animate-spin text-sky-blue dark:text-[#a6ffff]" />
                                                <span className="text-xs font-medium text-white">
                                                    {t(
                                                        'storybook.inspector.status.generating'
                                                    )}
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                    <button
                                        type="button"
                                        onClick={handleAIGenerateBackground}
                                        disabled={!imagePrompt.trim() || isGeneratingBackground}
                                        className={cn(
                                            "absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-xl border border-[#a6ffff]/50 bg-[#bfefff] text-[#0f1511] transition-all",
                                            (!imagePrompt.trim() || isGeneratingBackground)
                                                ? "opacity-50 cursor-not-allowed"
                                                : "hover:scale-105"
                                        )}
                                        title={
                                            isGeneratingBackground
                                                ? t(
                                                      'storybook.inspector.background.aiGenerating'
                                                  )
                                                : t(
                                                      'storybook.inspector.background.aiGenerate'
                                                  )
                                        }
                                    >
                                        {isGeneratingBackground ? (
                                            <Loader2 className="size-5 animate-spin" />
                                        ) : (
                                            <Icon name="ai-magic" className="size-5 stroke-black" />
                                        )}
                                    </button>
                                </div>
                                {/* Preview of generated background */}
                                {backgroundImageUrl && !isGeneratingBackground && (
                                    <div
                                        className="w-full aspect-video rounded-2xl border border-grey bg-grey-3 flex flex-col items-center justify-center gap-2 text-black/40 transition-all group overflow-hidden relative bg-cover bg-center hover:border-sky-blue/40 hover:text-black/60 dark:border-white/10 dark:bg-[#202927] dark:text-white/40 dark:hover:border-[#a6ffff]/30 dark:hover:text-white/60"
                                        style={{
                                            backgroundImage: `url("${backgroundImageUrl}")`
                                        }}
                                    />
                                )}
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className={dividerClassName} />

            <div ref={borderRef} className="space-y-4" onClick={() => setActiveRail('border')}>
                {renderColorSection(
                    t('storybook.inspector.border.colorLabel'),
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
                            {t('storybook.inspector.border.style')}
                        </Label>
                        <Select
                            value={borderStyle}
                            onValueChange={handleBorderStyleChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue
                                    placeholder={t(
                                        'storybook.inspector.placeholders.style'
                                    )}
                                />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_STYLE_OPTIONS.map((opt) => (
                                    <SelectItem key={opt} value={opt}>
                                        {t(`storybook.inspector.borderStyle.${opt}`)}
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
                            {t('storybook.inspector.border.width')}
                        </Label>
                        <Select
                            value={borderWidth}
                            onValueChange={handleBorderWidthChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue
                                    placeholder={t(
                                        'storybook.inspector.placeholders.width'
                                    )}
                                />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_WIDTH_OPTIONS.map((opt) => (
                                    <SelectItem
                                        key={opt.value}
                                        value={opt.value}
                                    >
                                        {opt.labelKey
                                            ? t(opt.labelKey)
                                            : opt.label}
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
                            {t('storybook.inspector.border.radius')}
                        </Label>
                        <Select
                            value={String(borderRadius)}
                            onValueChange={handleBorderRadiusChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue
                                    placeholder={t(
                                        'storybook.inspector.placeholders.radius'
                                    )}
                                />
                            </SelectTrigger>
                            <SelectContent>
                                {BORDER_RADIUS_OPTIONS.map((opt) => (
                                    <SelectItem
                                        key={opt.value}
                                        value={String(opt.value)}
                                    >
                                        {opt.labelKey
                                            ? t(opt.labelKey)
                                            : opt.label}
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

            <div ref={spacingRef} className="space-y-3" onClick={() => setActiveRail('spacing')}>
                <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>
                            {t('storybook.inspector.spacing.padding')}
                        </Label>
                        <Select
                            value={String(padding)}
                            onValueChange={handlePaddingChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue
                                    placeholder={t(
                                        'storybook.inspector.spacing.padding'
                                    )}
                                />
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
                                        <SelectItem
                                            value={String(padding)}
                                        >
                                            {padding}px
                                        </SelectItem>
                                    )}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className={fieldLabelClassName}>
                            {t('storybook.inspector.spacing.margin')}
                        </Label>
                        <Select
                            value={String(margin)}
                            onValueChange={handleMarginChange}
                        >
                            <SelectTrigger className={inputClassName}>
                                <SelectValue
                                    placeholder={t(
                                        'storybook.inspector.spacing.margin'
                                    )}
                                />
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
                                        <SelectItem
                                            value={String(margin)}
                                        >
                                            {margin}px
                                        </SelectItem>
                                    )}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            <div className={dividerClassName} />

            <div ref={shadowRef} className="space-y-3" onClick={() => setActiveRail('shadow')}>
                <Label className={sectionTitleClassName}>
                    {t('storybook.inspector.shadow.label')}
                </Label>
                <Select value={shadow} onValueChange={handleShadowChange}>
                    <SelectTrigger className={inputClassName}>
                        <SelectValue
                            placeholder={t('storybook.inspector.shadow.placeholder')}
                        />
                    </SelectTrigger>
                    <SelectContent>
                        {SHADOW_PRESETS.map((preset) => (
                            <SelectItem key={preset.value} value={preset.value}>
                                {preset.labelKey
                                    ? t(preset.labelKey)
                                    : preset.label}
                            </SelectItem>
                        ))}
                        {shadow &&
                            !SHADOW_PRESETS.some(
                                (preset) => preset.value === shadow
                            ) && (
                                <SelectItem value={shadow}>
                                    {shadow}
                                </SelectItem>
                            )}
                    </SelectContent>
                </Select>
            </div>
        </div>
    )

    return (
        <div className={containerClassName}>
            <div className="flex min-w-0 flex-1 flex-col min-h-0">
                <div className="flex-1 min-h-0 overflow-y-auto pl-4 pr-4 py-4">
                    {panelContent}
                </div>
            </div>

            {!isImage && selectedElement && (
                <div className="absolute right-3 top-3 hidden flex-col items-center gap-1 rounded-xl bg-white/90 p-1 shadow-2xl backdrop-blur-sm dark:bg-[#181e1c] lg:flex">
                    {railItems.map(
                        ({ id, label, iconName, icon: LucideIcon, ref }) => (
                            <button
                                key={id}
                                type="button"
                                onClick={() => {
                                    setActiveRail(id)
                                    ref.current?.scrollIntoView({
                                        behavior: 'smooth',
                                        block: 'start'
                                    })
                                }}
                                className={cn(
                                    'flex h-8 w-8 items-center justify-center rounded-lg transition-colors',
                                    activeRail === id
                                        ? 'bg-sky-blue text-black dark:bg-[#a6ffff] dark:text-[#181e1c]'
                                        : 'bg-grey-3 text-black/60 hover:bg-grey-4 hover:text-black dark:bg-[#263533] dark:text-white/70 dark:hover:bg-[#2e3f3d] dark:hover:text-white'
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
