import { useMemo, useState, useEffect } from 'react'
import { Icon } from '../ui/icon'
import {
    mediaTemplateService,
    type MediaTemplate
} from '@/services/media-template.service'
import { type ChatMediaType } from '@/constants/media-type-config'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

type InfographicCategoryKey =
    | 'all'
    | 'educationLearning'
    | 'businessStrategy'
    | 'dataAnalytics'
    | 'governmentPublic'
    | 'scienceResearch'
    | 'creativeEditorial'
    | 'premiumBrand'
    | 'technologyAI'
    | 'globalUniversal'

const INFOGRAPHIC_FILTERS: Array<{
    key: InfographicCategoryKey
    labelKey: string
}> = [
    { key: 'all', labelKey: 'media.templateExplorer.infographicFilters.all' },
    {
        key: 'educationLearning',
        labelKey: 'media.templateExplorer.infographicFilters.educationLearning'
    },
    {
        key: 'businessStrategy',
        labelKey: 'media.templateExplorer.infographicFilters.businessStrategy'
    },
    {
        key: 'dataAnalytics',
        labelKey: 'media.templateExplorer.infographicFilters.dataAnalytics'
    },
    {
        key: 'governmentPublic',
        labelKey: 'media.templateExplorer.infographicFilters.governmentPublic'
    },
    {
        key: 'scienceResearch',
        labelKey: 'media.templateExplorer.infographicFilters.scienceResearch'
    },
    {
        key: 'creativeEditorial',
        labelKey: 'media.templateExplorer.infographicFilters.creativeEditorial'
    },
    {
        key: 'premiumBrand',
        labelKey: 'media.templateExplorer.infographicFilters.premiumBrand'
    },
    {
        key: 'technologyAI',
        labelKey: 'media.templateExplorer.infographicFilters.technologyAI'
    },
    {
        key: 'globalUniversal',
        labelKey: 'media.templateExplorer.infographicFilters.globalUniversal'
    }
]

const INFOGRAPHIC_STYLE_MATCH: Record<string, InfographicCategoryKey[]> = {
    Minimalist: [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'creativeEditorial',
        'premiumBrand',
        'technologyAI',
        'globalUniversal'
    ],
    'Cute & Friendly': [
        'educationLearning',
        'businessStrategy',
        'creativeEditorial',
        'globalUniversal'
    ],
    'Playful & Colorful': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'creativeEditorial',
        'technologyAI',
        'globalUniversal'
    ],
    'Character Illustrations': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'creativeEditorial',
        'technologyAI',
        'globalUniversal'
    ],
    'Narrative Storytelling': [
        'educationLearning',
        'businessStrategy',
        'governmentPublic',
        'scienceResearch',
        'creativeEditorial',
        'premiumBrand',
        'technologyAI',
        'globalUniversal'
    ],
    'Timeline Infographic': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'creativeEditorial',
        'technologyAI',
        'globalUniversal'
    ],
    'Flowchart Infographic': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'technologyAI'
    ],
    'Hierarchy Diagram': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'technologyAI'
    ],
    'Strategic Framework Style': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'premiumBrand',
        'technologyAI'
    ],
    'Dashboard Infographic': [
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'premiumBrand',
        'technologyAI'
    ],
    'Isometric 3D Illustration': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'creativeEditorial',
        'premiumBrand',
        'technologyAI'
    ],
    'Collage / Mixed Media': [
        'educationLearning',
        'creativeEditorial',
        'premiumBrand',
        'globalUniversal'
    ],
    'Retro / Vintage': [
        'educationLearning',
        'governmentPublic',
        'scienceResearch',
        'creativeEditorial',
        'premiumBrand',
        'globalUniversal'
    ],
    'Line-Art / Outline Style': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'technologyAI'
    ],
    'Iconographic Style': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'technologyAI',
        'globalUniversal'
    ],
    'Government Info Style': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'globalUniversal'
    ],
    'Premium Luxury': [
        'businessStrategy',
        'creativeEditorial',
        'premiumBrand',
        'technologyAI'
    ],
    'Futuristic Tech Interface': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'scienceResearch',
        'premiumBrand',
        'technologyAI'
    ],
    'Hand-Drawn Whiteboard Sketch': [
        'educationLearning',
        'businessStrategy',
        'scienceResearch',
        'creativeEditorial',
        'technologyAI',
        'globalUniversal'
    ],
    'Scientific Academic Poster': [
        'educationLearning',
        'businessStrategy',
        'dataAnalytics',
        'governmentPublic',
        'scienceResearch',
        'technologyAI'
    ]
}

