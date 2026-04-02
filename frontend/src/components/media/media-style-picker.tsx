import { useState, useEffect, useRef } from 'react'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import {
    mediaTemplateService,
    type MediaTemplate
} from '@/services/media-template.service'
import { Icon } from '../ui/icon'
import { type ChatMediaType } from '@/constants/media-type-config'
import { cn } from '@/lib/utils'

interface MediaStylePickerProps {
    isVisible: boolean
    mediaType: ChatMediaType
    selectedTemplate?: string
    onTemplateSelect: (template: MediaTemplate | undefined) => void
    onExploreMore?: () => void
}

export const MediaStylePicker = ({
    isVisible,
    mediaType,
    selectedTemplate,
    onTemplateSelect,
    onExploreMore
}: MediaStylePickerProps) => {
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
          : undefined
    const [templates, setTemplates] = useState<MediaTemplate[]>([])
    const [loading, setLoading] = useState(false)
    const scrollContainerRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (isVisible) {
            fetchTemplates()
        }
    }, [isVisible, mediaType])

    const fetchTemplates = async () => {
        try {
            setLoading(true)
            const response = await mediaTemplateService.getMediaTemplates(
                0,
                5,
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
        // Toggle behavior: deselect if already selected, otherwise select
        if (selectedTemplate === template.id) {
            onTemplateSelect(undefined)
        } else {
            onTemplateSelect(template)
        }
    }

    if (!isVisible) return null

    return (
        <div className="w-full mt-3">
            <p className="text-sm mb-4 font-semibold md:pl-6">
                {isInfographic
                    ? t('media.stylePicker.infographicTitle')
                    : isPoster
                      ? t('media.stylePicker.posterTitle')
                      : t('media.stylePicker.title')}
            </p>

            <div className="relative">
                <div
                    ref={scrollContainerRef}
                    className="flex items-center justify-start gap-3 md:gap-4 overflow-x-auto md:p-4 scrollbar-hide max-w-[calc(100vw-16px)]"
                    style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
                >
                    {loading ? (
                        Array.from({ length: 5 }).map((_, index) => (
                            <div
                                key={index}
                                className={cn(
                                    'flex-shrink-0 rounded-xl bg-neutral-200 dark:bg-neutral-800 animate-pulse',
                                    isInfographicLike
                                        ? 'w-[88px] md:w-[128px]'
                                        : 'w-[100px] h-[100px]'
                                )}
                                style={
                                    isInfographic
                                        ? { aspectRatio: '164/109' }
                                        : templateAspectRatio
                                          ? { aspectRatio: templateAspectRatio }
                                          : undefined
                                }
                            />
                        ))
                    ) : templates.length === 0 ? (
                        <div className="text-sm text-black/50 dark:text-white/50 py-4">
                            {t('media.stylePicker.empty')}
                        </div>
                    ) : (
                        <>
                            {templates.map((template) => {
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
                                        className="flex-shrink-0 cursor-pointer transition-all duration-200 group hover:scale-105 w-[88px] md:w-[128px]"
                                    >
                                        <div
                                            className={cn(
                                                'relative w-[88px] md:w-[128px] rounded-xl overflow-hidden transition-all',
                                                !isInfographicLike &&
                                                    'h-[96px] md:h-[109px]',
                                                isSelected &&
                                                    'ring-3 ring-[#58dcfc]'
                                            )}
                                            style={
                                                templateAspectRatio
                                                    ? {
                                                          aspectRatio:
                                                              templateAspectRatio
                                                      }
                                                    : undefined
                                            }
                                        >
                                            {template.preview ? (
                                                <img
                                                    src={template.preview}
                                                    alt={templateLabel}
                                                    className="w-full h-full object-cover"
                                                    loading="lazy"
                                                />
                                            ) : (
                                                <div className="w-full h-full bg-gradient-to-br from-neutral-200 to-neutral-300 dark:from-neutral-700 dark:to-neutral-800 flex items-center justify-center">
                                                    <Icon
                                                        name="gen-image"
                                                        className="size-8 text-black/30 dark:text-white/30"
                                                    />
                                                </div>
                                            )}
                                        </div>

                                        {showTemplateLabel && (
                                            <div
                                                className={clsx(
                                                    'mt-3 flex items-center justify-center rounded-full text-xs text-center w-full',
                                                    isInfographicLike
                                                        ? 'min-h-[32px] px-2 py-1'
                                                        : 'h-6',
                                                    isSelected
                                                        ? 'bg-sky-blue font-bold text-black'
                                                        : 'text-black/80 dark:text-white/80'
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

                            {onExploreMore && (
                                <button
                                    onClick={onExploreMore}
                                    className="flex-shrink-0 cursor-pointer transition-all duration-200 hover:scale-105"
                                >
                                    <div className="h-[100px] flex items-center justify-center">
                                        <div className="size-12 rounded-full flex items-center justify-center bg-firefly dark:bg-sky-blue/30">
                                            <Icon
                                                name="add-circle"
                                                className="size-6 fill-sky-blue"
                                            />
                                        </div>
                                    </div>
                                    {showTemplateLabel && (
                                        <div className="h-[20px]" />
                                    )}
                                </button>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}
