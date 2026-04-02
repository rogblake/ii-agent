/**
 * Inspector Sidebar Component
 *
 * A collapsible sidebar panel for editing element properties in design mode.
 * Based on the Netflix clone design panel pattern.
 */

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
    X,
    RotateCcw,
    Type,
    Palette,
    Square,
    Maximize2,
    FileText
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Textarea } from '@/components/ui/textarea'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '@/components/ui/select'
import {
    FONT_FAMILIES,
    FONT_WEIGHTS,
    FONT_SIZES,
    BORDER_RADIUS,
    SPACING,
    TAILWIND_COLORS
} from './tailwind-constants'
import type { ElementInfo } from './types'

interface InspectorSidebarProps {
    isOpen: boolean
    selectedElement: ElementInfo | null
    pendingChangesCount: number
    onClose: () => void
    onStyleChange: (property: string, value: string) => void
    onTextChange: (text: string) => void
    onReset: () => void
}

export function InspectorSidebar({
    isOpen,
    selectedElement,
    pendingChangesCount,
    onClose,
    onStyleChange,
    onTextChange,
    onReset
}: InspectorSidebarProps) {
    const { t } = useTranslation()
    // Local state for form controls
    const [fontFamily, setFontFamily] = useState('')
    const [textContent, setTextContent] = useState('')
    const [fontSize, setFontSize] = useState(FONT_SIZES.default)
    const [fontWeight, setFontWeight] = useState('')
    const [textColor, setTextColor] = useState('#000000')
    const [bgColor, setBgColor] = useState('#ffffff')
    const [borderRadius, setBorderRadius] = useState(BORDER_RADIUS.default)
    const [paddingTop, setPaddingTop] = useState(SPACING.default)
    const [paddingBottom, setPaddingBottom] = useState(SPACING.default)
    const [paddingLeft, setPaddingLeft] = useState(SPACING.default)
    const [paddingRight, setPaddingRight] = useState(SPACING.default)

    // Update form controls when selected element changes
    useEffect(() => {
        if (!selectedElement) return

        const styles = selectedElement.computedStyles

        // Set text content
        setTextContent(selectedElement.textContent || '')

        // Parse font family
        if (styles.fontFamily) {
            const found = FONT_FAMILIES.find(
                (f) =>
                    f.value &&
                    styles.fontFamily
                        .toLowerCase()
                        .includes(f.value.split(',')[0].toLowerCase().trim())
            )
            setFontFamily(found?.value || '')
        }

        // Parse font size
        const sizeMatch = styles.fontSize?.match(/(\d+)/)
        if (sizeMatch) {
            setFontSize(
                Math.max(
                    FONT_SIZES.min,
                    Math.min(FONT_SIZES.max, parseInt(sizeMatch[1], 10))
                )
            )
        }

        // Parse font weight
        if (styles.fontWeight) {
            const found = FONT_WEIGHTS.find(
                (w) => w.value === styles.fontWeight
            )
            setFontWeight(found?.value || '')
        }

        // Parse colors (convert rgb to hex)
        setTextColor(rgbToHex(styles.color) || '#000000')
        setBgColor(rgbToHex(styles.backgroundColor) || '#ffffff')

        // Parse border radius
        const radiusMatch = styles.borderRadius?.match(/(\d+)/)
        if (radiusMatch) {
            setBorderRadius(
                Math.max(
                    BORDER_RADIUS.min,
                    Math.min(BORDER_RADIUS.max, parseInt(radiusMatch[1], 10))
                )
            )
        }

        // Parse padding
        const paddingParts = styles.padding?.split(' ') || []
        if (paddingParts.length >= 1) {
            const top = parseInt(paddingParts[0], 10) || 0
            const right = parseInt(paddingParts[1] || paddingParts[0], 10) || 0
            const bottom = parseInt(paddingParts[2] || paddingParts[0], 10) || 0
            const left =
                parseInt(
                    paddingParts[3] || paddingParts[1] || paddingParts[0],
                    10
                ) || 0
            setPaddingTop(Math.min(SPACING.max, top))
            setPaddingRight(Math.min(SPACING.max, right))
            setPaddingBottom(Math.min(SPACING.max, bottom))
            setPaddingLeft(Math.min(SPACING.max, left))
        }
    }, [selectedElement])

    // Handlers for style changes
    const handleTextContentChange = useCallback((value: string) => {
        setTextContent(value)
    }, [])

    const handleTextContentBlur = useCallback(() => {
        onTextChange(textContent)
    }, [onTextChange, textContent])

    const handleFontFamilyChange = useCallback(
        (value: string) => {
            setFontFamily(value)
            onStyleChange('font-family', value)
        },
        [onStyleChange]
    )

    const handleFontSizeChange = useCallback(
        (value: number[]) => {
            setFontSize(value[0])
            onStyleChange('font-size', `${value[0]}px`)
        },
        [onStyleChange]
    )

    const handleFontWeightChange = useCallback(
        (value: string) => {
            setFontWeight(value)
            onStyleChange('font-weight', value)
        },
        [onStyleChange]
    )

    const handleTextColorChange = useCallback(
        (value: string) => {
            setTextColor(value)
            onStyleChange('color', value)
        },
        [onStyleChange]
    )

    const handleBgColorChange = useCallback(
        (value: string) => {
            setBgColor(value)
            onStyleChange('background-color', value)
        },
        [onStyleChange]
    )

    const handleBorderRadiusChange = useCallback(
        (value: number[]) => {
            setBorderRadius(value[0])
            onStyleChange('border-radius', `${value[0]}px`)
        },
        [onStyleChange]
    )

    const handlePaddingChange = useCallback(
        (side: 'top' | 'right' | 'bottom' | 'left', value: number[]) => {
            const v = value[0]
            switch (side) {
                case 'top':
                    setPaddingTop(v)
                    break
                case 'right':
                    setPaddingRight(v)
                    break
                case 'bottom':
                    setPaddingBottom(v)
                    break
                case 'left':
                    setPaddingLeft(v)
                    break
            }
            // Build padding shorthand
            const newPadding = `${side === 'top' ? v : paddingTop}px ${side === 'right' ? v : paddingRight}px ${side === 'bottom' ? v : paddingBottom}px ${side === 'left' ? v : paddingLeft}px`
            onStyleChange('padding', newPadding)
        },
        [onStyleChange, paddingTop, paddingRight, paddingBottom, paddingLeft]
    )

    // Get element label
    const elementLabel = selectedElement
        ? `${selectedElement.tagName}${selectedElement.id ? `#${selectedElement.id}` : ''}${selectedElement.className ? '.' + selectedElement.className.split(' ').slice(0, 2).join('.') : ''}`
        : t('designMode.inspectorSidebar.noSelectionInline')

    return (
        <div
            className={cn(
                'absolute top-0 right-0 h-full w-80 bg-[#1a1a24] border-l border-t border-white/10 shadow-2xl transition-transform duration-300 z-50 flex flex-col',
                isOpen ? 'translate-x-0' : 'translate-x-full'
            )}
            data-design-ignore="true"
        >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">
                        {t('designMode.inspectorSidebar.title')}
                    </span>
                    {pendingChangesCount > 0 && (
                        <span className="px-2 py-0.5 text-xs bg-purple-600 text-white rounded-full">
                            {t(
                                'designMode.inspectorSidebar.changesCount',
                                {
                                    count: pendingChangesCount
                                }
                            )}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-gray-400 hover:text-white"
                        onClick={onReset}
                        title={t('designMode.inspectorSidebar.resetStyles')}
                    >
                        <RotateCcw className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-gray-400 hover:text-white"
                        onClick={onClose}
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Selected Element Label */}
            <div className="px-4 py-2 border-b border-white/10 bg-white/5">
                <p className="text-xs text-gray-400 truncate font-mono">
                    {elementLabel}
                </p>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {selectedElement ? (
                    <>
                        {/* Text Content Section */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-gray-400">
                                <FileText className="h-4 w-4" />
                                <span className="text-xs font-medium uppercase tracking-wider">
                                    {t(
                                        'designMode.inspectorSidebar.sections.textContent'
                                    )}
                                </span>
                            </div>

                            <div className="space-y-1.5">
                                <Label className="text-xs text-gray-400">
                                    {t(
                                        'designMode.inspectorSidebar.labels.content'
                                    )}
                                </Label>
                                <Textarea
                                    value={textContent}
                                    onChange={(e) =>
                                        handleTextContentChange(e.target.value)
                                    }
                                    onBlur={handleTextContentBlur}
                                    placeholder={t(
                                        'designMode.inspectorSidebar.placeholders.textContent'
                                    )}
                                    className="min-h-[80px] bg-white/5 border-white/10 text-white text-sm resize-none"
                                />
                            </div>
                        </section>

                        {/* Typography Section */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-gray-400">
                                <Type className="h-4 w-4" />
                                <span className="text-xs font-medium uppercase tracking-wider">
                                    {t(
                                        'designMode.inspectorSidebar.sections.typography'
                                    )}
                                </span>
                            </div>

                            <div className="space-y-3">
                                {/* Font Family */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.fontFamily'
                                        )}
                                    </Label>
                                    <Select
                                        value={fontFamily}
                                        onValueChange={handleFontFamilyChange}
                                    >
                                        <SelectTrigger className="h-8 bg-white/5 border-white/10 text-white text-sm">
                                            <SelectValue
                                                placeholder={t(
                                                    'designMode.inspectorSidebar.placeholders.fontFamily'
                                                )}
                                            />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {FONT_FAMILIES.map((font) => (
                                                <SelectItem
                                                    key={font.label}
                                                    value={
                                                        font.value || 'default'
                                                    }
                                                >
                                                    {font.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Font Size */}
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs text-gray-400">
                                            {t(
                                                'designMode.inspectorSidebar.labels.fontSize'
                                            )}
                                        </Label>
                                        <span className="text-xs text-gray-500">
                                            {fontSize}px
                                        </span>
                                    </div>
                                    <Slider
                                        value={[fontSize]}
                                        min={FONT_SIZES.min}
                                        max={FONT_SIZES.max}
                                        step={1}
                                        onValueChange={handleFontSizeChange}
                                        className="py-1"
                                    />
                                </div>

                                {/* Font Weight */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.fontWeight'
                                        )}
                                    </Label>
                                    <Select
                                        value={fontWeight}
                                        onValueChange={handleFontWeightChange}
                                    >
                                        <SelectTrigger className="h-8 bg-white/5 border-white/10 text-white text-sm">
                                            <SelectValue
                                                placeholder={t(
                                                    'designMode.inspectorSidebar.placeholders.fontWeight'
                                                )}
                                            />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {FONT_WEIGHTS.map((weight) => (
                                                <SelectItem
                                                    key={weight.label}
                                                    value={
                                                        weight.value ||
                                                        'default'
                                                    }
                                                >
                                                    {weight.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        </section>

                        {/* Colors Section */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-gray-400">
                                <Palette className="h-4 w-4" />
                                <span className="text-xs font-medium uppercase tracking-wider">
                                    {t(
                                        'designMode.inspectorSidebar.sections.colors'
                                    )}
                                </span>
                            </div>

                            <div className="space-y-3">
                                {/* Text Color */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.textColor'
                                        )}
                                    </Label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="color"
                                            value={textColor}
                                            onChange={(e) =>
                                                handleTextColorChange(
                                                    e.target.value
                                                )
                                            }
                                            className="w-8 h-8 rounded cursor-pointer bg-transparent"
                                        />
                                        <input
                                            type="text"
                                            value={textColor}
                                            onChange={(e) =>
                                                handleTextColorChange(
                                                    e.target.value
                                                )
                                            }
                                            className="flex-1 h-8 px-2 bg-white/5 border border-white/10 rounded text-sm text-white font-mono"
                                        />
                                    </div>
                                </div>

                                {/* Background Color */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.backgroundColor'
                                        )}
                                    </Label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="color"
                                            value={bgColor}
                                            onChange={(e) =>
                                                handleBgColorChange(
                                                    e.target.value
                                                )
                                            }
                                            className="w-8 h-8 rounded cursor-pointer bg-transparent"
                                        />
                                        <input
                                            type="text"
                                            value={bgColor}
                                            onChange={(e) =>
                                                handleBgColorChange(
                                                    e.target.value
                                                )
                                            }
                                            className="flex-1 h-8 px-2 bg-white/5 border border-white/10 rounded text-sm text-white font-mono"
                                        />
                                    </div>
                                </div>

                                {/* Quick Colors */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.quickColors'
                                        )}
                                    </Label>
                                    <div className="flex flex-wrap gap-1">
                                        {TAILWIND_COLORS.slice(0, 14).map(
                                            (color) => (
                                                <button
                                                    key={color}
                                                    className="w-5 h-5 rounded border border-white/20 hover:scale-110 transition-transform"
                                                    style={{
                                                        backgroundColor: color
                                                    }}
                                                    onClick={() =>
                                                        handleBgColorChange(
                                                            color
                                                        )
                                                    }
                                                    title={color}
                                                />
                                            )
                                        )}
                                    </div>
                                </div>
                            </div>
                        </section>

                        {/* Border Section */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-gray-400">
                                <Square className="h-4 w-4" />
                                <span className="text-xs font-medium uppercase tracking-wider">
                                    {t(
                                        'designMode.inspectorSidebar.sections.border'
                                    )}
                                </span>
                            </div>

                            <div className="space-y-1.5">
                                <div className="flex items-center justify-between">
                                    <Label className="text-xs text-gray-400">
                                        {t(
                                            'designMode.inspectorSidebar.labels.borderRadius'
                                        )}
                                    </Label>
                                    <span className="text-xs text-gray-500">
                                        {borderRadius}px
                                    </span>
                                </div>
                                <Slider
                                    value={[borderRadius]}
                                    min={BORDER_RADIUS.min}
                                    max={BORDER_RADIUS.max}
                                    step={1}
                                    onValueChange={handleBorderRadiusChange}
                                    className="py-1"
                                />
                            </div>
                        </section>

                        {/* Spacing Section */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-gray-400">
                                <Maximize2 className="h-4 w-4" />
                                <span className="text-xs font-medium uppercase tracking-wider">
                                    {t(
                                        'designMode.inspectorSidebar.sections.padding'
                                    )}
                                </span>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                {/* Top */}
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs text-gray-400">
                                            {t(
                                                'designMode.inspectorSidebar.labels.top'
                                            )}
                                        </Label>
                                        <span className="text-xs text-gray-500">
                                            {paddingTop}px
                                        </span>
                                    </div>
                                    <Slider
                                        value={[paddingTop]}
                                        min={SPACING.min}
                                        max={SPACING.max}
                                        step={1}
                                        onValueChange={(v) =>
                                            handlePaddingChange('top', v)
                                        }
                                        className="py-1"
                                    />
                                </div>

                                {/* Bottom */}
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs text-gray-400">
                                            {t(
                                                'designMode.inspectorSidebar.labels.bottom'
                                            )}
                                        </Label>
                                        <span className="text-xs text-gray-500">
                                            {paddingBottom}px
                                        </span>
                                    </div>
                                    <Slider
                                        value={[paddingBottom]}
                                        min={SPACING.min}
                                        max={SPACING.max}
                                        step={1}
                                        onValueChange={(v) =>
                                            handlePaddingChange('bottom', v)
                                        }
                                        className="py-1"
                                    />
                                </div>

                                {/* Left */}
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs text-gray-400">
                                            {t(
                                                'designMode.inspectorSidebar.labels.left'
                                            )}
                                        </Label>
                                        <span className="text-xs text-gray-500">
                                            {paddingLeft}px
                                        </span>
                                    </div>
                                    <Slider
                                        value={[paddingLeft]}
                                        min={SPACING.min}
                                        max={SPACING.max}
                                        step={1}
                                        onValueChange={(v) =>
                                            handlePaddingChange('left', v)
                                        }
                                        className="py-1"
                                    />
                                </div>

                                {/* Right */}
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs text-gray-400">
                                            {t(
                                                'designMode.inspectorSidebar.labels.right'
                                            )}
                                        </Label>
                                        <span className="text-xs text-gray-500">
                                            {paddingRight}px
                                        </span>
                                    </div>
                                    <Slider
                                        value={[paddingRight]}
                                        min={SPACING.min}
                                        max={SPACING.max}
                                        step={1}
                                        onValueChange={(v) =>
                                            handlePaddingChange('right', v)
                                        }
                                        className="py-1"
                                    />
                                </div>
                            </div>
                        </section>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-center text-gray-500">
                        <p className="text-sm">
                            {t(
                                'designMode.inspectorSidebar.noSelectionMessage'
                            )}
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}

// Helper function to convert RGB to Hex
function rgbToHex(color: string): string {
    if (!color) return '#ffffff'
    if (color.startsWith('#')) {
        if (color.length === 4) {
            return (
                '#' +
                color
                    .slice(1)
                    .split('')
                    .map((c) => c + c)
                    .join('')
            )
        }
        return color
    }
    if (color === 'transparent' || color === 'rgba(0, 0, 0, 0)') {
        return '#ffffff'
    }
    const matches = color.match(/\d+/g)
    if (!matches || matches.length < 3) return '#ffffff'
    const [r, g, b] = matches
    const toHex = (value: string) =>
        Math.max(0, Math.min(255, parseInt(value, 10)))
            .toString(16)
            .padStart(2, '0')
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}
