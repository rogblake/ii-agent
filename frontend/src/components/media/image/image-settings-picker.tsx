import { useMemo, useState } from 'react'
import type { ReactElement } from 'react'

import { Icon } from '../../ui/icon'
import { useTranslation } from 'react-i18next'
import { useIsMobile } from '@/hooks/use-mobile'
import { Popover, PopoverContent, PopoverTrigger } from '../../ui/popover'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuTrigger
} from '../../ui/dropdown-menu'
import { cn } from '@/lib/utils'
import type {
    ImageAspectRatio,
    ImageResolution,
    PageCount,
    TextPosition,
    StorybookLanguage,
    StorybookGenre
} from '@/typings/agent'

const ALL_ASPECT_RATIOS: { value: ImageAspectRatio; label: string }[] = [
    { value: '1:1', label: '1:1' },
    { value: '2:3', label: '2:3' },
    { value: '3:2', label: '3:2' },
    { value: '3:4', label: '3:4' },
    { value: '4:3', label: '4:3' },
    { value: '9:16', label: '9:16' },
    { value: '16:9', label: '16:9' },
    { value: '21:9', label: '21:9' }
]

// Default aspect ratios if model doesn't specify
const DEFAULT_ASPECT_RATIOS: ImageAspectRatio[] = [
    '1:1',
    '2:3',
    '3:2',
    '4:3',
    '9:16',
    '16:9'
]

// All possible resolutions with their pro status
const RESOLUTION_CONFIG: Record<
    ImageResolution,
    { label: string; isPro: boolean }
> = {
    '1K': { label: '1K', isPro: false },
    '2K': { label: '2K', isPro: false },
    '4K': { label: '4K', isPro: true },
    '8K': { label: '8K', isPro: true }
}

// Default resolutions if model doesn't specify
const DEFAULT_RESOLUTIONS: ImageResolution[] = ['1K', '2K', '4K', '8K']

interface AspectRatioPickerProps {
    aspectRatio: ImageAspectRatio
    onAspectRatioChange: (ratio: ImageAspectRatio) => void
    disabled?: boolean
    supportedAspectRatios?: ImageAspectRatio[]
    className?: string
    textPosition?: TextPosition
    modelName?: string
}

// Aspect ratio restrictions for separate_page mode per model
const SEPARATE_PAGE_ASPECT_RATIOS: Record<string, ImageAspectRatio[]> = {
    'nano-banana-pro': ['1:1', '2:3', '3:4', '4:3', '9:16', '16:9'],
    'gemini-3-pro-image-preview': ['1:1', '2:3', '3:4', '4:3', '9:16', '16:9'],
    'gpt-image-1.5': ['1:1', '2:3', '3:2'],
    default: ['1:1', '2:3', '3:4']
}

function getSeparatePageAspectRatios(
    modelName: string | undefined
): ImageAspectRatio[] {
    if (!modelName) return SEPARATE_PAGE_ASPECT_RATIOS['default']
    return (
        SEPARATE_PAGE_ASPECT_RATIOS[modelName] ??
        SEPARATE_PAGE_ASPECT_RATIOS['default']
    )
}

type PageCountConfig = { label?: string; labelKey?: string; isPro: boolean }

// All possible page counts with their pro status
const PAGE_COUNT_CONFIG: Record<PageCount, PageCountConfig> = {
    4: { label: '4', isPro: false },
    8: { label: '8', isPro: false },
    12: { label: '12', isPro: true },
    unlimited: { labelKey: 'media.imageSettings.unlimited', isPro: true }
}

// Default page counts
const DEFAULT_PAGE_COUNTS: PageCount[] = [4, 8, 12, 'unlimited']

interface PagePickerProps {
    pageCount: PageCount
    onPageCountChange: (count: PageCount) => void
    disabled?: boolean
    isPro?: boolean
    className?: string
}

const calculateAspectRatioDimensions = (
    ratio: string
): {
    width: number
    height: number
} => {
    const [width, height] = ratio.split(':').map(Number)
    const maxSize = 60
    const aspectRatioValue = width / height

    if (aspectRatioValue > 1) {
        return { width: maxSize, height: maxSize / aspectRatioValue }
    }
    return { width: maxSize * aspectRatioValue, height: maxSize }
}