const templateMatchesFilter = (
    template: MediaTemplate,
    filter: InfographicCategoryKey
) => {
    if (filter === 'all') return true
    const matches = INFOGRAPHIC_STYLE_MATCH[template.name]
    return matches ? matches.includes(filter) : false
}

interface MediaTemplateExplorerProps {
    isVisible: boolean
    mediaType: ChatMediaType
    selectedTemplate?: string
    onTemplateSelect: (template: MediaTemplate) => void
    handleTemplateClear: () => void
    onClose: () => void
}

export const MediaTemplateExplorer = ({
    isVisible,
    mediaType,
    selectedTemplate,
    onTemplateSelect,
    handleTemplateClear,
    onClose
}: MediaTemplateExplorerProps) => {
    const { t } = useTranslation()
    const templateNameMap = t('media.templateExplorer.templateNames', {
        returnObjects: true
    }) as Record<string, string>
    const isInfographic = mediaType === 'infographic'
    const isPoster = mediaType === 'poster'
    const isInfographicLike = isInfographic || isPoster
    const showTemplateLabel = !isPoster
    const templateAspectRatio = isInfographic
        ? '164/109'
        : isPoster
          ? '2/3'
          : '128/109'
    const [templates, setTemplates] = useState<MediaTemplate[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedFilter, setSelectedFilter] =
        useState<InfographicCategoryKey>('all')
    const [containerOffsets, setContainerOffsets] = useState({
        left: 0,
        right: 0
    })
    const gridClassName = clsx(
        'grid',
        isInfographicLike
            ? 'gap-4 grid-cols-2 sm:grid-cols-3 md:grid-cols-5'
            : 'gap-3 grid-cols-5'
    )

    useEffect(() => {
        if (isVisible) {
            fetchTemplates()
        }
    }, [isVisible, mediaType])

    useEffect(() => {
        if (isVisible) {
            setSelectedFilter('all')
        }
    }, [isVisible, mediaType])

    useEffect(() => {
        if (!isVisible || typeof window === 'undefined') return

        const updateOffsets = () => {
            const homeContainer = document.getElementById('home-container')
            if (homeContainer) {
                const rect = homeContainer.getBoundingClientRect()
                const left = Math.max(0, rect.left)
                const right = Math.max(0, window.innerWidth - rect.right)
                setContainerOffsets({ left, right })
            } else {
                setContainerOffsets({ left: 0, right: 0 })
            }
        }

        updateOffsets()
        window.addEventListener('resize', updateOffsets)
        return () => {
            window.removeEventListener('resize', updateOffsets)
        }
    }, [isVisible])

    const fetchTemplates = async () => {
        try {
            setLoading(true)
            const response = await mediaTemplateService.getMediaTemplates(
                0,
                20,
                mediaType
            )
            setTemplates(response.templates)
        } catch (error) {
            console.error('Failed to fetch media templates:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleTemplateClick = (template: MediaTemplate) => {
        if (selectedTemplate === template.id) {
            handleTemplateClear()
            onClose()
            return
        }
        onTemplateSelect(template)
        onClose()
    }

    const infographicFilters = isInfographic
        ? INFOGRAPHIC_FILTERS.map((filter) => ({
              ...filter,
              label: t(filter.labelKey)
          }))
        : []

    const filteredTemplates = useMemo(() => {
        if (!isInfographic || selectedFilter === 'all') return templates
        return templates.filter((template) =>
            templateMatchesFilter(template, selectedFilter)
        )
    }, [isInfographic, selectedFilter, templates])

    if (!isVisible) return null

    return (
        <div
            className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
            style={{
                paddingLeft: containerOffsets.left,
                paddingRight: containerOffsets.right
            }}
            onClick={onClose}
        >
            {/* Popup Card */}
            <div
                className="relative bg-white rounded-t-2xl md:rounded-2xl shadow-btn w-full md:w-[92vw] max-w-[720px] max-h-[80vh] overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="px-3 pt-5 pb-4 space-y-3">
                    <h2 className="text-base font-medium text-black">
                        {isInfographic
                            ? t('media.templateExplorer.infographicTitle')
                            : isPoster
                              ? t('media.templateExplorer.posterTitle')
                              : t('media.templateExplorer.title')}
                    </h2>
                    {isInfographic && (
                        <div
                            className="flex flex-nowrap gap-2 overflow-x-auto scrollbar-hide pb-1"
                            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
                        >
                            {infographicFilters.map((filter) => {
                                const isActive =
                                    selectedFilter === filter.key
                                return (
                                    <button
                                        key={filter.key}
                                        type="button"
                                        onClick={() =>
                                            setSelectedFilter(filter.key)
                                        }
                                        className={clsx(
                                            'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors flex-shrink-0',
                                            isActive
                                                ? 'bg-sky-blue text-black border-sky-blue'
                                                : 'bg-white text-black/70 border-black/15 hover:border-black/40'
                                        )}
                                    >
                                        {filter.label}
                                    </button>
                                )
                            })}
                        </div>
                    )}
                </div>

                {/* Template Grid */}
                <div className="px-3 pt-2 pb-12 md:pb-6 overflow-y-auto max-h-[calc(80vh-120px)]">
                    {loading ? (
                        <div className={gridClassName}>
                            {Array.from({ length: 20 }).map((_, index) => (
                                <div
                                    key={index}
                                    className="flex flex-col items-center"
                                >
                                    <div
                                        className="w-full rounded-xl bg-neutral-200 dark:bg-neutral-800 animate-pulse"
                                        style={{ aspectRatio: templateAspectRatio }}
                                    />
                                    {showTemplateLabel && (
                                        <div className="mt-2 h-3 w-16 bg-neutral-200 dark:bg-neutral-800 rounded animate-pulse" />
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : filteredTemplates.length === 0 ? (
                        <div className="text-center py-12">
                            <Icon
                                name="gen-image"
                                className="h-12 w-12 text-black/30 dark:text-white/30 mx-auto mb-3"
                            />
                            <p className="text-sm text-black/50 dark:text-white/50">
                                {t('media.stylePicker.empty')}
                            </p>
                        </div>
                    ) : (
                        <div className={gridClassName}>
                            {filteredTemplates.map((template) => {
                                const templateLabel =
                                    templateNameMap?.[template.name] ??
                                    template.name
                                const isSelected =
                                    selectedTemplate === template.id

                                return (
                                    <div
                                        key={template.id}
                                        onClick={() =>
                                            handleTemplateClick(template)
                                        }
                                        className="flex flex-col items-center cursor-pointer group"
                                    >
                                        <div
                                            className={clsx(
                                                'relative w-full rounded-xl overflow-hidden transition-all duration-200 hover:scale-105 hover:shadow-md',
                                                isPoster &&
                                                    isSelected &&
                                                    'ring-3 ring-[#58dcfc]'
                                            )}
                                        >
                                            {template.preview ? (
                                                <img
                                                    src={template.preview}
                                                    alt={templateLabel}
                                                    className="w-full h-full object-cover"
                                                    loading="lazy"
                                                    style={{
                                                        aspectRatio:
                                                            templateAspectRatio
                                                    }}
                                                />
                                            ) : (
                                                <div className="w-full h-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
                                                    <Icon
                                                        name="gen-image"
                                                        className="size-6 text-black/20 dark:text-white/20"
                                                    />
                                                </div>
                                            )}
                                        </div>

                                        {showTemplateLabel && (
                                            <div
                                                className={clsx(
                                                    'mt-2 flex justify-center items-center rounded-full text-xs text-center text-black w-full',
                                                    isInfographicLike
                                                        ? 'min-h-[36px] px-2 py-1'
                                                        : 'h-7',
                                                    {
                                                        'bg-sky-blue font-bold':
                                                            isSelected
                                                    }
                                                )}
                                            >
                                                {isSelected ? (
                                                    <Icon
                                                        name="tick"
                                                        className="size-4 fill-black"
                                                    />
                                                ) : (
                                                    <span
                                                        className={clsx(
                                                            'block w-full',
                                                            isInfographicLike
                                                                ? 'line-clamp-2 leading-tight'
                                                                : 'truncate'
                                                        )}
                                                    >
                                                        {templateLabel}
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
