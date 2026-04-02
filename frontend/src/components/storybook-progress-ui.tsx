import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import { ClickableImage } from '@/components/ui/fullscreen-image-modal'
import { Shimmer } from '@/components/ai-elements/shimmer'
import type { PageSlot, StorybookProgressData } from '@/utils/storybook-progress'
import { getStorybookProgressMessage } from '@/utils/storybook-progress'

interface StorybookProgressUIProps {
    data: StorybookProgressData
    generatingPages?: number[]
}

interface PageSlotContentProps {
    slot: PageSlot
    altText: string
}

const PageSlotContent = memo(({ slot, altText }: PageSlotContentProps) => {
    if (slot.isCompleted && slot.imageUrl) {
        return (
            <ClickableImage
                src={slot.imageUrl}
                alt={altText}
                className="w-full h-full object-cover"
            />
        )
    }

    const bgClasses = "w-full h-full bg-grey-1 dark:bg-charcoal flex items-center justify-center"

    if (slot.isGenerating) {
        return (
            <div className={`${bgClasses} flex-col`}>
                <div className="w-5 h-5 border-2 border-firefly dark:border-grey-2 border-t-transparent dark:border-t-transparent rounded-full animate-spin" />
                <span className="text-[10px] text-grey-4 dark:text-grey-5 mt-1">
                    {slot.pageNumber}
                </span>
            </div>
        )
    }

    return (
        <div className={bgClasses}>
            <span className="text-sm text-grey-4 dark:text-grey-5">
                {slot.pageNumber}
            </span>
        </div>
    )
})

PageSlotContent.displayName = 'PageSlotContent'

/**
 * Reusable storybook progress UI component.
 * Displays progress bar, page grid with placeholders, and error messages.
 */
export const StorybookProgressUI = memo(({ data, generatingPages = [] }: StorybookProgressUIProps) => {
    const { t } = useTranslation()
    const { totalPages, progressPercent, progressStatus, errorMessage, pageSlots } = data

    const progressMessage = getStorybookProgressMessage(t, totalPages, progressStatus, generatingPages)

    const isGenerating = progressStatus === 'generating'

    const isCancelled =
        errorMessage === 'storybook_cancelled' ||
        errorMessage === 'Storybook generation cancelled.'

    return (
        <div className="space-y-3">
            {/* Progress header */}
            <div className="flex items-center justify-between">
                {isGenerating ? (
                    <Shimmer className="text-sm font-medium">
                        {progressMessage}
                    </Shimmer>
                ) : (
                    <span className="text-sm font-medium text-grey-4 dark:text-grey-2">
                        {progressMessage}
                    </span>
                )}
            </div>

            {/* Progress bar */}
            <div className="h-1.5 bg-grey-2 dark:bg-grey-7 rounded-full overflow-hidden">
                <div
                    className="h-full bg-primary transition-all duration-500 ease-out"
                    style={{ width: `${progressPercent}%` }}
                />
            </div>

            {/* Error message if any */}
            {errorMessage && !isCancelled && (
                <p className="text-sm text-red-500">{errorMessage}</p>
            )}

            {/* Page grid with placeholders */}
            <div className="grid grid-cols-5 gap-2 mt-2">
                {pageSlots.map((slot: PageSlot) => (
                    <div
                        key={slot.pageNumber}
                        className="relative aspect-[3/4] rounded-lg overflow-hidden border border-grey-2 dark:border-grey-6"
                    >
                        <PageSlotContent
                            slot={slot}
                            altText={t('tools.storybookPageAlt', {
                                page: slot.pageNumber,
                                defaultValue: `Page ${slot.pageNumber}`
                            })}
                        />
                    </div>
                ))}
            </div>
        </div>
    )
})

StorybookProgressUI.displayName = 'StorybookProgressUI'