export function AspectRatioPicker({
    aspectRatio,
    onAspectRatioChange,
    disabled,
    supportedAspectRatios,
    className,
    textPosition,
    modelName
}: AspectRatioPickerProps): ReactElement {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const aspectRatios = useMemo(() => {
        // When in separate_page mode, use the separate_page ratios directly
        if (textPosition === 'separate_page') {
            const separatePageRatios = getSeparatePageAspectRatios(modelName)
            return ALL_ASPECT_RATIOS.filter((ratio) =>
                separatePageRatios.includes(ratio.value)
            )
        }

        const supported = supportedAspectRatios ?? DEFAULT_ASPECT_RATIOS
        return ALL_ASPECT_RATIOS.filter((ratio) =>
            supported.includes(ratio.value)
        )
    }, [supportedAspectRatios, textPosition, modelName])

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.imageSettings.ratio')}:</span>
                    <span>{aspectRatio}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent
                className="w-auto p-0 !bg-white border-none shadow-btn rounded-xl"
                align="start"
                sideOffset={8}
            >
                <div className="p-3">
                    <div className="text-base font-semibold text-black mb-3">
                        {t('media.imageSettings.ratio')}
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        {aspectRatios.map((ratio) => {
                            const dimensions = calculateAspectRatioDimensions(
                                ratio.value
                            )
                            return (
                                <button
                                    key={ratio.value}
                                    type="button"
                                    onClick={() => {
                                        onAspectRatioChange(ratio.value)
                                        setOpen(false)
                                    }}
                                    className="cursor-pointer flex items-center justify-center"
                                >
                                    <div
                                        className={cn(
                                            'rounded-xl transition-all flex items-center justify-center font-light border-2',
                                            aspectRatio === ratio.value
                                                ? 'bg-white border-black text-black text-xs'
                                                : 'bg-white border-grey text-black text-xs hover:border-grey-2'
                                        )}
                                        style={{
                                            width: `${dimensions.width}px`,
                                            height: `${dimensions.height}px`
                                        }}
                                    >
                                        {aspectRatio === ratio.value ? (
                                            <Icon
                                                name="tick"
                                                className="size-4 fill-black"
                                            />
                                        ) : (
                                            <span>{ratio.label}</span>
                                        )}
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

interface ResolutionPickerProps {
    resolution: ImageResolution
    onResolutionChange: (resolution: ImageResolution) => void
    disabled?: boolean
    isPro?: boolean
    supportedResolutions?: ImageResolution[]
    className?: string
}

export function ResolutionPicker({
    resolution,
    onResolutionChange,
    disabled,
    isPro = false,
    supportedResolutions,
    className
}: ResolutionPickerProps): ReactElement {
    const { t } = useTranslation()

    const resolutions = useMemo(() => {
        const supported = supportedResolutions ?? DEFAULT_RESOLUTIONS
        return supported.map((res) => ({
            value: res,
            label: RESOLUTION_CONFIG[res].label,
            isPro: RESOLUTION_CONFIG[res].isPro
        }))
    }, [supportedResolutions])

    const handleResolutionChange = (res: ImageResolution): void => {
        const resOption = resolutions.find((r) => r.value === res)
        if (resOption?.isPro && !isPro) return
        onResolutionChange(res)
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.imageSettings.resolution')}</span>
                    <span>{resolution}</span>
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-40 px-0 py-1 !bg-white shadow-btn rounded-xl"
                align="start"
                sideOffset={8}
            >
                <DropdownMenuLabel className="text-base font-semibold text-black px-3 py-1">
                    {t('media.imageSettings.resolution')}
                </DropdownMenuLabel>
                {resolutions.map((res) => {
                    const isDisabled = res.isPro && !isPro
                    return (
                        <DropdownMenuItem
                            key={res.value}
                            onClick={() => handleResolutionChange(res.value)}
                            disabled={isDisabled}
                            className={cn(
                                'flex items-center justify-between py-2 px-3 text-xs rounded-md',
                                'text-black',
                                isDisabled && 'opacity-50 cursor-not-allowed'
                            )}
                        >
                            <span>{res.label}</span>
                            <div className="ml-auto flex items-center justify-end gap-2">
                                {res.isPro && (
                                    <span className="px-1.5 py-0.5 text-[10px] rounded-full font-semibold bg-orange-3 text-black">
                                        {t('media.imageSettings.proPlan')}
                                    </span>
                                )}
                                {resolution === res.value && (
                                    <span className="w-4 flex justify-end">
                                        <Icon
                                            name="tick"
                                            className="size-4 fill-black"
                                        />
                                    </span>
                                )}
                            </div>
                        </DropdownMenuItem>
                    )
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export function PagePicker({
    pageCount,
    onPageCountChange,
    disabled,
    isPro = false,
    className
}: PagePickerProps): ReactElement {
    const { t } = useTranslation()
    const pageCountOptions = useMemo(
        () =>
            DEFAULT_PAGE_COUNTS.map((count) => {
                const config = PAGE_COUNT_CONFIG[count]
                return {
                    value: count,
                    label: config?.labelKey
                        ? t(config.labelKey)
                        : (config?.label ?? String(count)),
                    isPro: config?.isPro ?? false
                }
            }),
        [t]
    )

    const pageCountLabel = useMemo(() => {
        const config = PAGE_COUNT_CONFIG[pageCount]
        if (config?.labelKey) return t(config.labelKey)
        return config?.label ?? String(pageCount)
    }, [pageCount, t])

    const handlePageCountChange = (count: PageCount): void => {
        const pageOption = pageCountOptions.find((p) => p.value === count)
        if (pageOption?.isPro && !isPro) return
        onPageCountChange(count)
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.imageSettings.pages')}:</span>
                    <span>{pageCountLabel}</span>
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-56 px-0 py-1 !bg-white shadow-btn"
                align="start"
                sideOffset={8}
            >
                <DropdownMenuLabel className="text-base font-semibold text-black px-3 py-1">
                    {t('media.imageSettings.pages')}
                </DropdownMenuLabel>
                {pageCountOptions.map((page) => {
                    const isDisabled = page.isPro && !isPro
                    return (
                        <DropdownMenuItem
                            key={page.value}
                            onClick={() => handlePageCountChange(page.value)}
                            disabled={isDisabled}
                            className={cn(
                                'flex items-center justify-between px-3 py-2 text-xs rounded-md',
                                'text-black',
                                isDisabled && 'opacity-50 cursor-not-allowed'
                            )}
                        >
                            <span>
                                {page.label}{' '}
                                {t('media.imageSettings.pagesLabel')}
                            </span>
                            <div className="ml-auto flex items-center justify-end gap-2">
                                {pageCount === page.value ? (
                                    <span className="w-4 flex justify-end">
                                        <Icon
                                            name="tick"
                                            className="size-4 fill-black"
                                        />
                                    </span>
                                ) : (
                                    page.isPro && (
                                        <span className="px-1.5 py-0.5 text-[10px] rounded-full font-semibold bg-orange-3 text-black">
                                            {t('media.imageSettings.proPlan')}
                                        </span>
                                    )
                                )}
                            </div>
                        </DropdownMenuItem>
                    )
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

interface TextIncludedPickerProps {
    textPosition: TextPosition
    onTextPositionChange: (position: TextPosition) => void
    disabled?: boolean
    className?: string
}

export function TextIncludedPicker({
    textPosition,
    onTextPositionChange,
    disabled,
    className
}: TextIncludedPickerProps): ReactElement {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const formatTextPosition = (position: TextPosition): string => {
        if (position === 'none')
            return t('media.imageSettings.textPosition.none')
        return t(`media.imageSettings.textPosition.${position}`)
    }

    const handlePositionChange = (position: TextPosition): void => {
        onTextPositionChange(position)
        setOpen(false)
    }

    const renderPositionCard = (
        position: 'left' | 'right' | 'top' | 'bottom'
    ) => {
        const isSelected = textPosition === position
        return (
            <button
                key={position}
                type="button"
                onClick={() => handlePositionChange(position)}
                className={cn(
                    'cursor-pointer h-24 w-32 rounded-xl transition-all overflow-hidden border-2',
                    isSelected
                        ? 'border-black'
                        : 'border-grey hover:border-grey-2'
                )}
            >
                {position === 'left' && (
                    <div className="flex h-full">
                        <div
                            className={cn(
                                'w-12',
                                isSelected ? 'bg-[#181e1c]' : 'bg-grey/60'
                            )}
                        />
                        <div className="flex-1 bg-white flex items-center justify-center text-sm font-normal text-black">
                            {isSelected ? (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            ) : (
                                t('media.imageSettings.textPosition.left')
                            )}
                        </div>
                    </div>
                )}
                {position === 'right' && (
                    <div className="flex h-full">
                        <div className="flex-1 bg-white flex items-center justify-center text-sm font-normal text-black">
                            {isSelected ? (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            ) : (
                                t('media.imageSettings.textPosition.right')
                            )}
                        </div>
                        <div
                            className={cn(
                                'w-12',
                                isSelected ? 'bg-[#181e1c]' : 'bg-grey/60'
                            )}
                        />
                    </div>
                )}
                {position === 'top' && (
                    <div className="flex flex-col h-full">
                        <div
                            className={cn(
                                'h-8',
                                isSelected ? 'bg-[#181e1c]' : 'bg-grey/60'
                            )}
                        />
                        <div className="flex-1 bg-white flex items-center justify-center text-sm font-normal text-black">
                            {isSelected ? (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            ) : (
                                t('media.imageSettings.textPosition.top')
                            )}
                        </div>
                    </div>
                )}
                {position === 'bottom' && (
                    <div className="flex flex-col h-full">
                        <div className="flex-1 bg-white flex items-center justify-center text-sm font-normal text-black">
                            {isSelected ? (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            ) : (
                                t('media.imageSettings.textPosition.bottom')
                            )}
                        </div>
                        <div
                            className={cn(
                                'h-8',
                                isSelected ? 'bg-[#181e1c]' : 'bg-grey/60'
                            )}
                        />
                    </div>
                )}
            </button>
        )
    }

    const renderSeparatePageCard = () => {
        const isSelected = textPosition === 'separate_page'
        return (
            <button
                type="button"
                onClick={() => handlePositionChange('separate_page')}
                className={cn(
                    'cursor-pointer rounded-2xl transition-all overflow-hidden border-2 bg-white flex flex-col',
                    'w-48 p-1 h-full',
                    isSelected
                        ? 'border-black'
                        : 'border-grey hover:border-grey-2'
                )}
            >
                <div className="flex items-center justify-center mb-3">
                    <div className="w-full h-22 rounded-xl overflow-hidden flex bg-grey/5">
                        <div
                            className={cn(
                                'w-1/2 h-full mr-1',
                                isSelected ? 'bg-[#bee6f0]' : 'bg-grey/60'
                            )}
                        />
                        <div
                            className={cn(
                                'w-1/2 h-full flex flex-col gap-1.5 p-3 justify-center',
                                isSelected ? 'bg-[#181e1c]' : 'bg-grey/100'
                            )}
                        >
                            <div className="w-full h-1.5 bg-white rounded-sm" />
                            <div className="w-full h-1.5 bg-white rounded-sm" />
                            <div className="w-full h-1.5 bg-white rounded-sm" />
                            <div className="w-full h-1.5 bg-white rounded-sm" />
                            <div className="w-full h-1.5 bg-white rounded-sm" />
                            <div className="w-2/3 h-1.5 bg-white rounded-sm" />
                        </div>
                    </div>
                </div>
                <div className="flex flex-col items-center justify-center mb-3">
                    {isSelected ? (
                        <Icon name="tick" className="size-4 fill-black" />
                    ) : (
                        <span className="text-base text-black text-center leading-tight text-[14px]">
                            {t(
                                'media.imageSettings.textPosition.separate_page'
                            )}
                        </span>
                    )}
                </div>
                <div className="text-center mt-auto pb-4 px-2">
                    <p
                        className={cn(
                            'text-[12px] leading-snug font-normal',
                            isSelected ? 'text-[#181e1c]' : 'text-gray-400'
                        )}
                    >
                        {t('media.imageSettings.separatePageDescription')}
                    </p>
                </div>
            </button>
        )
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.imageSettings.textIncluded')}:</span>
                    <span>{formatTextPosition(textPosition)}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent
                className="w-auto p-0 !bg-white border-none shadow-btn rounded-xl"
                align="start"
                sideOffset={8}
            >
                <div className="p-3">
                    <div className="text-base font-semibold text-black mb-3">
                        {t('media.imageSettings.textIncluded')}
                    </div>

                    <div className="flex gap-3 mb-3">
                        <div className="grid grid-cols-2 gap-3">
                            {renderPositionCard('left')}
                            {renderPositionCard('right')}
                            {renderPositionCard('top')}
                            {renderPositionCard('bottom')}
                        </div>
                        {renderSeparatePageCard()}
                    </div>

                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={() => handlePositionChange('none')}
                            className={cn(
                                'cursor-pointer flex-1 px-3 py-2 text-xs rounded-md transition-colors font-medium',
                                textPosition === 'none'
                                    ? 'bg-[#bee6f0] text-black'
                                    : 'bg-[#ebf7fc] text-black'
                            )}
                        >
                            {t('media.imageSettings.noText')}
                        </button>
                        <button
                            type="button"
                            onClick={() => handlePositionChange('left')}
                            className={cn(
                                'cursor-pointer flex-1 px-3 py-2 text-xs rounded-md font-medium',
                                textPosition !== 'none'
                                    ? 'bg-[#bee6f0] text-black'
                                    : 'bg-[#ebf7fc] text-black'
                            )}
                        >
                            {t('media.imageSettings.textIncluded')}
                        </button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

const STORYBOOK_LANGUAGE_LABEL_KEYS: Record<StorybookLanguage, string> = {
    English: 'media.imageSettings.languages.english',
    Vietnamese: 'media.imageSettings.languages.vietnamese',
    Japanese: 'media.imageSettings.languages.japanese',
    Hindi: 'media.imageSettings.languages.hindi',
    Korean: 'media.imageSettings.languages.korean'
}

// Language options for storybook
const LANGUAGE_OPTIONS: { value: StorybookLanguage; labelKey: string }[] = [
    { value: 'English', labelKey: STORYBOOK_LANGUAGE_LABEL_KEYS.English },
    { value: 'Vietnamese', labelKey: STORYBOOK_LANGUAGE_LABEL_KEYS.Vietnamese },
    { value: 'Japanese', labelKey: STORYBOOK_LANGUAGE_LABEL_KEYS.Japanese },
    { value: 'Hindi', labelKey: STORYBOOK_LANGUAGE_LABEL_KEYS.Hindi },
    { value: 'Korean', labelKey: STORYBOOK_LANGUAGE_LABEL_KEYS.Korean }
]

interface LanguagePickerProps {
    language: StorybookLanguage
    onLanguageChange: (language: StorybookLanguage) => void
    disabled?: boolean
    className?: string
}

export function LanguagePicker({
    language,
    onLanguageChange,
    disabled,
    className
}: LanguagePickerProps): ReactElement {
    const { t } = useTranslation()
    const languageLabel = t(STORYBOOK_LANGUAGE_LABEL_KEYS[language])

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <span>{t('media.imageSettings.language')}:</span>
                    <span>{languageLabel}</span>
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-40 px-0 py-1 !bg-white shadow-btn"
                align="start"
                sideOffset={8}
            >
                <DropdownMenuLabel className="text-base font-semibold text-black px-3 py-1">
                    {t('media.imageSettings.language')}
                </DropdownMenuLabel>
                {LANGUAGE_OPTIONS.map((lang) => (
                    <DropdownMenuItem
                        key={lang.value}
                        onClick={() => onLanguageChange(lang.value)}
                        className="flex items-center justify-between px-3 py-2 text-xs rounded-md text-black"
                    >
                        <span>{t(lang.labelKey)}</span>
                        <span className="w-4 flex justify-end">
                            {language === lang.value && (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            )}
                        </span>
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

type StorybookStyle = 'storybook' | 'manga'

const STORYBOOK_STYLE_OPTIONS: {
    value: StorybookStyle
    labelKey: string
    icon: string
}[] = [
    {
        value: 'storybook',
        labelKey: 'media.imageSettings.styles.storybook',
        icon: 'storybook'
    },
    {
        value: 'manga',
        labelKey: 'media.imageSettings.styles.manga',
        icon: 'manga'
    }
]

interface StorybookStylePickerProps {
    mangaLayout: boolean
    onMangaLayoutChange: (enabled: boolean) => void
    disabled?: boolean
    compact?: boolean
    className?: string
}

export function StorybookStylePicker({
    mangaLayout,
    onMangaLayoutChange,
    disabled,
    compact = false,
    className
}: StorybookStylePickerProps): ReactElement {
    const { t } = useTranslation()
    const isMobile = useIsMobile()
    const selectedStyle: StorybookStyle = mangaLayout ? 'manga' : 'storybook'
    const selectedOption = STORYBOOK_STYLE_OPTIONS.find(
        (opt) => opt.value === selectedStyle
    )

    if (isMobile) {
        return (
            <DropdownMenu>
                <DropdownMenuTrigger asChild disabled={disabled}>
                    <button
                        className={cn(
                            'inline-flex items-center gap-1 rounded-full px-2 h-7 text-xs text-black dark:text-sky-blue-2',
                            'bg-charcoal/10 dark:bg-sky-blue-2/10 cursor-pointer',
                            disabled && 'opacity-50 pointer-events-none',
                            className
                        )}
                    >
                        <Icon
                            name={selectedOption?.icon ?? 'mode-storybook'}
                            className="size-4"
                        />
                        <span>{t(selectedOption?.labelKey ?? '')}</span>
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                    align="start"
                    className="min-w-[200px] p-2"
                >
                    <DropdownMenuLabel className="!text-base font-semibold">
                        {t('media.imageSettings.layoutMode')}
                    </DropdownMenuLabel>
                    {STORYBOOK_STYLE_OPTIONS.map((option) => {
                        const isSelected = selectedStyle === option.value
                        return (
                            <DropdownMenuItem
                                key={option.value}
                                onClick={() =>
                                    onMangaLayoutChange(
                                        option.value === 'manga'
                                    )
                                }
                                className="flex items-center justify-between"
                            >
                                <span>{t(option.labelKey)}</span>
                                {isSelected && (
                                    <Icon
                                        name="tick"
                                        className="size-4 fill-black"
                                    />
                                )}
                            </DropdownMenuItem>
                        )
                    })}
                </DropdownMenuContent>
            </DropdownMenu>
        )
    }

    return (
        <div className="flex items-center gap-2">
            <div
                role="radiogroup"
                aria-label={t('media.imageSettings.style')}
                className={cn(
                    'inline-flex items-center gap-1 rounded-full md:py-4 md:px-[5px] text-xs font-medium',
                    'bg-grey-5 border border-grey-2/60 dark:border-transparent dark:bg-white/10',
                    disabled && 'opacity-50 pointer-events-none',
                    className
                )}
            >
                {STORYBOOK_STYLE_OPTIONS.map((option) => {
                    const isSelected = selectedStyle === option.value
                    return (
                        <button
                            key={option.value}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            disabled={disabled}
                            onClick={() =>
                                onMangaLayoutChange(option.value === 'manga')
                            }
                            className={cn(
                                'cursor-pointer px-3 py-1 rounded-full transition-colors',
                                compact ? 'text-[11px]' : 'text-xs',
                                isSelected
                                    ? 'bg-charcoal text-sky-blue-2 shadow-sm dark:bg-sky-blue-2 dark:text-black'
                                    : 'text-charcoal/70 hover:bg-white/70 dark:text-white/80 dark:hover:bg-white/10'
                            )}
                        >
                            {t(option.labelKey)}
                        </button>
                    )
                })}
            </div>
        </div>
    )
}

// Genre options for storybook
const GENRE_OPTIONS: { value: StorybookGenre; labelKey: string }[] = [
    { value: 'fun_playful', labelKey: 'media.imageSettings.genres.funPlayful' },
    {
        value: 'classic_horror',
        labelKey: 'media.imageSettings.genres.classicHorror'
    },
    {
        value: 'superhero_action',
        labelKey: 'media.imageSettings.genres.superheroAction'
    },
    { value: 'dark_scifi', labelKey: 'media.imageSettings.genres.darkScifi' },
    {
        value: 'high_fantasy',
        labelKey: 'media.imageSettings.genres.highFantasy'
    },
    { value: 'neon_noir', labelKey: 'media.imageSettings.genres.neonNoir' },
    {
        value: 'wasteland_apocalypse',
        labelKey: 'media.imageSettings.genres.wastelandApocalypse'
    },
    {
        value: 'lighthearted_comedy',
        labelKey: 'media.imageSettings.genres.lightheartedComedy'
    },
    { value: 'teen_drama', labelKey: 'media.imageSettings.genres.teenDrama' }
]

interface GenrePickerProps {
    genre: StorybookGenre
    onGenreChange: (genre: StorybookGenre) => void
    disabled?: boolean
}

export function GenrePicker({
    genre,
    onGenreChange,
    disabled
}: GenrePickerProps): ReactElement {
    const { t } = useTranslation()

    const getGenreLabel = (genreValue: StorybookGenre): string => {
        const option = GENRE_OPTIONS.find((opt) => opt.value === genreValue)
        return option ? t(option.labelKey) : genreValue
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed'
                    )}
                >
                    <span>{t('media.imageSettings.genre')}:</span>
                    <span className="truncate max-w-[100px]">
                        {getGenreLabel(genre)}
                    </span>
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-56 p-2 !bg-white shadow-btn max-h-[300px] overflow-y-auto"
                align="start"
                sideOffset={8}
            >
                <DropdownMenuLabel className="text-base font-semibold text-black px-2 py-1">
                    {t('media.imageSettings.genre')}
                </DropdownMenuLabel>
                {GENRE_OPTIONS.map((g) => (
                    <DropdownMenuItem
                        key={g.value}
                        onClick={() => onGenreChange(g.value)}
                        className="flex items-center justify-between px-3 py-2 text-xs rounded-md text-black"
                    >
                        <span>{t(g.labelKey)}</span>
                        <span className="w-4 flex justify-end">
                            {genre === g.value && (
                                <Icon
                                    name="tick"
                                    className="size-4 fill-black"
                                />
                            )}
                        </span>
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

interface MoreSettingsPickerProps {
    genre: StorybookGenre
    onGenreChange: (genre: StorybookGenre) => void
    mangaLayout?: boolean
    richDialogue?: boolean
    onRichDialogueChange?: (enabled: boolean) => void
    voiceEnabled?: boolean
    onVoiceEnabledChange?: (enabled: boolean) => void
    textPosition?: TextPosition
    disabled?: boolean
    className?: string
}

export function MoreSettingsPicker({
    genre,
    onGenreChange,
    mangaLayout = false,
    richDialogue = false,
    onRichDialogueChange,
    voiceEnabled = false,
    onVoiceEnabledChange,
    textPosition,
    disabled,
    className
}: MoreSettingsPickerProps): ReactElement {
    const { t } = useTranslation()

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled}
                    className={cn(
                        'cursor-pointer flex items-center gap-1.5 px-1.5 py-1 rounded-md text-xs font-medium',
                        'bg-charcoal/10 dark:bg-white/10',
                        disabled && 'opacity-50 cursor-not-allowed',
                        className
                    )}
                >
                    <Icon
                        name="plus"
                        className="size-4 fill-black dark:fill-white"
                    />
                    <span>{t('media.imageSettings.more')}</span>
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                className="w-40 px-0 py-1 !bg-white shadow-btn"
                align="start"
                sideOffset={8}
            >
                {/* Genre Submenu */}
                <DropdownMenuSub>
                    <DropdownMenuSubTrigger className="cursor-pointer flex items-center justify-between px-3 py-2 text-xs rounded-md text-black hover:bg-grey-3">
                        <span>{t('media.imageSettings.genre')}</span>
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent
                        className="w-auto md:w-64 px-0 py-2 !bg-white shadow-btn rounded-xl"
                        sideOffset={8}
                    >
                        <DropdownMenuLabel className="text-base font-semibold text-black px-3 py-1">
                            {t('media.imageSettings.genre')}
                        </DropdownMenuLabel>
                        {GENRE_OPTIONS.map((g) => (
                            <DropdownMenuItem
                                key={g.value}
                                onClick={() => onGenreChange(g.value)}
                                className="flex items-center justify-between px-3 py-2 text-xs rounded-md text-black"
                            >
                                <span>{t(g.labelKey)}</span>
                                <span className="w-4 flex justify-end">
                                    {genre === g.value && (
                                        <Icon
                                            name="tick"
                                            className="size-4 fill-black"
                                        />
                                    )}
                                </span>
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuSubContent>
                </DropdownMenuSub>

                {/* Rich Dialogue Submenu - Only show for separate_page mode */}
                {textPosition === 'separate_page' && !mangaLayout && (
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="flex items-center justify-between px-3 py-2.5 text-xs rounded-md text-black hover:bg-grey-3">
                            <span>{t('media.imageSettings.richDialogue')}</span>
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent
                            className="w-[324px] h-[118px] p-0 !bg-white border border-grey dark:border-grey/40 shadow-lg overflow-hidden"
                            sideOffset={8}
                        >
                            <div className="p-3">
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <div className="text-base font-semibold text-black mb-1">
                                            {t(
                                                'media.imageSettings.richDialogue'
                                            )}
                                        </div>
                                        <p className="text-xs text-black/60">
                                            {t(
                                                'media.imageSettings.richDialogueDescription'
                                            )}
                                        </p>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() =>
                                            onRichDialogueChange?.(
                                                !richDialogue
                                            )
                                        }
                                        className={cn(
                                            'relative inline-flex h-6 w-10 items-center rounded-full transition-colors flex-shrink-0 cursor-pointer',
                                            richDialogue
                                                ? 'bg-charcoal'
                                                : 'bg-black/40'
                                        )}
                                    >
                                        <span
                                            className={cn(
                                                'inline-block h-5 w-5 transform rounded-full bg-sky-blue-2 transition-transform',
                                                richDialogue
                                                    ? 'translate-x-[18px]'
                                                    : 'translate-x-1'
                                            )}
                                        />
                                    </button>
                                </div>
                            </div>
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                )}

                {/* Voice Narration */}
                {!mangaLayout && (
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="flex items-center justify-between px-3 py-2.5 text-xs rounded-md text-black hover:bg-grey-3">
                            <span>{t('media.imageSettings.voice')}</span>
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent
                            className="w-[324px] h-[90px] p-0 !bg-white border border-grey dark:border-grey/40 shadow-lg overflow-hidden"
                            sideOffset={8}
                        >
                            <div className="p-3">
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <div className="text-base font-semibold text-black mb-1">
                                            {t('media.imageSettings.voice')}
                                        </div>
                                        <p className="text-xs text-black/60">
                                            {t(
                                                'media.imageSettings.voiceDescription'
                                            )}
                                        </p>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() =>
                                            !disabled &&
                                            onVoiceEnabledChange?.(
                                                !voiceEnabled
                                            )
                                        }
                                        disabled={disabled}
                                        className={cn(
                                            'relative inline-flex h-6 w-10 items-center rounded-full transition-colors flex-shrink-0',
                                            disabled
                                                ? 'cursor-not-allowed opacity-50'
                                                : 'cursor-pointer',
                                            voiceEnabled
                                                ? 'bg-charcoal'
                                                : 'bg-black/40'
                                        )}
                                    >
                                        <span
                                            className={cn(
                                                'inline-block h-5 w-5 transform rounded-full bg-sky-blue-2 transition-transform',
                                                voiceEnabled
                                                    ? 'translate-x-[18px]'
                                                    : 'translate-x-1'
                                            )}
                                        />
                                    </button>
                                </div>
                            </div>
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
